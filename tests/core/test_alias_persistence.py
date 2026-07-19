"""Tests for persistent AliasStore — SQLite backend, encryption, and TTL.

Verifies:
  - MemoryAliasBackend remains default and works identically to before
  - SQLiteAliasBackend persists across store instances
  - Encryption at rest (plaintext not visible in DB)
  - TTL auto-purge
  - Thread safety
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from piifilter.shared.alias_store import AliasStore
from piifilter.shared.alias_store_persistent import (
    MemoryAliasBackend,
    SQLiteAliasBackend,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db_path():
    """Return a temporary database path that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_aliases.db"


@pytest.fixture
def sqlite_backend(db_path: Path) -> SQLiteAliasBackend:
    return SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=24)


@pytest.fixture
def encrypted_backend(db_path: Path) -> SQLiteAliasBackend:
    """Backend with encryption enabled via env var override."""
    old = os.environ.get("PIIFILTER_STORE_KEY")
    os.environ["PIIFILTER_STORE_KEY"] = "test-encryption-key-42"
    try:
        yield SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=24)
    finally:
        if old is not None:
            os.environ["PIIFILTER_STORE_KEY"] = old
        else:
            os.environ.pop("PIIFILTER_STORE_KEY", None)


# ── Memory backend tests (backward compatibility) ────────────────────


class TestMemoryAliasBackend:
    """Original in-memory behaviour must remain unchanged."""

    def test_default_backend_is_memory(self):
        store = AliasStore()
        assert isinstance(store.backend, MemoryAliasBackend)

    def test_get_or_create_consistent(self):
        store = AliasStore(seed="test")
        a1 = store.get_or_create("conv-1", "Alice")
        a2 = store.get_or_create("conv-1", "Alice")
        assert a1 == a2

    def test_reverse_lookup(self):
        store = AliasStore(seed="test")
        alias = store.get_or_create("conv-1", "Bob")
        assert store.get_original("conv-1", alias) == "Bob"

    def test_reverse_lookup_unknown(self):
        store = AliasStore(seed="test")
        assert store.get_original("conv-1", "Nonexistent") is None

    def test_different_convs_different_aliases(self):
        store = AliasStore(seed="test")
        a1 = store.get_or_create("conv-1", "Bob")
        a2 = store.get_or_create("conv-2", "Bob")
        assert a1 != a2

    def test_get_all(self):
        store = AliasStore(seed="test")
        store.get_or_create("conv-1", "Alice")
        store.get_or_create("conv-1", "Bob")
        mappings = store.get_all("conv-1")
        assert "Alice" in mappings
        assert "Bob" in mappings

    def test_get_all_unknown_conversation(self):
        store = AliasStore(seed="test")
        assert store.get_all("nonexistent") == {}

    def test_clear_conversation(self):
        store = AliasStore(seed="test")
        store.get_or_create("conv-1", "Alice")
        store.clear_conversation("conv-1")
        assert store.get_all("conv-1") == {}

    def test_clear_all(self):
        store = AliasStore(seed="test")
        store.get_or_create("conv-1", "Alice")
        store.get_or_create("conv-2", "Bob")
        store.clear_all()
        assert store.get_all("conv-1") == {}
        assert store.get_all("conv-2") == {}

    def test_thread_safety(self):
        store = AliasStore(seed="test")
        errors: list[Exception] = []

        def worker(name: str) -> None:
            try:
                for i in range(100):
                    a = store.get_or_create("shared-conv", f"value-{name}-{i}")
                    assert a is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(chr(65 + i),)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety failed: {errors}"


# ── SQLite backend tests (persistence) ───────────────────────────────


class TestSQLiteAliasBackend:
    """SQLite backend: persistence, correctness, and lifecycle."""

    def test_get_or_create_consistent(self, sqlite_backend: SQLiteAliasBackend):
        a1 = sqlite_backend.get_or_create("conv-1", "Alice")
        a2 = sqlite_backend.get_or_create("conv-1", "Alice")
        assert a1 == a2

    def test_reverse_lookup(self, sqlite_backend: SQLiteAliasBackend):
        alias = sqlite_backend.get_or_create("conv-1", "Bob")
        assert sqlite_backend.get_original("conv-1", alias) == "Bob"

    def test_reverse_lookup_unknown(self, sqlite_backend: SQLiteAliasBackend):
        assert sqlite_backend.get_original("conv-1", "Nonexistent") is None

    def test_different_convs_different_aliases(self, sqlite_backend: SQLiteAliasBackend):
        a1 = sqlite_backend.get_or_create("conv-1", "Bob")
        a2 = sqlite_backend.get_or_create("conv-2", "Bob")
        assert a1 != a2

    def test_get_all(self, sqlite_backend: SQLiteAliasBackend):
        sqlite_backend.get_or_create("conv-1", "Alice")
        sqlite_backend.get_or_create("conv-1", "Bob")
        mappings = sqlite_backend.get_all("conv-1")
        assert mappings == {"Alice": mappings["Alice"], "Bob": mappings["Bob"]}

    def test_get_all_empty(self, sqlite_backend: SQLiteAliasBackend):
        assert sqlite_backend.get_all("nonexistent") == {}

    def test_clear_conversation(self, sqlite_backend: SQLiteAliasBackend):
        sqlite_backend.get_or_create("conv-1", "Alice")
        sqlite_backend.clear_conversation("conv-1")
        assert sqlite_backend.get_all("conv-1") == {}

    def test_clear_all(self, sqlite_backend: SQLiteAliasBackend):
        sqlite_backend.get_or_create("conv-1", "Alice")
        sqlite_backend.get_or_create("conv-2", "Bob")
        sqlite_backend.clear_all()
        assert sqlite_backend.get_all("conv-1") == {}
        assert sqlite_backend.get_all("conv-2") == {}

    def test_persistence_across_instances(self, db_path: Path):
        """Data stored in one backend instance is readable from another."""
        backend1 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        backend1.get_or_create("conv-1", "Alice", "PERSON")
        backend1.get_or_create("conv-1", "bob@example.com", "EMAIL")

        backend2 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        mappings = backend2.get_all("conv-1")
        assert "Alice" in mappings
        assert "bob@example.com" in mappings
        # Same seed + same conversation = same alias
        assert mappings["Alice"] == backend1.get_or_create("conv-1", "Alice", "PERSON")

    def test_with_entity_type(self, sqlite_backend: SQLiteAliasBackend):
        alias = sqlite_backend.get_or_create("conv-1", "Alice", "PERSON")
        assert alias is not None
        assert sqlite_backend.get_original("conv-1", alias) == "Alice"

    def test_uses_same_seed_as_alias_store(self, db_path: Path):
        """The SQLite backend integrated via AliasStore produces same aliases."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="deterministic")
        store = AliasStore(seed="deterministic", backend=backend)
        alias = store.get_or_create("conv-1", "John Smith")
        assert alias is not None
        # Verify it persisted
        assert store.get_original("conv-1", alias) == "John Smith"

    def test_thread_safety(self, db_path: Path):
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        errors: list[Exception] = []

        def worker(name: str) -> None:
            try:
                for i in range(50):
                    a = backend.get_or_create("shared-conv", f"value-{name}-{i}")
                    assert a is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(chr(65 + i),)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety failed: {errors}"


# ── Encryption at rest tests ─────────────────────────────────────────


class TestEncryptedBackend:
    """Encrypted SQLite backend: ciphertext in DB, plaintext in API."""

    def test_encrypted_data_not_visible_as_plaintext(self, encrypted_backend: SQLiteAliasBackend, db_path: Path):
        """The original and alias values must be encrypted in the database."""
        encrypted_backend.get_or_create("conv-1", "Alice", "PERSON")
        encrypted_backend.get_or_create("conv-1", "bob@example.com", "EMAIL")

        # Read raw DB — values should NOT appear as plaintext
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT original, alias FROM aliases").fetchall()
        conn.close()

        for original, alias in rows:
            # Values should be Fernet tokens (base64 with dots), not plaintext
            assert "Alice" not in str(original), "Original should be encrypted in DB"
            assert "bob@example.com" not in str(alias), "Alias should be encrypted in DB"
            # Should look like encrypted base64 (not plaintext readable)
            assert str(original).startswith("g"), "Encrypted values should be base64"

    def test_readable_via_backend(self, encrypted_backend: SQLiteAliasBackend, db_path: Path):
        """Despite encryption at rest, the API returns plaintext."""
        encrypted_backend.get_or_create("conv-1", "Alice", "PERSON")
        assert encrypted_backend.get_original("conv-1", encrypted_backend.get_or_create("conv-1", "Alice")) == "Alice"

    def test_persistence_across_instances_encrypted(self, db_path: Path):
        """Encrypted data survives backend instance recreation (same key)."""
        old = os.environ.get("PIIFILTER_STORE_KEY")
        os.environ["PIIFILTER_STORE_KEY"] = "persistent-test-key"
        try:
            backend1 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
            backend1.get_or_create("conv-1", "Alice", "PERSON")

            backend2 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
            assert "Alice" in backend2.get_all("conv-1")
            assert backend2.get_original("conv-1", backend2.get_or_create("conv-1", "Alice")) == "Alice"
        finally:
            if old is not None:
                os.environ["PIIFILTER_STORE_KEY"] = old
            else:
                os.environ.pop("PIIFILTER_STORE_KEY", None)

    def test_different_key_fails_to_decrypt(self, db_path: Path):
        """Data encrypted with one key is unreadable with a different key."""
        os.environ["PIIFILTER_STORE_KEY"] = "key-one"
        try:
            backend1 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
            backend1.get_or_create("conv-1", "SecretValue", "PERSON")
        finally:
            os.environ.pop("PIIFILTER_STORE_KEY", None)

        # Re-open with different key
        os.environ["PIIFILTER_STORE_KEY"] = "key-two"
        try:
            backend2 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
            # get_all should raise on decryption failure
            with pytest.raises(Exception):
                backend2.get_all("conv-1")
        finally:
            os.environ.pop("PIIFILTER_STORE_KEY", None)

    def test_no_encryption_without_key(self, db_path: Path):
        """Without PIIFILTER_STORE_KEY, values are stored in plaintext."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        backend.get_or_create("conv-1", "PlainTextValue", "PERSON")

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT original FROM aliases").fetchall()
        conn.close()
        assert any("PlainTextValue" in str(row[0]) for row in rows)


# ── TTL (auto-purge) tests ───────────────────────────────────────────


class TestAliasTTL:
    """Time-to-live auto-purge: conversations older than TTL are dropped."""

    def test_ttl_purges_old_entries(self, db_path: Path):
        """After TTL expires, old entries are purged on next access."""
        # Create a backend with 0-hour TTL
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=0)
        backend.get_or_create("conv-1", "Alice")
        backend.get_or_create("conv-1", "Bob")
        # Wait so entries age past TTL=0 cutoff
        time.sleep(0.5)

        # Access triggers purge
        mappings = backend.get_all("conv-1")
        assert mappings == {}, f"Expected empty, got {mappings}"

    def test_ttl_keeps_recent_entries(self, db_path: Path):
        """Entries within TTL are preserved."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=24)
        backend.get_or_create("conv-1", "Alice")
        assert "Alice" in backend.get_all("conv-1")

    def test_ttl_mixed_entries(self, db_path: Path):
        """Only expired entries are purged; recent ones survive (same backend)."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=24)
        backend.get_or_create("old-conv", "OldValue")

        # Manually set created_at to 25 hours ago (past the 24h TTL)
        conn = backend._connect()
        cutoff_past = time.time() - 25 * 3600
        conn.execute("UPDATE aliases SET created_at = ? WHERE conversation_id = ?", (cutoff_past, "old-conv"))
        conn.commit()
        conn.close()

        # This triggers purge — old entry should be gone
        backend.get_or_create("new-conv", "NewValue")

        assert backend.get_all("old-conv") == {}, "Old entries should be purged"
        assert "NewValue" in backend.get_all("new-conv")

    def test_default_ttl_value(self, db_path: Path):
        """Default TTL is 24 hours."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        assert backend._ttl_hours == 24

    def test_custom_ttl_accepted(self, db_path: Path):
        """Custom TTL value is accepted."""
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed", ttl_hours=48)
        assert backend._ttl_hours == 48


# ── AliasStore integration with SQLiteBackend ─────────────────────────


class TestAliasStoreWithSQLiteBackend:
    """AliasStore works transparently with the SQLite backend."""

    def test_store_accepts_sqlite_backend(self, sqlite_backend: SQLiteAliasBackend):
        store = AliasStore(seed="test-seed", backend=sqlite_backend)
        assert isinstance(store.backend, SQLiteAliasBackend)

    def test_get_or_create_via_store(self, db_path: Path):
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store = AliasStore(seed="test-seed", backend=backend)
        alias = store.get_or_create("conv-1", "Alice")
        assert store.get_original("conv-1", alias) == "Alice"

    def test_persistence_via_store_across_instances(self, db_path: Path):
        """Persistence works when accessed via AliasStore wrapper."""
        backend1 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store1 = AliasStore(seed="test-seed", backend=backend1)
        store1.get_or_create("conv-1", "PersistentValue")

        backend2 = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store2 = AliasStore(seed="test-seed", backend=backend2)
        assert "PersistentValue" in store2.get_all("conv-1")

    def test_clear_all_via_store(self, db_path: Path):
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store = AliasStore(seed="test-seed", backend=backend)
        store.get_or_create("conv-1", "Alice")
        store.clear_all()
        assert store.get_all("conv-1") == {}

    def test_clear_conversation_via_store(self, db_path: Path):
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store = AliasStore(seed="test-seed", backend=backend)
        store.get_or_create("conv-1", "Alice")
        store.clear_conversation("conv-1")
        assert store.get_all("conv-1") == {}

    def test_thread_safety_via_store(self, db_path: Path):
        backend = SQLiteAliasBackend(db_path=db_path, seed="test-seed")
        store = AliasStore(seed="test-seed", backend=backend)
        errors: list[Exception] = []

        def worker(name: str) -> None:
            try:
                for i in range(50):
                    a = store.get_or_create("shared-conv", f"value-{name}-{i}")
                    assert a is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(chr(65 + i),)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety failed: {errors}"