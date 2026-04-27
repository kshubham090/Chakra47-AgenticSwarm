# Community Agent Guide

Welcome to Chakra47-AgenticSwarm. This guide covers everything you need to build, test, and submit a community agent.

---

## Core rule: Code decides. LLM advises.

Every agent must have a **deterministic Python code path** for all known situations. Ollama is only called when your code genuinely cannot classify the input. Agents that default to LLM calls will not be merged.

---

## Quickstart

```bash
git clone https://github.com/kshubham090/Chakra47-AgenticSwarm.git
cd Chakra47-AgenticSwarm
pip install -e .
cp community_agents/template/agent_template.py community_agents/my_agent/agent.py
```

---

## Agent structure

Every agent is one file, one class, under 200 lines. It must extend `BaseAgent` and implement `run()` and `_deterministic_logic()`.

```python
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)


class MyAgent(BaseAgent):
    name = "my_agent"
    description = "One-line description of what this agent does."

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self._threshold: float = cfg.get("threshold", 0.5)

    def run(self, context: AgentContext) -> AgentResult:
        result = self._deterministic_logic(context)
        if result.is_resolved:
            return result
        # Unknown input — fall through to exception (caller may invoke LLM bridge)
        return AgentResult.exception(
            agent=self.name,
            reason=f"Could not classify input: {context.input!r}",
        )

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(
                agent=self.name,
                reason="Input must be a dict",
            )
        value = context.input.get("score")
        if value is None:
            return AgentResult.passed(agent=self.name, payload={"skipped": True})
        if value >= self._threshold:
            return AgentResult.blocked(agent=self.name, reason=f"Score {value} exceeds threshold")
        return AgentResult.passed(agent=self.name, payload={"score": value})
```

### AgentResult outcomes

| Method | Status | When to use |
|---|---|---|
| `AgentResult.passed(agent, payload)` | `PASS` | Input is safe / task complete |
| `AgentResult.blocked(agent, reason)` | `BLOCK` | Input violates a rule — pipeline stops |
| `AgentResult.escalate(agent, reason)` | `ESCALATE` | Needs human review — pipeline continues |
| `AgentResult.exception(agent, reason)` | `EXCEPTION` | Genuinely unclassifiable input |

### AgentContext fields

| Field | Type | Description |
|---|---|---|
| `input` | `Any` | The normalized payload from the Ingester (usually a `dict`) |
| `task_id` | `str` | UUID for the current pipeline run |
| `metadata` | `dict` | Extra data from upstream agents (e.g. `agent_outputs`) |
| `history` | `list[dict]` | Recent result history for trend analysis |

---

## Configurable thresholds

Hardcoded numbers are a code smell. Put tunable values in `rules.yaml` under your agent's section:

```yaml
my_agent:
  threshold: 0.5
```

Load them via `swarm_core.rules.engine.load_config_yaml()`:

```python
from swarm_core.rules.engine import load_config_yaml

cfg = load_config_yaml().get("my_agent", {})
self._threshold = cfg.get("threshold", 0.5)
```

---

## Tests (required)

Tests live in `tests/test_agents/test_my_agent.py`. Two rules apply:

1. **Known inputs must resolve via code** — `result.decision_source == DecisionSource.CODE`
2. **Unknown inputs must return EXCEPTION** — mock the LLM bridge; it must not be called for known inputs

Minimal test skeleton:

```python
from unittest.mock import MagicMock
import pytest
from swarm_core.base import AgentContext, AgentStatus, DecisionSource
from community_agents.my_agent.agent import MyAgent


def test_known_input_resolves_via_code():
    agent = MyAgent()
    result = agent.run(AgentContext(input={"score": 0.2}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE


def test_block_on_threshold_exceeded():
    agent = MyAgent()
    result = agent.run(AgentContext(input={"score": 0.9}))
    assert result.status == AgentStatus.BLOCK


def test_exception_on_non_dict_input():
    agent = MyAgent()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


def test_skips_when_key_missing():
    agent = MyAgent()
    result = agent.run(AgentContext(input={"other_key": 1}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True
```

Run with coverage:

```bash
pytest --cov=community_agents/my_agent tests/test_agents/test_my_agent.py
```

---

## Rules

- One file per agent. Class stays under 200 lines.
- No external API calls — no OpenAI, Anthropic, Google, etc. Ollama only, exception path only.
- Use `from swarm_core.utils import get_logger` — no `print` statements.
- Type hints on all code. Docstrings on all public methods.
- Run `black . && ruff check . && pytest tests/` before opening a PR.

---

## Submitting

1. Branch: `agent/your-agent-name`
2. PR title: `[Agent] AgentName — one-line description`
3. Contact the maintainer on LinkedIn before opening: [linkedin.com/in/shubhamgupta04907](https://linkedin.com/in/shubhamgupta04907)

Maintainers squash commits on merge.
