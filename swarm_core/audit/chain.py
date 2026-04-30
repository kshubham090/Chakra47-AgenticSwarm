from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client
from swarm_core.config import SUPABASE_KEY, SUPABASE_URL

_TABLE = "audit_logs"


@dataclass
class AuditEntry:
    id: str
    task_id: str
    agent: str
    status: str
    decision_source: str
    reason: str
    input_hash: str
    prev_hash: str
    block_hash: str
    extra_payload: dict[str, Any]
    created_at: str


def _sha256(data: dict[str, Any]) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _hash_input(raw_input: Any) -> str:
    return hashlib.sha256(str(raw_input).encode()).hexdigest()


class AuditChain:
    """SHA-256 hash-chain logger backed by Supabase. Never calls LLM."""

    _GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise OSError(
                "Missing required env var: SUPABASE_URL / SUPABASE_KEY."
                " Copy .env.example → .env and fill it in, or pass --no-audit."
            )
        self._client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._last_hash: str = self._fetch_last_hash()

    def _fetch_last_hash(self) -> str:
        response = (
            self._client.table(_TABLE)
            .select("block_hash")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["block_hash"]
        return self._GENESIS_HASH

    def log(
        self,
        task_id: str,
        agent: str,
        status: str,
        decision_source: str,
        raw_input: Any,
        reason: str = "",
        extra_payload: dict[str, Any] | None = None,
    ) -> AuditEntry:
        now = datetime.now(timezone.utc).isoformat()
        input_hash = _hash_input(raw_input)
        entry_id = str(uuid.uuid4())

        block_data = {
            "id": entry_id,
            "task_id": task_id,
            "agent": agent,
            "status": status,
            "decision_source": decision_source,
            "reason": reason,
            "input_hash": input_hash,
            "prev_hash": self._last_hash,
            "created_at": now,
        }
        block_hash = _sha256(block_data)

        row = {
            **block_data,
            "block_hash": block_hash,
            "extra_payload": extra_payload or {},
        }

        self._client.table(_TABLE).insert(row).execute()
        self._last_hash = block_hash

        return AuditEntry(
            id=entry_id,
            task_id=task_id,
            agent=agent,
            status=status,
            decision_source=decision_source,
            reason=reason,
            input_hash=input_hash,
            prev_hash=block_data["prev_hash"],
            block_hash=block_hash,
            extra_payload=extra_payload or {},
            created_at=now,
        )

    def verify_chain(self) -> bool:
        """Walks every entry in insertion order and verifies the hash chain is intact."""
        response = self._client.table(_TABLE).select("*").order("created_at", desc=False).execute()
        rows = response.data
        if not rows:
            return True

        prev_hash = self._GENESIS_HASH
        for row in rows:
            expected_block_data = {
                "id": row["id"],
                "task_id": row["task_id"],
                "agent": row["agent"],
                "status": row["status"],
                "decision_source": row["decision_source"],
                "reason": row["reason"],
                "input_hash": row["input_hash"],
                "prev_hash": prev_hash,
                "created_at": row["created_at"],
            }
            expected_hash = _sha256(expected_block_data)
            if expected_hash != row["block_hash"]:
                return False
            prev_hash = row["block_hash"]

        return True
