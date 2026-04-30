from __future__ import annotations

from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_WEIGHTS: dict[str, float] = {
    "risk_score": 1.0,
    "severity": 0.5,
    "confidence": -0.3,  # higher confidence in safety lowers the composite score
}


class RiskAgent(BaseAgent):
    """
    Aggregates weighted numeric risk signals into a composite score and classifies it.
    Unknown signal keys fall back to weight=1.0.
    Always deterministic — no LLM path.
    """

    name = "risk_agent"
    description = (
        "Computes a composite risk score from weighted numeric signals and classifies risk level."
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._critical_threshold: float = cfg.get("critical_threshold", 0.8)
        self._elevated_threshold: float = cfg.get("elevated_threshold", 0.5)
        self._weights: dict[str, float] = cfg.get("weights", _DEFAULT_WEIGHTS)

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict of named numeric risk signals",
            )

        signals = {k: v for k, v in context.input.items() if isinstance(v, (int, float))}
        if not signals:
            return AgentResult.exception(
                agent=self.name,
                reason="No numeric risk signals found in input",
            )

        weighted_sum = sum(self._weights.get(k, 1.0) * v for k, v in signals.items())
        score = min(1.0, max(0.0, weighted_sum))

        logger.debug("risk_agent: composite score=%.4f signals=%s", score, signals)

        if score >= self._critical_threshold:
            return AgentResult.blocked(
                agent=self.name,
                reason=(
                    f"Composite risk score {score:.3f} exceeds"
                    f" critical threshold {self._critical_threshold}"
                ),
            )
        if score >= self._elevated_threshold:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Composite risk score {score:.3f} exceeds"
                    f" elevated threshold {self._elevated_threshold}"
                ),
            )

        return AgentResult.passed(
            agent=self.name,
            payload={"composite_risk_score": round(score, 4), "signals": signals},
        )
