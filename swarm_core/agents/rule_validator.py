from __future__ import annotations

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.rules.engine import Rule, _evaluate_condition
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class RuleValidator(BaseAgent):
    """
    Pre-flight validation: runs input against ALL rules and reports every violation.
    Unlike RuleEngine (first-match), RuleValidator exhaustively checks all rules
    so callers get a complete picture before committing to an action.
    Always deterministic — no LLM path.
    """

    name = "rule_validator"
    description = "Validates a proposed action against all symbolic rules, reporting all violations."

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = rules or []

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason=f"RuleValidator expects dict input, got {type(context.input).__name__}",
            )

        blocks = [
            r for r in self._rules
            if r.action.upper() == "BLOCK" and _evaluate_condition(r.condition, context.input)
        ]
        escalations = [
            r for r in self._rules
            if r.action.upper() == "ESCALATE" and _evaluate_condition(r.condition, context.input)
        ]

        if blocks:
            ids = [r.id for r in blocks]
            return AgentResult.blocked(
                agent=self.name,
                reason=f"Violated {len(blocks)} rule(s): {ids}",
            )
        if escalations:
            ids = [r.id for r in escalations]
            return AgentResult.escalate(
                agent=self.name,
                reason=f"Warning: {len(escalations)} rule(s) triggered: {ids}",
            )

        return AgentResult.passed(
            agent=self.name,
            payload={"rules_checked": len(self._rules), "violations": 0},
        )
