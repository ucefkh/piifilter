"""PIIFilter v2 — Event-driven pipeline that chains stages via Session.

Each stage receives and returns a Session. Stages emit before/after events
on the EventBus. No stage calls another stage directly.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from piifilter.session import Session
from piifilter.events.bus import EventBus, PipelineEvent
from piifilter.registry.registry import PluginRegistry
from piifilter.config import FilterConfig
from piifilter.shared.models import DetectedEntity, ReplacementMode, RiskLevel
from piifilter.shared.alias_store import AliasStore

logger = logging.getLogger(__name__)


class FilterPipeline:
    """Event-driven pipeline that chains detection → risk → policy → replace → forward.

    Each stage receives and returns a Session. Stages emit before/after events
    on the EventBus. No stage calls another stage directly.
    """

    def __init__(
        self,
        config: Optional[FilterConfig] = None,
        registry: Optional[PluginRegistry] = None,
        event_bus: Optional[EventBus] = None,
        alias_store: Optional[AliasStore] = None,
    ):
        self.config = config or FilterConfig()
        self.registry = registry or PluginRegistry()
        self.event_bus = event_bus or EventBus()
        self.alias_store = alias_store

    async def run(self, session: Session) -> Session:
        """Execute the full pipeline on a Session."""
        session.started_at = datetime.utcnow()

        # Wire alias_store if the pipeline owns one
        if self.alias_store is not None and session.alias_store is None:
            session.alias_store = self.alias_store

        await self.event_bus.emit(PipelineEvent.PIPELINE_START, session)
        session.add_audit("pipeline", "start", {"request_id": session.request_id})

        try:
            # 1. Detect
            await self.event_bus.emit(PipelineEvent.BEFORE_DETECTION, session)
            session = await self._detect(session)
            await self.event_bus.emit(PipelineEvent.AFTER_DETECTION, session)
            session.add_audit("detection", "complete", {"count": len(session.entities)})

            if session.is_blocked:
                return await self._finish(session)

            # 2. Risk
            await self.event_bus.emit(PipelineEvent.BEFORE_RISK, session)
            session = await self._assess_risk(session)
            await self.event_bus.emit(PipelineEvent.AFTER_RISK, session)
            session.add_audit("risk", "complete", {"score": session.risk.score if session.risk else 0})

            if session.is_blocked:
                return await self._finish(session)

            # 3. Policy
            await self.event_bus.emit(PipelineEvent.BEFORE_POLICY, session)
            session = await self._apply_policy(session)
            await self.event_bus.emit(PipelineEvent.AFTER_POLICY, session)

            if session.is_blocked:
                return await self._finish(session)

            # 4. Replace
            await self.event_bus.emit(PipelineEvent.BEFORE_REPLACEMENT, session)
            session = await self._replace(session)
            await self.event_bus.emit(PipelineEvent.AFTER_REPLACEMENT, session)
            session.add_audit("replacement", "complete", {"replacements": len(session.replacements)})

            # 5. Forward
            if session.provider_config:
                await self.event_bus.emit(PipelineEvent.BEFORE_FORWARD, session)
                session = await self._forward(session)
                await self.event_bus.emit(PipelineEvent.AFTER_FORWARD, session)

        except Exception as exc:
            logger.exception("Pipeline error for request %s", session.request_id)
            session.blocked = True
            session.block_reason = f"Pipeline error: {exc}"
            await self.event_bus.emit(PipelineEvent.PIPELINE_ERROR, session)
            session.add_audit("pipeline", "error", {"error": str(exc)})

        return await self._finish(session)

    async def _detect(self, session: Session) -> Session:
        """Run all registered detectors on the session."""
        all_entities = []
        for detector in self.registry.list_detectors():
            try:
                entities = await detector.detect(session.prompt)
                all_entities.extend(entities)
            except Exception as exc:
                logger.warning("Detector %s failed: %s", detector.name, exc)
                session.add_audit("detection", "error", {
                    "detector": detector.name,
                    "error": str(exc),
                })
                await self.event_bus.emit(
                    PipelineEvent.PIPELINE_ERROR, session
                )

        # Priority-based dedup: give regex higher priority than presidio
        # for overlapping spans, since regex has higher precision.
        # Sort by detector priority first (regex=0, presidio=1, gliner=2),
        # then by score descending, then position.
        all_entities.sort(key=lambda e: (
            0 if (e.get("detector") if isinstance(e, dict) else e.detector) == "regex"
            else 1 if (e.get("detector") if isinstance(e, dict) else e.detector) == "presidio"
            else 2,
            -(e.get("score") if isinstance(e, dict) else e.score),
            e.get("start") if isinstance(e, dict) else e.start,
        ))

        # ── max(raw, pipeline) merge ───────────────────────────────────
        # Save raw regex results BEFORE dedup. When pipeline_mode is True
        # we UNION them back after dedup so pipeline can never remove a
        # correct regex match.  Regex has perfect precision on its entity
        # types — if it matched, the match is real.
        _raw_regex_entities: list[dict | DetectedEntity] = [
            e for e in all_entities
            if _entity_detector(e) == "regex"
        ]

        # Dedup by interval: if a higher-priority (regex) entity already
        # covers this span, skip lower-priority ones.
        # But if a lower-priority entity has a DIFFERENT type and is NOT
        # fully contained by the same-type interval, keep it.
        # Cross-type suppression: Presidio PERSON detections that overlap
        # with structural entity types (FILE_PATH, URL, EMAIL, etc.) are
        # likely NER noise from structured fields — suppress them to
        # preserve PERSON precision.
        _PERSON_CROSS_SUPPRESS_TYPES = {
            "FILE_PATH", "URL", "DOMAIN", "EMAIL", "IP_ADDRESS",
            "API_KEY", "JWT", "SSH_KEY", "DATABASE_URL", "PRIVATE_URL",
            "CREDIT_CARD", "SOCIAL_SECURITY", "PASSPORT", "IBAN",
            # Name-like types: regex already handles these with perfect or
            # near-perfect precision. Presidio PERSON overlapping these is
            # always a duplicate — suppress it.
            "EMPLOYEE_NAME", "CUSTOMER_NAME", "PROJECT_NAME",
        }

        # Common English words that Presidio NER often misidentifies as PERSON
        # when they appear capitalized at the start of sentences or in headings.
        # These are not real person names — suppress any PERSON detection that
        # consists entirely of one of these tokens.
        _COMMON_WORDS: set[str] = {
            "the", "a", "an", "in", "on", "at", "by", "to", "of", "for",
            "with", "from", "and", "or", "but", "not", "this", "that",
            "these", "those", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "must",
            "shall", "can", "need", "dare", "ought",
            "i", "you", "he", "she", "it", "we", "they",
            "me", "him", "her", "us", "them",
            "my", "your", "his", "its", "our", "their",
            "mine", "yours", "hers", "ours", "theirs",
            "who", "whom", "which", "what", "whose",
            "man", "woman", "person", "people", "child",
            "day", "week", "month", "year", "time", "today",
            "monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "spring", "summer", "autumn", "winter",
            "hello", "hi", "hey", "good", "bad", "new", "old",
            "first", "last", "next", "previous", "final",
            "one", "two", "three", "four", "five", "six", "seven",
            "eight", "nine", "ten",
            "yes", "no", "ok", "okay", "please", "thank", "thanks",
            "info", "information", "data", "file", "code", "text",
            "test", "name", "type", "user", "admin", "system",
            "see", "let", "use", "get", "set", "put", "make", "take",
            "note", "page", "line", "end", "start", "order", "case",
            "high", "low", "top", "bottom", "left", "right", "center",
            "now", "here", "there", "where", "how", "why", "when",
            "all", "some", "any", "many", "much", "few", "several",
            "each", "every", "both", "either", "neither",
            "other", "another", "such", "same", "different",
            "back", "still", "well", "just", "only", "also", "very",
            "too", "quite", "rather", "enough",
            "up", "down", "over", "under", "above", "below",
            "before", "after", "during", "within", "without",
            "about", "around", "between", "among", "through",
            "against", "along", "across", "behind", "beyond",
            "into", "onto", "upon", "out", "off", "away",
            "again", "ever", "never", "always", "often",
            "usually", "sometimes", "rarely", "seldom",
            "then", "than", "as", "so", "if", "else",
            "while", "because", "since", "until", "though",
            "although", "unless", "whereas",
            "result", "default", "failed", "error", "warning",
            "success", "status", "value", "key", "path", "home",
            "type", "public", "private", "internal", "external",
            "config", "setup", "init", "list", "index", "total",
            "server", "client", "host", "port", "link", "site",
            "cat", "dog", "rat", "bat", "hat",
            "img", "src", "href", "url", "uri", "urn",
            "select", "insert", "update", "delete", "from", "where",
            "true", "false", "null", "none", "nil", "empty",
            "next", "prev", "back", "forward",
            "member", "group", "team", "role", "owner", "guide",
            "table", "row", "column", "cell", "field", "form",
            "done", "ready", "wait", "stop", "go", "run",
            "add", "remove", "edit", "view", "show", "hide",
            "open", "close", "save", "load", "send", "receive",
            "find", "search", "filter", "sort", "print",
            "include", "exclude", "merge", "split", "join",
            "support", "help", "contact", "about", "home",
            "product", "service", "price", "cost", "rate", "plan",
            "sign", "login", "logout", "register", "reset",
            "billing", "account", "profile", "setting", "option",
            "security", "privacy", "policy", "terms", "condition",
            "read", "write", "copy", "paste", "cut",
            "tag", "label", "note", "mark", "flag",
            "source", "target", "origin", "destination",
            "build", "deploy", "release", "version", "commit",
            "bug", "fix", "patch", "update", "change",
            "feature", "enhancement", "improvement", "optimization",
            "download", "upload", "sync", "backup", "restore",
            "api", "rest", "graphql", "grpc", "soap",
            "json", "xml", "yaml", "toml", "csv", "tsv",
            "back", "cancel", "create", "delete", "enable", "disable",
            # Additional common words found in FP analysis
            "email", "mail", "token", "cert", "key", "pass",
            "subject", "body", "header", "footer",
            "address", "phone", "mobile", "fax",
            "id", "ids", "ref", "no", "num", "str", "int",
            "bool", "obj", "arr", "dict", "list",
            "manager", "director", "ceo", "cto", "cfo",
            "employee", "customer", "client", "vendor",
            "username", "password", "secret", "salt",
            "hash", "encrypt", "decrypt", "auth", "perm",
            "access", "grant", "deny", "allow", "block",
            "web", "app", "desktop", "mobile", "cloud",
            "dir", "dirs", "file", "files", "doc", "docs",
            "log", "logs", "msg", "message", "title",
            "desc", "description", "summary", "detail",
            "note", "notes", "comment", "comments",
        }

        seen_intervals: dict[str, list[tuple[int, int]]] = {}
        all_interval_map: dict[str, list[tuple[int, int]]] = {}
        deduped = []
        for e in all_entities:
            if isinstance(e, dict):
                et = e.get("entity_type", "UNKNOWN")
                estart, eend = e.get("start", 0), e.get("end", 0)
                evalue = e.get("value", "")
                detector = e.get("detector", "")
            else:
                et = e.type.value if hasattr(e.type, 'value') else str(e.type)
                estart, eend = e.start, e.end
                evalue = getattr(e, 'text', getattr(e, 'value', ''))
                detector = getattr(e, 'detector', '')

            # ── PERSON false-positive guards ──────────────────────────
            # These apply only to Presidio NER PERSON detections, since
            # regex PERSON already has perfect precision (1.0).
            if et == "PERSON" and detector == "presidio":
                text_lower = evalue.strip().lower()

                # 1. Short name guard: suppress single-character or
                #    very short spans that are unlikely to be real names.
                if len(evalue.strip()) < 3:
                    continue

                # 2. Numeric guard: suppress if the span contains digits
                #    (real person names don't have numbers).
                if any(ch.isdigit() for ch in evalue):
                    continue

                # 3. Common word guard: if the span is a single token
                #    that matches a very common English word, suppress it.
                tokens = text_lower.split()
                if len(tokens) == 1 and tokens[0] in _COMMON_WORDS:
                    continue

                # 4. All-common guard: if every token in a multi-token
                #    span is a common word (e.g. "The Man", "First Name"),
                #    suppress it too.
                if len(tokens) > 1 and all(t in _COMMON_WORDS for t in tokens):
                    continue

                # 5. Email-context guard: if a multi-word PERSON span is
                #    followed immediately (with or without space) by an
                #    opening paren or email-like text, it's likely a
                #    name-in-email-header format where regex already
                #    handles the entity.
                # Use session.prompt (original text) to check context after the span.
                after_span = session.prompt[eend:eend+20] if eend < len(session.prompt) else ""
                if after_span.strip().startswith("(") or after_span.strip().startswith("<"):
                    continue

            # Cross-type suppression: PERSON from NER that overlaps with
            # a structural entity type is likely noise.
            if et == "PERSON":
                overlaps_structural = False
                for stype in _PERSON_CROSS_SUPPRESS_TYPES:
                    s_intervals = all_interval_map.get(stype, [])
                    for s, e2 in s_intervals:
                        if not (eend <= s or estart >= e2):
                            overlaps_structural = True
                            break
                    if overlaps_structural:
                        break
                if overlaps_structural:
                    continue

            # ── IP_ADDRESS double-fire suppression ─────────────────────
            # Presidio/Gliner IP_ADDRESS detections that overlap with regex
            # IP_ADDRESS detections are duplicates. Regex has higher
            # precision for IP addresses — suppress NER-based IPs that
            # overlap any regex-matched span.
            if et == "IP_ADDRESS" and detector in ("presidio", "gliner"):
                regex_ip_intervals = all_interval_map.get("IP_ADDRESS", [])
                ner_suppressed = False
                for s, e2 in regex_ip_intervals:
                    # NER IP fully contained in regex IP — suppress
                    if s <= estart and eend <= e2:
                        ner_suppressed = True
                        break
                    # NER IP overlaps a regex IP span — suppress
                    if not (eend <= s or estart >= e2):
                        ner_suppressed = True
                        break
                if ner_suppressed:
                    continue

            intervals = seen_intervals.get(et, [])
            contained = any(s <= estart and eend <= e2 for s, e2 in intervals)
            if not contained:
                seen_intervals.setdefault(et, []).append((estart, eend))
                all_interval_map.setdefault(et, []).append((estart, eend))
                deduped.append(e)

        # ── max(raw, pipeline) merge ────────────────────────────────
        # When pipeline_mode is True, UNION raw-regex results back in.
        # This ensures pipeline dedup can NEVER remove a correct regex
        # match.  For overlapping spans we prefer the regex entity
        # (perfect precision) over any other detector's result.
        if session.config.detection.pipeline_mode and _raw_regex_entities:
            # Build a set of (start, end, type) for entities already in deduped
            deduped_spans: set[tuple[int, int, str]] = set()
            for e in deduped:
                s, endpos, et = _entity_span(e)
                deduped_spans.add((s, endpos, et))

            for raw_e in _raw_regex_entities:
                rs, rend, ret = _entity_span(raw_e)
                raw_key = (rs, rend, ret)

                # If this exact regex entity is NOT in deduped, add it back.
                # Also check for containment: if no deduped entity of the
                # same type fully contains this span, add it.
                if raw_key in deduped_spans:
                    continue

                # Check if a deduped entity of the same type already
                # fully contains this span.  If so, the regex entity is
                # a duplicate — skip.  But if it's a DIFFERENT type or
                # not contained, keep the regex match.
                contained_by_dedup = any(
                    s <= rs and rend <= endpos and et == ret
                    for s, endpos, et in deduped_spans
                )
                if not contained_by_dedup:
                    deduped.append(raw_e)
                    deduped_spans.add(raw_key)

        deduped.sort(key=lambda e: e.get("start") if isinstance(e, dict) else e.start)
        session.entities = deduped
        return session

    async def _assess_risk(self, session: Session) -> Session:
        """Calculate risk score based on detected entities."""
        score = 0.0
        critical_types = set()
        details = []

        from piifilter.shared.models import RiskAssessment, RiskLevel

        for entity in session.entities:
            et = entity.type.value
            if et in ("API_KEY", "JWT", "SSH_KEY", "DATABASE_URL", "SOCIAL_SECURITY", "CREDIT_CARD", "PASSPORT", "IBAN"):
                pts = 25
                critical_types.add(et)
            elif et in ("BANK_ACCOUNT", "PRIVATE_URL", "GPS"):
                pts = 15
            elif et in ("EMAIL", "PHONE", "ADDRESS", "FILE_PATH", "IP_ADDRESS"):
                pts = 10
            else:
                pts = 5
            score += pts
            details.append({"text": entity.text[:40], "type": et, "points": pts})

        score = min(score, 100.0)
        if score <= 25:
            level = RiskLevel.LOW
        elif score <= 50:
            level = RiskLevel.MEDIUM
        elif score <= 75:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL

        session.risk = RiskAssessment(
            score=score,
            level=level,
            detected_count=len(session.entities),
            critical_entities=sorted(critical_types),
            recommendation={
                RiskLevel.LOW: "Proceed — minimal sensitive data detected",
                RiskLevel.MEDIUM: "Review — consider masking sensitive fields",
                RiskLevel.HIGH: "Review required — sensitive information detected",
                RiskLevel.CRITICAL: "Block prompt — critical credentials detected",
            }.get(level, ""),
            details=details,
        )
        return session

    async def _apply_policy(self, session: Session) -> Session:
        """Evaluate policy rules against detected entities and risk."""
        if not session.config.policy.rules:
            return session

        for rule in session.config.policy.rules:
            condition = rule.if_condition
            entity_types_in_condition = condition.get("type", "")
            risk_threshold = condition.get("risk", 0)
            operator = condition.get("operator", ">=")

            # Check entity type rules
            if entity_types_in_condition:
                types_list = [entity_types_in_condition] if isinstance(entity_types_in_condition, str) else entity_types_in_condition
                for entity in session.entities:
                    if entity.type.value in types_list and rule.action == "BLOCK":
                        session.blocked = True
                        session.block_reason = f"Policy BLOCK: {entity.type.value} detected ({entity.text[:40]})"
                        return session

            # Check risk score rules
            if risk_threshold and session.risk:
                if operator == ">" and session.risk.score > risk_threshold:
                    if rule.action == "BLOCK":
                        session.blocked = True
                        session.block_reason = f"Policy BLOCK: risk {session.risk.score:.0f} > {risk_threshold}"
                        return session

        return session

    async def _replace(self, session: Session) -> Session:
        """Apply the selected replacement strategy."""
        if not session.entities:
            session.filtered_prompt = session.prompt
            return session

        strategy_name = session.mode.value if session.mode else session.config.replacement.default_strategy
        strategy = self.registry.get_strategy_or_none(strategy_name)

        if strategy:
            filtered_text, replacements = await strategy.replace(session, session.entities)
            session.filtered_prompt = filtered_text
            session.replacements = replacements
        else:
            # Fallback: basic semantic replacement
            text = session.prompt
            replacements = []
            for entity in sorted(session.entities, key=lambda e: e.start, reverse=True):
                alias = session.get_alias(entity.text, entity.type.value if hasattr(entity.type, 'value') else str(entity.type))
                text = text[:entity.start] + alias + text[entity.end:]
                replacements.append(type('R', (), {'original': entity.text, 'replacement': alias, 'entity_type': entity.type, 'mode': ReplacementMode.SEMANTIC})())
            session.filtered_prompt = text
            session.replacements = replacements

        return session

    async def _forward(self, session: Session) -> Session:
        """Forward filtered prompt to LLM provider."""
        if not session.filtered_prompt:
            session.filtered_prompt = session.prompt

        provider_name = session.provider_config.name if session.provider_config else session.config.provider.name
        provider = self.registry.get_provider_or_none(provider_name)

        if provider:
            try:
                session.llm_response = await provider.forward(session)
                session.add_audit("forward", "complete", {"provider": provider_name})
            except Exception as exc:
                session.llm_response = f"[PIIFilter Error: {exc}]"
                session.add_audit("forward", "error", {"provider": provider_name, "error": str(exc)})
        else:
            session.blocked = True
            session.block_reason = f"Provider '{provider_name}' not found in registry"
            session.llm_response = f"[PIIFilter Error: Provider '{provider_name}' not registered]"

        return session

    async def _finish(self, session: Session) -> Session:
        """Finalize the session with timing and end event."""
        session.completed_at = datetime.utcnow()
        await self.event_bus.emit(PipelineEvent.PIPELINE_END, session)
        session.add_audit("pipeline", "complete", {"latency_ms": session.latency_ms})
        return session

    async def close(self) -> None:
        """Shutdown all registered plugins."""
        await self.registry.shutdown_all()


# ── Module-level helpers ────────────────────────────────────────────


def _entity_detector(e: dict | DetectedEntity) -> str:
    """Extract detector name from an entity dict or DetectedEntity object."""
    if isinstance(e, dict):
        return e.get("detector", "")
    return getattr(e, "detector", "")


def _entity_span(e: dict | DetectedEntity) -> tuple[int, int, str]:
    """Extract (start, end, entity_type) from an entity dict or DetectedEntity."""
    if isinstance(e, dict):
        return (
            e.get("start", 0),
            e.get("end", 0),
            e.get("entity_type", "UNKNOWN"),
        )
    return (e.start, e.end, e.type.value if hasattr(e.type, 'value') else str(e.type))