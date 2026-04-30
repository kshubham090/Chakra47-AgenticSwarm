from __future__ import annotations

import statistics
from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class AnomalyDetector(BaseAgent):
    """
    Detects statistical anomalies via z-score analysis.
    Always deterministic — no LLM path.
    Requires at least 2 numeric values in context.input['values'].
    """

    name = "anomaly_detector"
    description = "Flags statistical outliers in numeric data using z-score thresholds."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._z_threshold: float = cfg.get("z_score_threshold", 2.5)
        self._severe_z_threshold: float = cfg.get("severe_z_score_threshold", 4.0)

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with a 'values' key containing a list of numbers",
            )

        raw_values = context.input.get("values")
        if raw_values is None:
            return AgentResult.passed(agent=self.name, payload={"skipped": True})
        if len(raw_values) < 2:
            return AgentResult.exception(
                agent=self.name,
                reason=f"At least 2 values required for anomaly detection, got {len(raw_values)}",
            )

        try:
            values = [float(v) for v in raw_values]
        except (TypeError, ValueError) as exc:
            return AgentResult.exception(
                agent=self.name, reason=f"Non-numeric value in input: {exc}"
            )

        mean = statistics.mean(values)
        std = statistics.stdev(values)

        if std == 0.0:
            return AgentResult.passed(
                agent=self.name,
                payload={"max_z_score": 0.0, "anomaly": False, "mean": mean, "std": 0.0},
            )

        z_scores = [abs((v - mean) / std) for v in values]
        max_z = max(z_scores)
        worst_idx = z_scores.index(max_z)

        if max_z >= self._severe_z_threshold:
            return AgentResult.blocked(
                agent=self.name,
                reason=(
                    f"Severe anomaly: z={max_z:.2f} at index {worst_idx} "
                    f"(threshold={self._severe_z_threshold})"
                ),
            )
        if max_z >= self._z_threshold:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Anomaly detected: z={max_z:.2f} at index {worst_idx} "
                    f"(threshold={self._z_threshold})"
                ),
            )

        return AgentResult.passed(
            agent=self.name,
            payload={
                "max_z_score": round(max_z, 4),
                "anomaly": False,
                "mean": round(mean, 4),
                "std": round(std, 4),
            },
        )
