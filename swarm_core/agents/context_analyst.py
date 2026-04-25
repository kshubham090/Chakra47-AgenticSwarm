from __future__ import annotations

from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_FAILURE_STATUSES: frozenset[str] = frozenset({"BLOCK", "EXCEPTION"})


class ContextAnalyst(BaseAgent):
    """
    Analyzes the context history for failure trends.
    A high failure rate in recent history indicates systemic issues.
    Always deterministic — no LLM path.
    """

    name = "context_analyst"
    description = "Detects failure trends in context history using a sliding window."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._window: int = cfg.get("history_window", 10)
        self._critical_rate: float = cfg.get("critical_failure_rate", 0.7)
        self._elevated_rate: float = cfg.get("elevated_failure_rate", 0.4)

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        history = context.history
        if not history:
            return AgentResult.passed(
                agent=self.name,
                payload={"trend": "no_history", "failure_rate": 0.0, "window": 0},
            )

        recent = history[-self._window:]
        failure_count = sum(1 for h in recent if h.get("status") in _FAILURE_STATUSES)
        failure_rate = failure_count / len(recent)
        payload: dict[str, Any] = {
            "failure_rate": round(failure_rate, 4),
            "window": len(recent),
            "failures": failure_count,
        }

        if failure_rate >= self._critical_rate:
            return AgentResult.blocked(
                agent=self.name,
                reason=(
                    f"Critical failure rate in recent history: "
                    f"{failure_rate:.0%} ({failure_count}/{len(recent)})"
                ),
            )
        if failure_rate >= self._elevated_rate:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Elevated failure rate in recent history: "
                    f"{failure_rate:.0%} ({failure_count}/{len(recent)})"
                ),
            )

        return AgentResult.passed(agent=self.name, payload=payload)
