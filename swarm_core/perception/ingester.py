from __future__ import annotations

import json
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from swarm_core.base import AgentContext
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class SourceType(str, Enum):
    DICT = "dict"
    JSON = "json"
    TEXT = "text"
    FILE = "file"
    BYTES = "bytes"
    PASSTHROUGH = "context"
    UNKNOWN = "unknown"


class Ingester:
    """
    Layer 1 — Perception.
    Normalizes any raw input into an AgentContext.
    Deterministic — no LLM calls, ever.
    """

    def ingest(self, raw: Any, task_id: str | None = None) -> AgentContext:
        """Convert raw input from any source into a structured AgentContext."""
        if isinstance(raw, AgentContext):
            logger.debug("ingester: passthrough — already an AgentContext")
            return raw

        tid = task_id or str(uuid.uuid4())

        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            logger.debug("ingester: decoded %d bytes", len(raw))
            ctx = self._from_str(text, tid)
            ctx.metadata["source_type"] = SourceType.BYTES
            return ctx

        if isinstance(raw, Path):
            return self._from_path(raw, tid)

        if isinstance(raw, str):
            return self._from_str(raw, tid)

        if isinstance(raw, dict):
            ctx = self._from_dict(raw, tid)
            ctx.metadata["source_type"] = SourceType.DICT
            return ctx

        logger.warning("ingester: unknown input type %s — wrapping as-is", type(raw).__name__)
        return AgentContext(
            input=raw,
            task_id=tid,
            metadata={"source_type": SourceType.UNKNOWN, "raw_type": type(raw).__name__},
        )

    def _from_str(self, raw: str, task_id: str) -> AgentContext:
        stripped = raw.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    ctx = self._from_dict(parsed, task_id)
                    ctx.metadata["source_type"] = SourceType.JSON
                    return ctx
            except json.JSONDecodeError:
                pass
        # Wrap plain text so downstream agents always receive a dict.
        # Agents that need specific keys (risk_score, waypoints …) will skip gracefully.
        return AgentContext(
            input={"text": stripped},
            task_id=task_id,
            metadata={"source_type": SourceType.TEXT},
        )

    def _from_path(self, path: Path, task_id: str) -> AgentContext:
        if not path.exists():
            logger.error("ingester: file not found: %s", path)
            return AgentContext(
                input={"error": f"File not found: {path}"},
                task_id=task_id,
                metadata={"source_type": SourceType.FILE, "path": str(path), "error": True},
            )
        contents = path.read_text(encoding="utf-8", errors="replace")
        logger.debug("ingester: read %d chars from %s", len(contents), path)
        ctx = self._from_str(contents, task_id)
        ctx.metadata["source_type"] = SourceType.FILE
        ctx.metadata["path"] = str(path)
        return ctx

    def _from_dict(self, raw: dict[str, Any], task_id: str) -> AgentContext:
        """Extract envelope keys (task_id, metadata) and return an AgentContext.
        Source type is NOT set here — the caller always sets it.
        """
        tid = str(raw.get("task_id", task_id))
        metadata: dict[str, Any] = dict(raw.get("metadata", {}))

        if "input" in raw:
            payload: Any = raw["input"]
        else:
            payload = {k: v for k, v in raw.items() if k not in ("task_id", "metadata")}

        return AgentContext(input=payload, task_id=tid, metadata=metadata)
