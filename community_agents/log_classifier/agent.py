from __future__ import annotations

from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_CRITICAL = frozenset({"CRITICAL", "FATAL", "PANIC", "EMERG"})
_ERROR = frozenset({"ERROR", "ERR", "EXCEPTION", "TRACEBACK", "STDERR"})
_WARN = frozenset({"WARN", "WARNING", "DEPRECATED", "CAUTION"})


class LogClassifier(BaseAgent):
    """
    Classifies a single log line by severity.

    Input: ``{"log_line": "<raw log string>"}``

    Decision table (deterministic, code path only):
    - CRITICAL / FATAL / PANIC  → BLOCK   (halt pipeline — system-level failure)
    - ERROR / EXCEPTION         → ESCALATE (needs human review)
    - WARN / DEPRECATED         → PASS    (flagged in payload)
    - INFO / DEBUG / unknown    → PASS
    """

    name = "log_classifier"
    description = (
        "Classifies a log line by severity: CRITICAL→BLOCK, ERROR→ESCALATE, WARN/INFO→PASS."
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        extra_critical = {k.upper() for k in cfg.get("critical_keywords", [])}
        extra_error = {k.upper() for k in cfg.get("error_keywords", [])}
        extra_warn = {k.upper() for k in cfg.get("warn_keywords", [])}
        self._critical = _CRITICAL | extra_critical
        self._error = _ERROR | extra_error
        self._warn = _WARN | extra_warn

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with a 'log_line' key",
            )

        log_line = context.input.get("log_line")
        if log_line is None:
            return AgentResult.passed(agent=self.name, payload={"skipped": True})
        if not isinstance(log_line, str):
            return AgentResult.exception(
                agent=self.name,
                reason=f"'log_line' must be a string, got {type(log_line).__name__}",
            )

        severity = self._classify(log_line)
        logger.info("log_classifier: %s → %s", log_line[:80], severity)

        if severity == "CRITICAL":
            return AgentResult.blocked(
                agent=self.name,
                reason=f"Critical log entry detected: {log_line[:120]}",
            )
        if severity == "ERROR":
            return AgentResult.escalate(
                agent=self.name,
                reason=f"Error log entry requires review: {log_line[:120]}",
            )
        return AgentResult.passed(
            agent=self.name,
            payload={"severity": severity, "flagged": severity == "WARN"},
        )

    def _classify(self, line: str) -> str:
        upper = line.upper()
        for token in self._critical:
            if token in upper:
                return "CRITICAL"
        for token in self._error:
            if token in upper:
                return "ERROR"
        for token in self._warn:
            if token in upper:
                return "WARN"
        return "INFO"
