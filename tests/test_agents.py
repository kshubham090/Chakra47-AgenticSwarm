from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from swarm_core.agents.anomaly_detector import AnomalyDetector
from swarm_core.agents.comms_agent import CommsAgent
from swarm_core.agents.context_analyst import ContextAnalyst
from swarm_core.agents.mission_planner import MissionPlanner
from swarm_core.agents.override_handler import OverrideHandler
from swarm_core.agents.path_planner import PathPlanner
from swarm_core.agents.resource_monitor import ResourceMonitor
from swarm_core.agents.risk_agent import RiskAgent
from swarm_core.agents.rule_validator import RuleValidator
from swarm_core.base import AgentContext, AgentResult, AgentStatus, DecisionSource
from swarm_core.rules.engine import Rule


# ── ResourceMonitor ────────────────────────────────────────────────────────────

def _mock_psutil(cpu: float, mem: float, disk: float):
    return {
        "swarm_core.agents.resource_monitor.psutil.cpu_percent": cpu,
        "swarm_core.agents.resource_monitor.psutil.virtual_memory": lambda: MagicMock(percent=mem),
        "swarm_core.agents.resource_monitor.psutil.disk_usage": lambda _: MagicMock(percent=disk),
    }


def _run_monitor(cpu: float, mem: float, disk: float) -> AgentResult:
    agent = ResourceMonitor()
    with patch("swarm_core.agents.resource_monitor.psutil.cpu_percent", return_value=cpu), \
         patch("swarm_core.agents.resource_monitor.psutil.virtual_memory", return_value=MagicMock(percent=mem)), \
         patch("swarm_core.agents.resource_monitor.psutil.disk_usage", return_value=MagicMock(percent=disk)):
        return agent.run(AgentContext(input={}))


def test_resource_monitor_pass_when_normal():
    result = _run_monitor(cpu=50.0, mem=60.0, disk=40.0)
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE


def test_resource_monitor_escalate_when_elevated():
    result = _run_monitor(cpu=85.0, mem=60.0, disk=40.0)
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.CODE


def test_resource_monitor_block_when_critical():
    result = _run_monitor(cpu=97.0, mem=60.0, disk=40.0)
    assert result.status == AgentStatus.BLOCK
    assert result.decision_source == DecisionSource.CODE


# ── RuleValidator ──────────────────────────────────────────────────────────────

def _make_rules() -> list[Rule]:
    return [
        Rule(id="block_high", condition="risk_score > 0.8", action="BLOCK", priority=1, reason="High risk"),
        Rule(id="escalate_med", condition="risk_score > 0.5", action="ESCALATE", priority=2, reason="Med risk"),
    ]


def test_rule_validator_pass_when_no_violations():
    agent = RuleValidator(rules=_make_rules())
    result = agent.run(AgentContext(input={"risk_score": 0.2}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE


def test_rule_validator_block_when_rule_violated():
    agent = RuleValidator(rules=_make_rules())
    result = agent.run(AgentContext(input={"risk_score": 0.9}))
    assert result.status == AgentStatus.BLOCK
    assert "block_high" in result.reason


def test_rule_validator_escalate_on_warning_rule():
    agent = RuleValidator(rules=_make_rules())
    result = agent.run(AgentContext(input={"risk_score": 0.6}))
    assert result.status == AgentStatus.ESCALATE


def test_rule_validator_exception_on_non_dict():
    agent = RuleValidator(rules=_make_rules())
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


# ── AnomalyDetector ────────────────────────────────────────────────────────────

def test_anomaly_detector_pass_normal_values():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input={"values": [10, 11, 10, 9, 10, 11]}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE
    assert result.payload["anomaly"] is False


def test_anomaly_detector_escalate_on_anomaly():
    agent = AnomalyDetector(config={"z_score_threshold": 2.0, "severe_z_score_threshold": 5.0})
    result = agent.run(AgentContext(input={"values": [10, 10, 10, 10, 10, 50]}))
    assert result.status == AgentStatus.ESCALATE


def test_anomaly_detector_block_on_severe_anomaly():
    # 6 identical values bound max z-score at ~2.04 (= 5√6/6); need ≥11 values for z > 3.0
    agent = AnomalyDetector(config={"z_score_threshold": 2.0, "severe_z_score_threshold": 3.0})
    result = agent.run(AgentContext(input={"values": [10] * 10 + [1000]}))
    assert result.status == AgentStatus.BLOCK


def test_anomaly_detector_exception_too_few_values():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input={"values": [42]}))
    assert result.status == AgentStatus.EXCEPTION


def test_anomaly_detector_skips_when_no_values_key():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input={"risk_score": 0.3}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True


def test_anomaly_detector_pass_zero_variance():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input={"values": [5, 5, 5, 5]}))
    assert result.status == AgentStatus.PASS
    assert result.payload["max_z_score"] == 0.0


# ── RiskAgent ──────────────────────────────────────────────────────────────────

def test_risk_agent_pass_low_score():
    agent = RiskAgent()
    result = agent.run(AgentContext(input={"risk_score": 0.2}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE


def test_risk_agent_escalate_medium_score():
    agent = RiskAgent()
    result = agent.run(AgentContext(input={"risk_score": 0.6}))
    assert result.status == AgentStatus.ESCALATE


def test_risk_agent_block_high_score():
    agent = RiskAgent()
    result = agent.run(AgentContext(input={"risk_score": 0.9}))
    assert result.status == AgentStatus.BLOCK


def test_risk_agent_exception_no_numeric_signals():
    agent = RiskAgent()
    result = agent.run(AgentContext(input={"label": "hello"}))
    assert result.status == AgentStatus.EXCEPTION


# ── ContextAnalyst ─────────────────────────────────────────────────────────────

def test_context_analyst_pass_no_history():
    agent = ContextAnalyst()
    result = agent.run(AgentContext(input={}, history=[]))
    assert result.status == AgentStatus.PASS
    assert result.payload["trend"] == "no_history"


def test_context_analyst_pass_healthy_history():
    agent = ContextAnalyst()
    history = [{"status": "PASS"}] * 10
    result = agent.run(AgentContext(input={}, history=history))
    assert result.status == AgentStatus.PASS


def test_context_analyst_escalate_elevated_failures():
    agent = ContextAnalyst(config={"elevated_failure_rate": 0.4, "critical_failure_rate": 0.7})
    history = [{"status": "BLOCK"}] * 5 + [{"status": "PASS"}] * 5
    result = agent.run(AgentContext(input={}, history=history))
    assert result.status == AgentStatus.ESCALATE


def test_context_analyst_block_critical_failures():
    agent = ContextAnalyst(config={"elevated_failure_rate": 0.4, "critical_failure_rate": 0.7})
    history = [{"status": "BLOCK"}] * 8 + [{"status": "PASS"}] * 2
    result = agent.run(AgentContext(input={}, history=history))
    assert result.status == AgentStatus.BLOCK


# ── MissionPlanner ─────────────────────────────────────────────────────────────

def _make_mission_planner() -> MissionPlanner:
    mock_bridge = MagicMock()
    mock_bridge.classify.return_value = AgentResult.exception(
        agent="mission_planner", reason="LLM fallback test"
    )
    # LLMBridge is imported inside __init__; passing llm_bridge= directly overrides it
    return MissionPlanner(llm_bridge=mock_bridge)


def test_mission_planner_known_type_resolves_via_code():
    planner = _make_mission_planner()
    result = planner.run(AgentContext(input={"mission_type": "patrol"}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE
    assert "steps" in result.payload
    planner._llm_bridge.classify.assert_not_called()


def test_mission_planner_unknown_type_falls_to_llm():
    planner = _make_mission_planner()
    result = planner.run(AgentContext(input={"mission_type": "self_destruct"}))
    planner._llm_bridge.classify.assert_called_once()


def test_mission_planner_missing_key_returns_exception():
    planner = _make_mission_planner()
    result = planner._deterministic_logic(AgentContext(input={}))
    assert result.status == AgentStatus.EXCEPTION
    planner._llm_bridge.classify.assert_not_called()


def test_mission_planner_all_known_types_resolve_via_code():
    planner = _make_mission_planner()
    known = ["patrol", "deliver", "inspect", "report", "standby", "monitor", "scan", "alert"]
    for mission in known:
        result = planner._deterministic_logic(AgentContext(input={"mission_type": mission}))
        assert result.status == AgentStatus.PASS, f"Expected PASS for mission_type={mission!r}"


# ── PathPlanner ────────────────────────────────────────────────────────────────

def test_path_planner_skips_when_no_waypoints_key():
    agent = PathPlanner()
    result = agent.run(AgentContext(input={"risk_score": 0.2}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True


def test_path_planner_valid_two_waypoints():
    agent = PathPlanner()
    result = agent.run(AgentContext(input={"waypoints": [[0, 0], [3, 4]]}))
    assert result.status == AgentStatus.PASS
    assert result.payload["total_distance"] == pytest.approx(5.0)


def test_path_planner_too_few_waypoints_blocked():
    agent = PathPlanner()
    result = agent.run(AgentContext(input={"waypoints": [[0, 0]]}))
    assert result.status == AgentStatus.BLOCK


def test_path_planner_too_many_waypoints_escalated():
    agent = PathPlanner(config={"min_waypoints": 2, "max_waypoints": 3})
    waypoints = [[i, i] for i in range(10)]
    result = agent.run(AgentContext(input={"waypoints": waypoints}))
    assert result.status == AgentStatus.ESCALATE


def test_path_planner_multi_segment_distance():
    agent = PathPlanner()
    # (0,0)→(3,4)=5, (3,4)→(3,4)=0 edge case; use (0,0)→(3,4)→(6,8)=5+5=10
    result = agent.run(AgentContext(input={"waypoints": [[0, 0], [3, 4], [6, 8]]}))
    assert result.status == AgentStatus.PASS
    assert result.payload["total_distance"] == pytest.approx(10.0)


# ── CommsAgent ─────────────────────────────────────────────────────────────────

def test_comms_agent_valid_message_passes():
    agent = CommsAgent()
    result = agent.run(AgentContext(input={"message": "status OK", "target": "orchestrator"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["routed_to"] == "orchestrator"


def test_comms_agent_unknown_target_blocked():
    agent = CommsAgent()
    result = agent.run(AgentContext(input={"message": "hello", "target": "unknown_agent"}))
    assert result.status == AgentStatus.BLOCK


def test_comms_agent_empty_message_blocked():
    agent = CommsAgent()
    result = agent.run(AgentContext(input={"message": "", "target": "orchestrator"}))
    assert result.status == AgentStatus.BLOCK


def test_comms_agent_missing_target_blocked():
    agent = CommsAgent()
    result = agent.run(AgentContext(input={"message": "ping"}))
    assert result.status == AgentStatus.BLOCK


# ── OverrideHandler ────────────────────────────────────────────────────────────

def test_override_handler_valid_key_passes():
    agent = OverrideHandler()
    result = agent.run(AgentContext(input={
        "override_key": "OVERRIDE_ALPHA",
        "reason": "Maintenance window authorized by ops lead",
        "agent_target": "risk_agent",
    }))
    assert result.status == AgentStatus.PASS
    assert result.payload["approved"] is True


def test_override_handler_invalid_key_blocked():
    agent = OverrideHandler()
    result = agent.run(AgentContext(input={
        "override_key": "OVERRIDE_UNKNOWN",
        "reason": "Testing",
    }))
    assert result.status == AgentStatus.BLOCK


def test_override_handler_missing_reason_blocked():
    agent = OverrideHandler()
    result = agent.run(AgentContext(input={"override_key": "OVERRIDE_BETA"}))
    assert result.status == AgentStatus.BLOCK


def test_override_handler_no_key_skips():
    # No override_key means this is not an override request — skip, not BLOCK
    agent = OverrideHandler()
    result = agent.run(AgentContext(input={"reason": "no key provided"}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True


# ── non-dict input edge cases ──────────────────────────────────────────────────

def test_anomaly_detector_exception_non_dict_input():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


def test_anomaly_detector_exception_non_numeric_values():
    agent = AnomalyDetector()
    result = agent.run(AgentContext(input={"values": [1, 2, "not_a_number"]}))
    assert result.status == AgentStatus.EXCEPTION


def test_comms_agent_exception_non_dict_input():
    agent = CommsAgent()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


def test_comms_agent_skips_when_no_message_and_no_mission():
    agent = CommsAgent()
    result = agent.run(AgentContext(input={}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True


def test_mission_planner_exception_non_dict_input():
    planner = _make_mission_planner()
    result = planner._deterministic_logic(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION
    planner._llm_bridge.classify.assert_not_called()


def test_override_handler_exception_non_dict_input():
    agent = OverrideHandler()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


def test_path_planner_exception_non_dict_input():
    agent = PathPlanner()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION


def test_path_planner_exception_waypoints_not_list():
    agent = PathPlanner()
    result = agent.run(AgentContext(input={"waypoints": "not_a_list"}))
    assert result.status == AgentStatus.EXCEPTION


def test_path_planner_exception_invalid_waypoint_format():
    agent = PathPlanner()
    result = agent.run(AgentContext(input={"waypoints": [[0, 0], ["a", "b"]]}))
    assert result.status == AgentStatus.EXCEPTION


def test_resource_monitor_disk_error_uses_fallback():
    agent = ResourceMonitor()
    with patch("swarm_core.agents.resource_monitor.psutil.cpu_percent", return_value=50.0), \
         patch("swarm_core.agents.resource_monitor.psutil.virtual_memory", return_value=MagicMock(percent=60.0)), \
         patch("swarm_core.agents.resource_monitor.psutil.disk_usage", side_effect=PermissionError("no access")):
        result = agent.run(AgentContext(input={}))
    assert result.status == AgentStatus.PASS


def test_risk_agent_exception_non_dict_input():
    agent = RiskAgent()
    result = agent.run(AgentContext(input="not a dict"))
    assert result.status == AgentStatus.EXCEPTION
