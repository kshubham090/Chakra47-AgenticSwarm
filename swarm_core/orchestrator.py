from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swarm_core.agents import (
    AnomalyDetector,
    CommsAgent,
    ContextAnalyst,
    MissionPlanner,
    OverrideHandler,
    PathPlanner,
    ResourceMonitor,
    RiskAgent,
    RuleValidator,
)
from swarm_core.audit.audit_agent import AuditAgent
from swarm_core.audit.chain import AuditChain
from swarm_core.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from swarm_core.perception.ingester import Ingester
from swarm_core.rules.engine import RuleEngine, load_config_yaml, load_rules_yaml
from swarm_core.utils import get_logger

logger = get_logger(__name__)


@dataclass
class SwarmResult:
    task_id: str
    final_status: AgentStatus
    agent_results: list[AgentResult] = field(default_factory=list)
    blocked_by: str | None = None
    escalations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.final_status == AgentStatus.PASS

    @property
    def blocked(self) -> bool:
        return self.final_status == AgentStatus.BLOCK


class Orchestrator:
    """
    Wires all 4 layers: Perception → Rules → Agents → Audit.
    AuditAgent is called after every agent decision — without exception.
    Agent outputs are stored in context.metadata["agent_outputs"] so downstream
    agents can consume upstream results without Layer 4 calling Layer 1 directly.
    """

    def __init__(
        self,
        audit_chain: AuditChain,
        agents: list[BaseAgent] | None = None,
        rule_engine: RuleEngine | None = None,
        ingester: Ingester | None = None,
        rules_path: Path | str | None = None,
    ) -> None:
        self._ingester: Ingester = ingester or Ingester()
        self._rule_engine: RuleEngine = rule_engine or RuleEngine(rules_path=rules_path)
        self._audit_agent: AuditAgent = AuditAgent(chain=audit_chain)
        self._pipeline: list[BaseAgent] = (
            agents if agents is not None else _default_pipeline(rules_path)
        )

    def run(self, raw: Any, task_id: str | None = None) -> SwarmResult:
        """Ingest raw input, gate through rules, run agent pipeline, audit every step."""
        context = self._ingester.ingest(raw, task_id=task_id)
        context.metadata.setdefault("agent_outputs", {})
        logger.info("orchestrator: starting task %s", context.task_id)

        rule_result = self._rule_engine.run(context)
        self._record(context, rule_result)
        self._audit(context, rule_result)

        if rule_result.status == AgentStatus.BLOCK:
            logger.warning("orchestrator: blocked by rule engine — %s", rule_result.reason)
            return SwarmResult(
                task_id=context.task_id,
                final_status=AgentStatus.BLOCK,
                agent_results=[rule_result],
                blocked_by=rule_result.agent,
            )

        escalations: list[str] = []
        if rule_result.status == AgentStatus.ESCALATE:
            escalations.append(rule_result.agent)
            context.metadata["escalated"] = True
            logger.warning("orchestrator: escalation from rule engine — %s", rule_result.reason)

        results: list[AgentResult] = [rule_result]

        for agent in self._pipeline:
            result = agent.run(context)
            self._record(context, result)
            self._audit(context, result)
            results.append(result)
            context.history.append({"agent": result.agent, "status": result.status.value})

            if result.status == AgentStatus.BLOCK:
                logger.warning(
                    "orchestrator: pipeline blocked by %s — %s", result.agent, result.reason
                )
                return SwarmResult(
                    task_id=context.task_id,
                    final_status=AgentStatus.BLOCK,
                    agent_results=results,
                    blocked_by=result.agent,
                    escalations=escalations,
                )

            if result.status == AgentStatus.ESCALATE:
                escalations.append(result.agent)

        final_status = AgentStatus.ESCALATE if escalations else AgentStatus.PASS
        logger.info("orchestrator: task %s complete — %s", context.task_id, final_status.value)
        return SwarmResult(
            task_id=context.task_id,
            final_status=final_status,
            agent_results=results,
            escalations=escalations,
        )

    def _record(self, context: AgentContext, result: AgentResult) -> None:
        """Store non-skipped agent payloads so downstream agents can read upstream outputs."""
        if result.payload and not result.payload.get("skipped"):
            context.metadata["agent_outputs"][result.agent] = result.payload

    def _audit(self, context: AgentContext, result: AgentResult) -> None:
        audit_ctx = AgentContext(
            input=context.input,
            task_id=context.task_id,
            metadata={**context.metadata, "result_to_audit": result},
        )
        self._audit_agent.run(audit_ctx)


def _default_pipeline(rules_path: Path | str | None = None) -> list[BaseAgent]:
    """Build the default 9-agent pipeline, wiring rules.yaml config into every agent."""
    cfg = load_config_yaml(rules_path)
    rules = load_rules_yaml(rules_path)
    return [
        ResourceMonitor(config=cfg.get("resource_monitor")),
        RuleValidator(rules=rules),
        AnomalyDetector(config=cfg.get("anomaly_detector")),
        RiskAgent(config=cfg.get("risk_agent")),
        ContextAnalyst(config=cfg.get("context_analyst")),
        MissionPlanner(),
        PathPlanner(config=cfg.get("path_planner")),
        CommsAgent(valid_targets=set(cfg.get("comms_agent", {}).get("valid_targets", []))),
        OverrideHandler(valid_keys=set(cfg.get("override_handler", {}).get("valid_keys", []))),
    ]
