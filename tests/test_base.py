from swarm_core.base import AgentContext, AgentResult, AgentStatus, DecisionSource


def test_agent_result_passed_is_resolved():
    result = AgentResult.passed(agent="test_agent", payload={"x": 1})
    assert result.is_resolved is True
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE


def test_agent_result_blocked_is_resolved():
    result = AgentResult.blocked(agent="test_agent", reason="blocked by rule")
    assert result.is_resolved is True
    assert result.status == AgentStatus.BLOCK


def test_agent_result_escalate_not_resolved():
    result = AgentResult.escalate(agent="test_agent", reason="needs human")
    assert result.is_resolved is False
    assert result.status == AgentStatus.ESCALATE


def test_agent_result_exception_not_resolved():
    result = AgentResult.exception(agent="test_agent", reason="unknown pattern")
    assert result.is_resolved is False
    assert result.status == AgentStatus.EXCEPTION


def test_agent_context_auto_task_id():
    ctx1 = AgentContext(input="hello")
    ctx2 = AgentContext(input="hello")
    assert ctx1.task_id != ctx2.task_id


def test_agent_context_custom_task_id():
    ctx = AgentContext(input="hello", task_id="fixed-id")
    assert ctx.task_id == "fixed-id"
