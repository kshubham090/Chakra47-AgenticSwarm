# Contributing to Agentic Swarm

First off — thank you for being here. Every contribution moves this framework forward.

This document covers everything you need to know to contribute effectively.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [The Golden Rule](#the-golden-rule)
- [How to Contribute](#how-to-contribute)
- [Building a New Agent](#building-a-new-agent)
- [Improving Existing Agents](#improving-existing-agents)
- [Architecture Rules](#architecture-rules)
- [Pull Request Process](#pull-request-process)
- [Code Standards](#code-standards)
- [Testing Requirements](#testing-requirements)
- [Getting Help](#getting-help)

---

## Code of Conduct

Be respectful. Be direct. Focus on the work.

We welcome contributors from all backgrounds. What matters here is your code and your ideas — not who you are. Harassment, discrimination, or gatekeeping of any kind will result in immediate removal from the project.

---

## The Golden Rule

> **Code decides. LLM advises.**

This is the single most important principle in Agentic Swarm. Before writing any agent logic, internalize this:

- Every agent must have a **deterministic Python code path** for known situations
- The local LLM (Ollama) is called **only** when the exception classifier cannot match input to any known pattern
- An agent that defaults to LLM calls will not be merged — no exceptions

This is not about distrust of LLMs. It's about building systems that are fast, predictable, auditable, and work fully offline.

---

## How to Contribute

### Types of contributions we welcome

**High priority:**
- New specialist agents in `community_agents/`
- Tests for existing agents
- Improvements to the rule engine (`rules.yaml` patterns, exception classifier)
- Bug fixes with reproduction steps

**Also welcome:**
- Documentation improvements
- Architecture discussions (open an Issue first)
- Performance optimizations

**Not accepted:**
- Agents that call LLMs as the primary decision path
- Dependencies on cloud APIs — everything must work offline
- Agents without tests
- Breaking changes to the `BaseAgent` interface without prior discussion in an Issue

---

## Building a New Agent

This is the most impactful way to contribute. Here's the full process:

### Step 1 — Check what's needed

Look at the open Issues tagged `agent-request`. If your agent idea isn't listed, open an Issue first describing what it does and why it belongs in the swarm. Wait for maintainer acknowledgment before building.

### Step 2 — Copy the template

```bash
cp -r community_agents/template community_agents/your_agent_name
```

Rename `agent_template.py` to `your_agent_name.py`.

### Step 3 — Implement the interface

Every agent must extend `BaseAgent` and implement `run()`:

```python
from swarm_core.base import BaseAgent, AgentContext, AgentResult

class YourAgent(BaseAgent):
    name = "your_agent"
    description = "One line: what this agent does and when it activates"

    def run(self, context: AgentContext) -> AgentResult:
        # ALWAYS try deterministic logic first
        result = self._deterministic_logic(context)
        if result.is_resolved:
            return result

        # Only raise exception if truly unclassifiable
        return AgentResult.exception(
            reason=f"Could not classify input: {context.input}",
            agent=self.name
        )

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        # Your code-first decision logic
        # Use if/elif/else, thresholds, rule lookups
        # Do NOT call Ollama here — that's handled by the LLM bridge
        ...
```

### Step 4 — Write your rules (if applicable)

If your agent makes decisions based on configurable thresholds or conditions, add them to `rules.yaml` instead of hardcoding:

```yaml
# rules.yaml
your_agent:
  rules:
    - condition: "value < 1.5"
      action: "BLOCK"
      priority: 1
    - condition: "value < 3.0"
      action: "WARN"
      priority: 2
```

### Step 5 — Write tests

No tests = no merge. See [Testing Requirements](#testing-requirements).

### Step 6 — Open a Pull Request

Follow the [Pull Request Process](#pull-request-process) below.

---

## Improving Existing Agents

If you want to improve a core agent in `swarm_core/agents/`:

1. Open an Issue describing the problem and your proposed fix
2. Wait for a maintainer to confirm it's the right approach
3. Make the change — keep it focused and minimal
4. Update or add tests
5. Open a PR referencing the Issue

Do not refactor working code without prior discussion. Build forward, not sideways.

---

## Architecture Rules

These are non-negotiable. PRs that violate these will be closed.

**Layer integrity:** Do not bypass layers. Layer 4 agents must not call Layer 1 directly — data flows through the orchestrator.

**Agent size:** Each agent class must stay under 200 lines. If it's growing beyond that, it's doing too much — split it.

**No cloud dependencies:** Zero calls to OpenAI, Anthropic, Google, or any external API. Everything runs locally. Ollama only, and only on the exception path.

**Audit Agent is sacred:** `AuditAgent` must never call an LLM under any circumstances. Logging must be 100% deterministic and tamper-evident. Do not modify AuditAgent without a maintainer explicitly approving.

**One file per agent:** Each agent lives in its own file. No multi-agent files.

---

## Pull Request Process

1. **Fork** the repo and create a branch: `git checkout -b agent/your-agent-name` or `fix/what-youre-fixing`

2. **Build and test locally:**
   ```bash
   pip install -e .
   pytest tests/
   ```

3. **Open a PR** against the `main` branch with:
   - A clear title: `[Agent] YourAgentName — one line description` or `[Fix] what was broken`
   - Description covering: what it does, why it's needed, how you tested it
   - Reference to the Issue it addresses: `Closes #123`

4. **PR checklist** — your PR must satisfy all of these:
   - [ ] Extends `BaseAgent` and implements `run()` correctly
   - [ ] Has a deterministic code path for all known cases
   - [ ] LLM is only called via `AgentResult.exception()` — never directly
   - [ ] Tests written and passing (`pytest tests/`)
   - [ ] No external API dependencies
   - [ ] Agent is under 200 lines
   - [ ] `name` and `description` fields set on the class
   - [ ] Added to `community_agents/` not `swarm_core/agents/` (core agents are maintainer-managed)

5. **Review:** A maintainer will review within 5 business days. Expect feedback. We review for architecture compliance first, then correctness.

6. **Merge:** Once approved, a maintainer merges. We squash commits on merge to keep history clean.

---

## Code Standards

- **Python 3.10+** — use type hints throughout
- **Black** for formatting: `black .`
- **Ruff** for linting: `ruff check .`
- **Docstrings** on every public method — one line minimum
- **No print statements** — use the logger: `from swarm_core.utils import logger`
- **No `TODO` comments in merged code** — open an Issue instead
- **Imports:** stdlib → third party → swarm_core (alphabetical within groups)

Run before every commit:
```bash
black .
ruff check .
pytest tests/
```

---

## Testing Requirements

Every agent contribution must include:

**Unit tests** — test the deterministic logic path:
```python
# tests/test_agents/test_your_agent.py
from swarm_core.base import AgentContext
from community_agents.your_agent_name.your_agent_name import YourAgent

def test_known_case_resolves_without_llm():
    agent = YourAgent()
    ctx = AgentContext(input={"value": 1.0}, config={})
    result = agent.run(ctx)
    assert result.is_resolved
    assert result.source == "code"  # Must not be "llm"
    assert result.action == "BLOCK"

def test_unknown_case_raises_exception():
    agent = YourAgent()
    ctx = AgentContext(input={"value": None, "unknown_field": True}, config={})
    result = agent.run(ctx)
    assert result.is_exception
    assert result.source == "exception"
```

**What we test for:**
- Known inputs resolve via code (never via LLM in tests — mock the LLM bridge)
- Unknown inputs correctly raise an exception result
- Edge cases at threshold boundaries
- Agent returns correct `AgentResult` structure

**Coverage:** Aim for 80%+ on your agent file. Run: `pytest --cov=community_agents/your_agent_name`

---

## Getting Help

- **Questions about architecture:** Open a GitHub Discussion
- **Bug reports:** Open an Issue with reproduction steps
- **Agent ideas:** Open an Issue tagged `agent-request`

---

## Recognition

Contributors are listed in the repo's [Contributors graph](https://github.com/kshubham090/Chakra47-AgenticSwarm/graphs/contributors). Significant contributions will be called out in release notes.

If you build something that gets merged into `swarm_core/agents/` as a core agent — that's a big deal. That means your code is running inside every deployment of this framework.

---

*Agentic Swarm — CONTRIBUTING.md*
