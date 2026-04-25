from __future__ import annotations

from swarm_core.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_MISSION_STEPS: dict[str, list[str]] = {
    "patrol":   ["define_route", "check_resources", "execute_patrol", "report_findings"],
    "deliver":  ["verify_payload", "plan_path", "execute_delivery", "confirm_receipt"],
    "inspect":  ["identify_target", "run_diagnostics", "compile_report", "notify_operator"],
    "report":   ["collect_data", "format_report", "route_to_comms", "archive"],
    "standby":  ["enter_idle", "monitor_alerts", "await_orders"],
    "monitor":  ["set_observation_window", "collect_metrics", "evaluate_thresholds", "report_status"],
    "scan":     ["define_scan_area", "execute_scan", "analyze_results", "report_findings"],
    "alert":    ["identify_trigger", "assess_severity", "notify_stakeholders", "log_event"],
}


class MissionPlanner(BaseAgent):
    """
    Decomposes known mission types into deterministic step plans.
    Unknown types fall back to the LLM bridge (exception path only).
    """

    name = "mission_planner"
    description = "Converts a mission_type into an ordered step plan. LLM fallback for unknown types."

    def __init__(self, known_types: list[str] | None = None, llm_bridge: object | None = None) -> None:
        from swarm_core.rules.llm_bridge import LLMBridge
        self._known_types: set[str] = set(known_types) if known_types is not None else set(_MISSION_STEPS)
        self._llm_bridge = llm_bridge if llm_bridge is not None else LLMBridge()

    def run(self, context: AgentContext) -> AgentResult:
        result = self._deterministic_logic(context)
        if result.status != AgentStatus.EXCEPTION:
            return result
        logger.info("mission_planner: unknown mission type — delegating to LLM bridge")
        return self._llm_bridge.classify(context, agent_name=self.name)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with a 'mission_type' key",
            )

        mission_type = str(context.input.get("mission_type", "")).lower().strip()
        if not mission_type:
            return AgentResult.exception(
                agent=self.name,
                reason="'mission_type' is required",
            )

        if mission_type not in self._known_types:
            return AgentResult.exception(
                agent=self.name,
                reason=f"Unknown mission type: {mission_type!r}",
            )

        steps = _MISSION_STEPS.get(mission_type, [])
        return AgentResult.passed(
            agent=self.name,
            payload={"mission_type": mission_type, "steps": steps, "step_count": len(steps)},
        )
