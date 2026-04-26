from __future__ import annotations

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_VALID_TARGETS: frozenset[str] = frozenset({
    "orchestrator",
    "audit_agent",
    "mission_planner",
    "risk_agent",
    "resource_monitor",
    "anomaly_detector",
    "human_operator",
})


class CommsAgent(BaseAgent):
    """
    Validates and routes messages between agents and human operators.
    BLOCK on empty message or unknown target.
    Always deterministic — no LLM path.
    """

    name = "comms_agent"
    description = "Validates message format and target, then approves routing."

    def __init__(self, valid_targets: set[str] | frozenset[str] | None = None) -> None:
        self._valid_targets: frozenset[str] = (
            frozenset(valid_targets) if valid_targets is not None else _DEFAULT_VALID_TARGETS
        )

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with 'message' and 'target' keys",
            )

        raw_message = context.input.get("message")
        target = str(context.input.get("target", "")).strip()

        if raw_message is None:
            # No explicit message — auto-build a status update from mission context
            mission = context.metadata.get("agent_outputs", {}).get("mission_planner", {})
            if not mission:
                return AgentResult.passed(agent=self.name, payload={"skipped": True})
            message = (
                f"Swarm pipeline status: mission '{mission.get('mission_type', 'unknown')}' "
                f"— {mission.get('step_count', 0)} steps planned"
            )
            target = target or "orchestrator"
        else:
            message = str(raw_message).strip()
            if not message:
                return AgentResult.blocked(agent=self.name, reason="Empty message cannot be routed")
            if not target:
                return AgentResult.blocked(agent=self.name, reason="Routing target is required")

        if target not in self._valid_targets:
            return AgentResult.blocked(
                agent=self.name,
                reason=f"Unknown routing target: {target!r}",
            )

        priority = str(context.input.get("priority", "normal")).lower()
        return AgentResult.passed(
            agent=self.name,
            payload={
                "routed_to": target,
                "priority": priority,
                "message_length": len(message),
                "message": message,
            },
        )
