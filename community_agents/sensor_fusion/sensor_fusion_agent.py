from __future__ import annotations

import statistics
from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class SensorFusionAgent(BaseAgent):
    """
    Fuses readings from multiple named sensor streams into a single consensus result.

    Input::

        {
            "sensors": {"temperature": 72.4, "pressure": 101.3, "humidity": 55.0},
            "required": ["temperature"]   # optional — sensors that must be present
        }

    Decision table (deterministic, code path only):

    - Missing required sensor         → BLOCK   (critical data absent)
    - Max deviation > conflict_threshold → ESCALATE (sensors disagree)
    - Any reading > outlier_threshold from mean → ESCALATE (rogue sensor)
    - All sensors agree                → PASS   (fused mean in payload)
    """

    name = "sensor_fusion"
    description = "Fuses readings from multiple sensor streams into a single consensus result."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._conflict_threshold: float = float(cfg.get("conflict_threshold", 15.0))
        self._outlier_threshold: float = float(cfg.get("outlier_threshold", 20.0))

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with a 'sensors' key containing named numeric readings",
            )

        raw_sensors = context.input.get("sensors")
        if raw_sensors is None:
            return AgentResult.exception(
                agent=self.name,
                reason="Input dict must contain a 'sensors' key",
            )
        if not isinstance(raw_sensors, dict) or len(raw_sensors) == 0:
            return AgentResult.exception(
                agent=self.name,
                reason="'sensors' must be a non-empty dict of {name: numeric_value}",
            )

        try:
            sensors: dict[str, float] = {k: float(v) for k, v in raw_sensors.items()}
        except (TypeError, ValueError) as exc:
            return AgentResult.exception(
                agent=self.name,
                reason=f"All sensor values must be numeric: {exc}",
            )

        required: list[str] = context.input.get("required") or []
        block_result = self._check_required(sensors, required)
        if block_result is not None:
            return block_result

        if len(sensors) == 1:
            only_value = next(iter(sensors.values()))
            logger.info("sensor_fusion: single sensor — passing through (value=%.4f)", only_value)
            return AgentResult.passed(
                agent=self.name,
                payload={
                    "fused_mean": round(only_value, 4),
                    "max_deviation": 0.0,
                    "sensor_count": 1,
                    "sensors": sensors,
                },
            )

        values = list(sensors.values())
        mean = statistics.mean(values)
        max_deviation = max(abs(v - mean) for v in values)
        worst_sensor = max(sensors, key=lambda k: abs(sensors[k] - mean))

        logger.info(
            "sensor_fusion: mean=%.4f max_deviation=%.4f sensors=%d",
            mean,
            max_deviation,
            len(sensors),
        )

        if max_deviation > self._outlier_threshold:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Sensor outlier detected: '{worst_sensor}' deviates {max_deviation:.2f} "
                    f"from mean {mean:.2f} (outlier_threshold={self._outlier_threshold})"
                ),
            )

        if max_deviation > self._conflict_threshold:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Sensor conflict: max deviation {max_deviation:.2f} exceeds "
                    f"conflict_threshold={self._conflict_threshold} "
                    f"(worst sensor: '{worst_sensor}')"
                ),
            )

        return AgentResult.passed(
            agent=self.name,
            payload={
                "fused_mean": round(mean, 4),
                "max_deviation": round(max_deviation, 4),
                "sensor_count": len(sensors),
                "sensors": sensors,
            },
        )

    def _check_required(
        self, sensors: dict[str, float], required: list[str]
    ) -> AgentResult | None:
        missing = [name for name in required if name not in sensors]
        if missing:
            return AgentResult.blocked(
                agent=self.name,
                reason=f"Required sensor(s) missing from input: {missing}",
            )
        return None
