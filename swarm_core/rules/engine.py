from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from swarm_core.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from swarm_core.rules.llm_bridge import LLMBridge
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "rules.yaml"

_OPS: dict[str, Any] = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

_CONDITION_RE = re.compile(r"^(\w+)\s*(>=|<=|==|!=|>|<)\s*(.+)$")


@dataclass(frozen=True)
class Rule:
    id: str
    condition: str
    action: str
    priority: int
    reason: str


def _parse_literal(raw: str) -> int | float | str:
    """Safely parse a rule literal — tries int, then float, then bare string."""
    stripped = raw.strip().strip("\"'")
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _evaluate_condition(condition: str, values: dict[str, Any]) -> bool:
    """Evaluate a single 'field op literal' condition. Never uses eval()."""
    m = _CONDITION_RE.match(condition.strip())
    if not m:
        return False
    field, op, raw_literal = m.group(1), m.group(2), m.group(3)
    if field not in values:
        return False
    actual = values[field]
    expected = _parse_literal(raw_literal)
    try:
        return bool(_OPS[op](actual, expected))
    except TypeError:
        return False


class RuleEngine(BaseAgent):
    """
    Layer 2 — Symbolic Rule Engine.
    Evaluates rules from rules.yaml deterministically.
    LLM bridge is called only when no rule matches (exception path).
    """

    name = "rule_engine"
    description = "Evaluates symbolic rules from rules.yaml; calls LLM only on exception path."

    def __init__(
        self,
        rules_path: Path | str | None = None,
        llm_bridge: LLMBridge | None = None,
    ) -> None:
        self._rules: list[Rule] = self._load_rules(Path(rules_path or _DEFAULT_RULES_PATH))
        self._llm_bridge: LLMBridge = llm_bridge if llm_bridge is not None else LLMBridge()

    def run(self, context: AgentContext) -> AgentResult:
        result = self._deterministic_logic(context)
        if result.status != AgentStatus.EXCEPTION:
            return result
        logger.info("rule_engine: no rule matched — delegating to LLM bridge")
        return self._llm_bridge.classify(context, agent_name=self.name)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason=f"Rule engine expects dict input, got {type(context.input).__name__}",
            )
        matched = self._match_rules(context.input)
        if matched is None:
            return AgentResult.exception(
                agent=self.name,
                reason=f"No rule matched input keys: {list(context.input.keys())}",
            )
        return self._apply_rule(matched)

    def _match_rules(self, values: dict[str, Any]) -> Rule | None:
        for rule in sorted(self._rules, key=lambda r: r.priority):
            if _evaluate_condition(rule.condition, values):
                logger.debug("rule_engine: matched rule '%s'", rule.id)
                return rule
        return None

    def _apply_rule(self, rule: Rule) -> AgentResult:
        action = rule.action.upper()
        if action == "BLOCK":
            return AgentResult.blocked(agent=self.name, reason=rule.reason)
        if action == "ESCALATE":
            return AgentResult.escalate(agent=self.name, reason=rule.reason)
        return AgentResult.passed(agent=self.name, payload={"matched_rule": rule.id})

    def _load_rules(self, path: Path) -> list[Rule]:
        if not path.exists():
            logger.warning("rules.yaml not found at %s — engine will always use LLM bridge", path)
            return []
        with path.open() as f:
            data = yaml.safe_load(f)
        raw_rules: list[dict[str, Any]] = data.get("rule_engine", {}).get("rules", [])
        rules = [
            Rule(
                id=r["id"],
                condition=r["condition"],
                action=r["action"],
                priority=r.get("priority", 99),
                reason=r.get("reason", ""),
            )
            for r in raw_rules
        ]
        logger.info("rule_engine: loaded %d rules from %s", len(rules), path)
        return rules
