from community_agents.sensor_fusion.sensor_fusion_agent import SensorFusionAgent
from swarm_core.base import AgentContext, AgentStatus, DecisionSource


def _ctx(input_data) -> AgentContext:
    return AgentContext(input=input_data)


# ── passing cases ─────────────────────────────────────────────────────────────


def test_sensors_agree_passes():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {"temp": 70.0, "pressure": 72.0, "humidity": 71.0}}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE
    assert "fused_mean" in result.payload
    assert result.payload["sensor_count"] == 3


def test_fused_mean_is_correct():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {"a": 10.0, "b": 20.0, "c": 30.0}}))
    assert result.status == AgentStatus.PASS
    assert result.payload["fused_mean"] == 20.0


def test_single_sensor_passes():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {"temperature": 55.0}}))
    assert result.status == AgentStatus.PASS
    assert result.payload["fused_mean"] == 55.0
    assert result.payload["max_deviation"] == 0.0
    assert result.payload["sensor_count"] == 1


def test_required_sensor_present_passes():
    agent = SensorFusionAgent()
    result = agent.run(
        _ctx({"sensors": {"temperature": 70.0, "humidity": 68.0}, "required": ["temperature"]})
    )
    assert result.status == AgentStatus.PASS


# ── escalation cases ──────────────────────────────────────────────────────────


def test_conflict_threshold_exceeded_escalates():
    agent = SensorFusionAgent(config={"conflict_threshold": 5.0, "outlier_threshold": 50.0})
    # mean=100, max_deviation=10 > conflict_threshold=5
    result = agent.run(_ctx({"sensors": {"a": 100.0, "b": 100.0, "c": 110.0}}))
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.CODE


def test_outlier_threshold_exceeded_escalates():
    agent = SensorFusionAgent(config={"conflict_threshold": 5.0, "outlier_threshold": 10.0})
    result = agent.run(_ctx({"sensors": {"a": 50.0, "b": 51.0, "c": 75.0}}))
    assert result.status == AgentStatus.ESCALATE
    assert "outlier" in result.reason.lower()


def test_default_thresholds_escalate_on_large_deviation():
    agent = SensorFusionAgent()
    # mean≈116.7, max_deviation≈33.3 > default outlier_threshold of 20
    result = agent.run(_ctx({"sensors": {"x": 100.0, "y": 100.0, "z": 150.0}}))
    assert result.status == AgentStatus.ESCALATE


# ── blocking cases ────────────────────────────────────────────────────────────


def test_missing_required_sensor_blocks():
    agent = SensorFusionAgent()
    result = agent.run(
        _ctx({"sensors": {"humidity": 55.0}, "required": ["temperature"]})
    )
    assert result.status == AgentStatus.BLOCK
    assert result.decision_source == DecisionSource.CODE
    assert "temperature" in result.reason


def test_multiple_missing_required_sensors_blocks():
    agent = SensorFusionAgent()
    result = agent.run(
        _ctx({"sensors": {"humidity": 55.0}, "required": ["temperature", "pressure"]})
    )
    assert result.status == AgentStatus.BLOCK
    assert "temperature" in result.reason
    assert "pressure" in result.reason


# ── exception cases ───────────────────────────────────────────────────────────


def test_non_dict_input_is_exception():
    agent = SensorFusionAgent()
    result = agent.run(_ctx("bare string"))
    assert result.status == AgentStatus.EXCEPTION
    assert result.decision_source == DecisionSource.CODE


def test_missing_sensors_key_is_exception():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"other_key": "value"}))
    assert result.status == AgentStatus.EXCEPTION


def test_empty_sensors_dict_is_exception():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {}}))
    assert result.status == AgentStatus.EXCEPTION


def test_non_numeric_sensor_value_is_exception():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {"temperature": "hot", "pressure": 101.3}}))
    assert result.status == AgentStatus.EXCEPTION


def test_sensors_value_not_dict_is_exception():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": [1, 2, 3]}))
    assert result.status == AgentStatus.EXCEPTION


# ── custom config ─────────────────────────────────────────────────────────────


def test_custom_conflict_threshold_tighter():
    agent = SensorFusionAgent(config={"conflict_threshold": 1.0, "outlier_threshold": 50.0})
    # mean=11.5, max_deviation=1.5 > conflict_threshold=1.0
    result = agent.run(_ctx({"sensors": {"a": 10.0, "b": 13.0}}))
    assert result.status == AgentStatus.ESCALATE


def test_custom_conflict_threshold_wider():
    agent = SensorFusionAgent(config={"conflict_threshold": 100.0, "outlier_threshold": 200.0})
    result = agent.run(_ctx({"sensors": {"a": 10.0, "b": 80.0}}))
    assert result.status == AgentStatus.PASS


def test_payload_contains_all_fields_on_pass():
    agent = SensorFusionAgent()
    result = agent.run(_ctx({"sensors": {"a": 10.0, "b": 11.0, "c": 10.5}}))
    assert result.status == AgentStatus.PASS
    for field in ("fused_mean", "max_deviation", "sensor_count", "sensors"):
        assert field in result.payload
