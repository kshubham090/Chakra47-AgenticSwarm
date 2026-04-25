from __future__ import annotations

import math
from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class PathPlanner(BaseAgent):
    """
    Plans a path through an ordered list of (x, y) waypoints.
    BLOCK if too few waypoints, ESCALATE if too many (human review needed).
    Always deterministic — no LLM path.
    """

    name = "path_planner"
    description = "Validates waypoints and computes path distance. Deterministic for all valid inputs."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._min_waypoints: int = cfg.get("min_waypoints", 2)
        self._max_waypoints: int = cfg.get("max_waypoints", 50)

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with a 'waypoints' key",
            )

        waypoints = context.input.get("waypoints")
        if not isinstance(waypoints, list):
            return AgentResult.exception(
                agent=self.name,
                reason="'waypoints' must be a list of [x, y] pairs",
            )

        if len(waypoints) < self._min_waypoints:
            return AgentResult.blocked(
                agent=self.name,
                reason=(
                    f"At least {self._min_waypoints} waypoints required, "
                    f"got {len(waypoints)}"
                ),
            )
        if len(waypoints) > self._max_waypoints:
            return AgentResult.escalate(
                agent=self.name,
                reason=(
                    f"Too many waypoints ({len(waypoints)} > {self._max_waypoints}) "
                    f"— requires human review"
                ),
            )

        try:
            distance = self._total_distance(waypoints)
        except (TypeError, ValueError) as exc:
            return AgentResult.exception(
                agent=self.name,
                reason=f"Invalid waypoint format — expected [x, y] pairs: {exc}",
            )

        return AgentResult.passed(
            agent=self.name,
            payload={
                "path": waypoints,
                "waypoint_count": len(waypoints),
                "total_distance": distance,
            },
        )

    @staticmethod
    def _total_distance(waypoints: list) -> float:
        total = 0.0
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            total += math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        return round(total, 4)
