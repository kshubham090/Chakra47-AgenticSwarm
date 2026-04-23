<div align="center">

# ⚡Chakra47's Agentic Swarm

**An open-source framework for building governed autonomous agent swarms.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Contributors](https://img.shields.io/github/contributors/kshubham090/Chakra47-AgenticSwarm)](https://github.com/kshubham090/Chakra47-AgenticSwarm/graphs/contributors)
[![Issues](https://img.shields.io/github/issues/kshubham090/Chakra47-AgenticSwarm)](https://github.com/kshubham090/Chakra47-AgenticSwarm/issues)

[Architecture](#architecture) · [Contributing](./CONTRIBUTING.md) · [Roadmap](#roadmap)

</div>

---

## What is Chakra47's Agentic Swarm?

**Chakra47's Agentic Swarm** is a general-purpose framework for building governed, multi-agent systems — where a central orchestrator coordinates specialist agents to perceive, reason, decide, and act.

Use it to build anything that needs structured, auditable, multi-agent behavior: SaaS automation pipelines, PaaS orchestration layers, decision engines, monitoring systems, or any domain where deterministic reliability matters more than raw LLM flexibility.

> **The mission of this repo:** Build the best open-source agentic swarm framework, governed by neuro-symbolic AI, where code is the default and LLMs are the exception.

---

## Why Chakra47's Agentic Swarm is Different

Most agentic frameworks hand all decisions to an LLM. This framework flips that — code runs everything it can, and the LLM handles only what code genuinely cannot.

| | Typical Agent Frameworks | Agentic Swarm |
|---|---|---|
| Decision making | LLM-first | Code-first, LLM on exceptions only |
| Safety | Prompt-based guardrails | Symbolic rule engine — hard gates |
| Auditability | Logs | Cryptographic hash-chain audit trail |
| Real-time | No | Yes — WebSocket live state |
| Offline capable | No | Yes — LLM optional |

---

## Architecture

Agentic Swarm follows a strict 4-layer architecture. All contributions must respect this structure.

```
┌─────────────────────────────────────────────────────────┐
│                   AGENTIC SWARM CORE                    │
│                                                         │
│  LAYER 1   PERCEPTION                                   │
│            Input ingestion from any source              │
│            Structured context output                    │
│                          ↓                              │
│  LAYER 2   SYMBOLIC RULE ENGINE                         │
│            Deterministic decision trees (code-first)    │
│            Exception classifier                         │
│            Local LLM bridge — Ollama (exceptions only)  │
│            Gate result: PASS · BLOCK · ESCALATE         │
│                          ↓                              │
│  LAYER 3   CRYPTOGRAPHIC AUDIT CHAIN                    │
│            SHA-256 hash-chain on every decision         │
│            Decision source tagged: code vs LLM          │
│            Tamper-evident · fully traceable             │
│                          ↓                              │
│  LAYER 4   AGENTIC ORCHESTRATOR + SWARM                 │
│            Specialist agent classes (Python)            │
│            Code-first · LLM only on exception path      │
│            Human-in-the-loop approval flow              │
└─────────────────────────────────────────────────────────┘
```

### The Golden Rule

> **Code decides. LLM advises.**

Every agent must have a deterministic code path for known situations. The local LLM (via Ollama) is called **only** when the exception classifier cannot match the input to any known pattern. This keeps the system fast, predictable, auditable, and offline-capable.

---

## The 10 Core Agents

These are the baseline agents. Each is a Python class with a `run(context) -> AgentResult` interface.

| Agent | Responsibility | LLM Fallback Trigger |
|---|---|---|
| `MissionPlanner` | Parse user prompt → subtask list | Unknown task type |
| `ContextAnalyst` | Interpret Layer 1 input and build context | Unknown input pattern |
| `RiskAgent` | Assess risk and conflict in planned actions | Ambiguous risk signal |
| `PathPlanner` | Sequence and route task execution | Fully blocked, no valid path |
| `AnomalyDetector` | Detect deviations from expected state | Unknown anomaly pattern |
| `RuleValidator` | Gate check against `rules.yaml` rule set | Action in grey zone |
| `CommsAgent` | Format status updates → user/interface | Complex situation explanation |
| `ResourceMonitor` | CPU, memory, quota threshold checks | Unusual resource drain |
| `AuditAgent` | Hash-chain logging — **no LLM, ever** | Never |
| `OverrideHandler` | Process mid-run user commands | Ambiguous user intervention |

### Agent Interface Contract

Every agent — core or community-contributed — must implement this interface:

```python
from swarm_core.base import BaseAgent, AgentContext, AgentResult

class MyAgent(BaseAgent):
    name = "my_agent"
    description = "One line description of what this agent does"

    def run(self, context: AgentContext) -> AgentResult:
        # 1. Try deterministic code path first
        result = self._deterministic_logic(context)
        if result.is_resolved:
            return result

        # 2. Only if unresolved — raise exception for LLM bridge
        return AgentResult.exception(
            reason="Could not classify: {context.input}",
            agent=self.name
        )

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        # Your code-first logic here
        ...
```

---

## Project Structure

```
AgenticSwarm/
├── swarm_core/
│   ├── base.py              # BaseAgent, AgentContext, AgentResult
│   ├── orchestrator.py      # Main swarm orchestrator
│   ├── perception/          # Layer 1 — input ingestion
│   ├── rules/               # Layer 2 — rule engine + LLM bridge
│   │   └── rules.yaml       # Declarative rule definitions
│   ├── audit/               # Layer 3 — hash-chain logger
│   └── agents/              # Layer 4 — the 10 core agents
├── community_agents/        # ← Community contributed agents live here
│   └── template/
│       └── agent_template.py
├── tests/
│   ├── test_agents/
│   └── test_orchestrator/
├── docs/
│   └── architecture.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally
- `llama3.2` model pulled: `ollama pull llama3.2` or any other suitable models

### Install

```bash
git clone https://github.com/kshubham090/Chakra47-AgenticSwarm.git
cd Chakra47-AgenticSwarm
pip install -e .
```

### Run the swarm

```bash
# Run a mission via CLI
swarm run "monitor all inputs and flag anomalies"

# Run tests
pytest tests/
```

---

## How to Contribute

We welcome contributions of all kinds — new agents, improvements to existing agents, bug fixes, docs, and tests.

**Read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR.**

The fastest way to contribute is to **build a new specialist agent** in `community_agents/`. Copy the template, implement your logic, add tests, and open a PR.

Some agents we'd love to see built:

- `SwarmCoordinator` — multi-agent task distribution
- `SensorFusionAgent` — merge data from multiple input types
- `ThreatAssessmentAgent` — classify risk levels from context output
- `EnergyOptimizer` — resource-aware task sequencing
- `CommunicationRelay` — agent-to-agent message routing
- `MapBuilder` — build state maps from perception data in real time

---

## Roadmap

| Milestone | Status |
|---|---|
| Core agent base classes + orchestrator | 🔄 In progress |
| 10 baseline agents implemented | 🔄 In progress |
| Rule engine with `rules.yaml` loader | 🔄 In progress |
| SHA-256 audit chain | 🔄 In progress |
| Community agent template + docs | 📋 Planned |
| Web dashboard (optional) | 📋 Planned |
| Plugin SDK | 🔭 Future |

---

## License

Apache License 2.0 — see [LICENSE](./LICENSE) for full text.

You are free to use, modify, and distribute this code — including commercially — as long as you include attribution and the original license.

---

<div align="center">
<sub>If this project helped you, give it a ⭐ — it helps more people find it.</sub>
</div>
