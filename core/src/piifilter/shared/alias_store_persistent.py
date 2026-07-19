"""Persistent alias store backends for conversation-scoped deterministic aliasing.

Provides:
- ``AliasBackend`` — abstract base class
- ``MemoryAliasBackend`` — thread-safe in-memory dict (original default)
- ``SQLiteAliasBackend`` — persistent, encrypted SQLite-backed store

Encryption uses Fernet (symmetric AES-128-CBC with HMAC). When
``PIIFILTER_STORE_KEY`` is set, both the original value and the alias
are encrypted at rest. A deterministic *lookup key* (SHA-256 hash of the
plaintext) is stored alongside the encrypted value so lookups remain fast
without revealing the plaintext.

Usage:

    from piifilter.shared.alias_store import AliasStore
    from piifilter.shared.alias_store_persistent import SQLiteAliasBackend

    backend = SQLiteAliasBackend()
    store = AliasStore(backend=backend)
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from piifilter.shared.utils import generate_alias

# ── Constants ─────────────────────────────────────────────────────────

DEFAULT_DB_DIR = Path.home() / ".piifilter"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "aliases.db"
DEFAULT_TTL_HOURS = 24
FERNET_SALT = b"piifilter_alias_store_salt_v1"  # fixed salt for deterministic key derivation


# ── Backend interface ─────────────────────────────────────────────────


class AliasBackend(ABC):
    """Abstract interface for alias storage backends.

    Implementations must be thread-safe.
    """

    @abstractmethod
    def get_or_create(self, conversation_id: str, original: str, entity_type: Optional[str] = None) -> str:
        """Return existing alias for *original* in *conversation_id*, or create one."""
        ...

    @abstractmethod
    def get_original(self, conversation_id: str, alias: str) -> Optional[str]:
        """Reverse-lookup: given an alias, return the original value (or None)."""
        ...

    @abstractmethod
    def get_all(self, conversation_id: str) -> dict[str, str]:
        """Return all ``{original: alias}`` mappings for a conversation."""
        ...

    @abstractmethod
    def clear_conversation(self, conversation_id: str) -> None:
        """Remove all mappings for a conversation."""

    @abstractmethod
    def clear_all(self) -> None:
        """Reset the entire store."""


# ── In-memory backend (original default) ──────────────────────────────


class MemoryAliasBackend(AliasBackend):
    """Thread-safe in-memory dict-based alias backend.

    This is the default backend used when no persistent store is configured.
    """

    def __init__(self, seed: str = "deterministic"):
        self._seed = seed
        self._lock = threading.RLock()
        self._store: dict[str, dict[str, str]] = {}  # conv_id -> {original: alias}
        self._reverse: dict[str, dict[str, str]] = {}  # conv_id -> {alias: original}

    def get_or_create(self, conversation_id: str, original: str, entity_type: Optional[str] = None) -> str:
        with self._lock:
            conv = self._store.setdefault(conversation_id, {})
            rev = self._reverse.setdefault(conversation_id, {})
            if original in conv:
                return conv[original]
            alias = generate_alias(original, self._seed, conversation_id)
            conv[original] = alias
            rev[alias] = original
            return alias

    def get_original(self, conversation_id: str, alias: str) -> Optional[str]:
        with self._lock:
            return self._reverse.get(conversation_id, {}).get(alias)

    def get_all(self, conversation_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._store.get(conversation_id, {}))

    def clear_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._store.pop(conversation_id, None)
            self._reverse.pop(conversation_id, None)

    def clear_all(self) -> None:
        with self._lock:
            self._store.clear()
            self._reverse.clear()

    @property
    def conversation_count(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def total_mappings(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._store.values())


# ── Helpers ────────────────────────────────────────────────────────────


def _get_store_key() -> Optional[str]:
    """Return the store encryption key from env var, or None."""
    return os.environ.get("PIIFILTER_STORE_KEY")


def _derive_fernet_key(passphrase: str) -> "Fernet":
    """Derive a Fernet key from *passphrase* using PBKDF2."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=FERNET_SALT,
        iterations=600_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
    return Fernet(key)


def _make_fernet() -> Optional[object]:
    """Create a Fernet instance from the env var, or return None."""
    key = _get_store_key()
    if key is None:
        return None
    return _derive_fernet_key(key)


def _encrypt(fernet: Optional[object], plaintext: str) -> str:
    """Encrypt *plaintext* if a Fernet key is available, otherwise return as-is."""
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def _decrypt(fernet: Optional[object], ciphertext: str) -> str:
    """Decrypt *ciphertext* if a Fernet key is available, otherwise return as-is."""
    if fernet is None:
        return ciphertext
    return fernet.decrypt(ciphertext.encode()).decode()


# ── SQLite persistent backend ─────────────────────────────────────────


class SQLiteAliasBackend(AliasBackend):
    """Persistent alias store backed by an encrypted SQLite database.

    Features:
      - Stores aliases in ``~/.piifilter/aliases.db`` (configurable via env var
        ``PIIFILTER_DB_PATH``).
      - Encrypts ``alias`` and ``original`` columns at rest using Fernet when
        ``PIIFILTER_STORE_KEY`` is set (required to enable persistence).
      - Auto-purges conversations older than *ttl_hours* (default 24).
      - Thread-safe via SQLite's built-in locking and a reentrant Python lock.

    .. note::

       If ``PIIFILTER_STORE_KEY`` is not set, the backend falls *back* to
       storing plaintext.  This is intentional so that unit tests and
       ephemeral usage work without configuration, while the env var gates
       encryption for production deployments.
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        seed: str = "deterministic",
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        self._seed = seed
        self._ttl_hours = ttl_hours
        self._db_path = Path(db_path or os.environ.get("PIIFILTER_DB_PATH", DEFAULT_DB_PATH))
        self._lock = threading.RLock()

        # Derive Fernet key once at construction
        self._fernet = _make_fernet()

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def __repr__(self) -> str:
        encrypted = self._fernet is not None
        return (
            f"SQLiteAliasBackend(db={self._db_path}, "
            f"encrypted={encrypted}, ttl={self._ttl_hours}h)"
        )

    # ── Database initialisation ────────────────────────────────────

    def _init_db(self) -> None:
        """Create the database and table if they don't exist.

        The schema uses ``lookup_key`` for forward lookups (original->alias)
        and ``alias_lookup_key`` for reverse lookups (alias->original).
        Both are deterministic hashes so lookups remain fast even when
        the actual values are encrypted with non-deterministic Fernet.
        """
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    conversation_id TEXT NOT NULL,
                    lookup_key TEXT NOT NULL,
                    alias_lookup_key TEXT NOT NULL DEFAULT '',
                    original TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    entity_type TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_aliases_conv_lookup
                ON aliases (conversation_id, lookup_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_aliases_conv_alias
                ON aliases (conversation_id, alias_lookup_key)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection with row factory."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _purge_expired(self, conn: sqlite3.Connection) -> None:
        """Delete rows older than TTL."""
        cutoff = time.time() - self._ttl_hours * 3600
        conn.execute("DELETE FROM aliases WHERE created_at < ?", (cutoff,))
        conn.commit()

    def _lookup_hash(self, plaintext: str) -> str:
        """Deterministic hash for lookups when encryption is enabled."""
        return hashlib.sha256(plaintext.encode()).hexdigest()

    # ── Backend interface ──────────────────────────────────────────

    def get_or_create(self, conversation_id: str, original: str, entity_type: Optional[str] = None) -> str:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired(conn)
                lookup = self._lookup_hash(original)

                # Lookup existing by deterministic key
                row = conn.execute(
                    "SELECT alias FROM aliases WHERE conversation_id = ? AND lookup_key = ?",
                    (conversation_id, lookup),
                ).fetchone()

                if row is not None:
                    return _decrypt(self._fernet, row["alias"])

                # Create new alias
                alias = generate_alias(original, self._seed, conversation_id)
                enc_original = _encrypt(self._fernet, original)
                enc_alias = _encrypt(self._fernet, alias)
                alias_lookup = self._lookup_hash(alias)
                now = time.time()

                conn.execute(
                    """INSERT INTO aliases
                       (conversation_id, lookup_key, alias_lookup_key, original, alias, entity_type, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (conversation_id, lookup, alias_lookup, enc_original, enc_alias, entity_type, now),
                )
                conn.commit()
                return alias
            finally:
                conn.close()

    def get_original(self, conversation_id: str, alias: str) -> Optional[str]:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired(conn)
                alias_lookup = self._lookup_hash(alias)

                row = conn.execute(
                    "SELECT original FROM aliases WHERE conversation_id = ? AND alias_lookup_key = ?",
                    (conversation_id, alias_lookup),
                ).fetchone()
                if row is None:
                    return None
                return _decrypt(self._fernet, row["original"])
            finally:
                conn.close()

    def get_all(self, conversation_id: str) -> dict[str, str]:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired(conn)
                rows = conn.execute(
                    "SELECT original, alias FROM aliases WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchall()
                result: dict[str, str] = {}
                for row in rows:
                    orig = _decrypt(self._fernet, row["original"])
                    alias = _decrypt(self._fernet, row["alias"])
                    result[orig] = alias
                return result
            finally:
                conn.close()

    def clear_conversation(self, conversation_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM aliases WHERE conversation_id = ?", (conversation_id,))
                conn.commit()
            finally:
                conn.close()

    def clear_all(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM aliases")
                conn.commit()
            finally:
                conn.close()