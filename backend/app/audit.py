"""
Append-only, hash-chained audit trail.

Every entry embeds the SHA-256 hash of the entry before it, so the chain can be
replayed and verified independently of the application that wrote it (the same
property blockchains use for tamper-evidence, without needing a distributed
ledger — a single authoritative log is enough for a servicing audit trail).
Entries are written to Postgres with INSERT-only privileges for the app role;
UPDATE/DELETE are revoked at the DB grant level so tampering requires DBA access,
which is itself logged by the database's own audit extension (e.g. pgAudit).

In production, entries would also be forwarded to Splunk / Elasticsearch via the
`sink` hook below for real-time SOC monitoring and long-term retention separate
from the transactional DB.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    id: str
    session_id: str
    timestamp: str
    event_type: str          # e.g. "classification" | "policy_decision" | "tool_call" | "escalation" | "message"
    actor: str                # "agent" | "policy_engine" | "member" | "core_system:<name>"
    payload: dict[str, Any]
    prev_hash: str
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        canonical = json.dumps(
            {
                "id": self.id,
                "session_id": self.session_id,
                "timestamp": self.timestamp,
                "event_type": self.event_type,
                "actor": self.actor,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


class AuditLog:
    """
    In-memory reference implementation. Swap `_store` for a Postgres-backed
    append-only table (INSERT-only grant) in production; the hashing scheme
    is unchanged since it depends only on entry content, not storage.
    """

    def __init__(self, sink: Optional[Callable[[AuditEntry], None]] = None) -> None:
        self._chains: dict[str, list[AuditEntry]] = {}
        self._sink = sink  # e.g. push to Splunk HEC / Elasticsearch index

    def append(
        self,
        session_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> AuditEntry:
        chain = self._chains.setdefault(session_id, [])
        prev_hash = chain[-1].hash if chain else GENESIS_HASH
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            actor=actor,
            payload=payload,
            prev_hash=prev_hash,
        )
        chain.append(entry)
        if self._sink:
            self._sink(entry)
        return entry

    def get_chain(self, session_id: str) -> list[AuditEntry]:
        return list(self._chains.get(session_id, []))

    def verify(self, session_id: str) -> tuple[bool, Optional[str]]:
        """Recompute every hash and every link; return (is_valid, first_broken_id)."""
        chain = self._chains.get(session_id, [])
        expected_prev = GENESIS_HASH
        for entry in chain:
            if entry.prev_hash != expected_prev:
                return False, entry.id
            recomputed = entry._compute_hash()
            if recomputed != entry.hash:
                return False, entry.id
            expected_prev = entry.hash
        return True, None


# Module-level singleton for the scaffold; inject a request-scoped instance
# (or a DB-backed one) in a real deployment instead.
audit_log = AuditLog()
