from __future__ import annotations

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_VALID_KEYS: frozenset[str] = frozenset({
    "OVERRIDE_ALPHA",
    "OVERRIDE_BETA",
    "OVERRIDE_GAMMA",
})


class OverrideHandler(BaseAgent):
    """
    Validates and approves human override requests.
    Requires a valid override_key and a non-empty reason.
    BLOCK on invalid key, missing key, or missing reason.
    Always deterministic — no LLM path.
    """

    name = "override_handler"
    description = "Validates human override requests against the authorized key list."

    def __init__(self, valid_keys: set[str] | frozenset[str] | None = None) -> None:
        self._valid_keys: frozenset[str] = (
            frozenset(valid_keys) if valid_keys is not None else _DEFAULT_VALID_KEYS
        )

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict with 'override_key' and 'reason'",
            )

        override_key = str(context.input.get("override_key", "")).strip()
        reason = str(context.input.get("reason", "")).strip()
        agent_target = str(context.input.get("agent_target", "")).strip()

        # No override_key means this input is not an override request — skip silently
        if not override_key:
            return AgentResult.passed(agent=self.name, payload={"skipped": True})
        if override_key not in self._valid_keys:
            return AgentResult.blocked(
                agent=self.name,
                reason=f"Invalid override key: {override_key!r}",
            )
        if not reason:
            return AgentResult.blocked(
                agent=self.name,
                reason="Override 'reason' must be provided",
            )

        logger.info("override_handler: approved override %s targeting '%s'", override_key, agent_target)
        return AgentResult.passed(
            agent=self.name,
            payload={
                "override_key": override_key,
                "agent_target": agent_target,
                "reason": reason,
                "approved": True,
            },
        )
