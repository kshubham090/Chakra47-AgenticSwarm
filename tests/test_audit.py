from unittest.mock import MagicMock, patch
import pytest

from swarm_core.audit.chain import AuditChain, _sha256, _hash_input
from swarm_core.audit.audit_agent import AuditAgent
from swarm_core.base import AgentContext, AgentResult, AgentStatus, DecisionSource


# ── chain unit tests (Supabase mocked) ────────────────────────────────────────

def _make_chain(rows: list[dict] | None = None) -> AuditChain:
    """Return an AuditChain with a fully mocked Supabase client."""
    mock_client = MagicMock()
    last_hash_response = MagicMock()
    last_hash_response.data = rows or []
    (
        mock_client.table.return_value
        .select.return_value
        .order.return_value
        .limit.return_value
        .execute.return_value
    ) = last_hash_response

    with patch("swarm_core.audit.chain.create_client", return_value=mock_client):
        with patch("swarm_core.audit.chain.SUPABASE_URL", "http://fake"):
            with patch("swarm_core.audit.chain.SUPABASE_KEY", "fake-key"):
                chain = AuditChain()

    chain._client = mock_client
    return chain


def test_genesis_hash_when_no_rows():
    chain = _make_chain(rows=[])
    assert chain._last_hash == AuditChain._GENESIS_HASH


def test_log_produces_entry(monkeypatch):
    chain = _make_chain()
    insert_mock = MagicMock()
    chain._client.table.return_value.insert.return_value.execute = insert_mock

    entry = chain.log(
        task_id="task-1",
        agent="test_agent",
        status="PASS",
        decision_source="code",
        raw_input="hello world",
        reason="all good",
    )

    assert entry.task_id == "task-1"
    assert entry.agent == "test_agent"
    assert entry.prev_hash == AuditChain._GENESIS_HASH
    assert len(entry.block_hash) == 64
    assert chain._last_hash == entry.block_hash


def test_chained_hashes_link_correctly():
    chain = _make_chain()
    chain._client.table.return_value.insert.return_value.execute = MagicMock()

    entry1 = chain.log("t1", "agent_a", "PASS", "code", "input_a")
    entry2 = chain.log("t1", "agent_b", "PASS", "code", "input_b")

    assert entry2.prev_hash == entry1.block_hash


def test_sha256_is_deterministic():
    data = {"a": 1, "b": "hello"}
    assert _sha256(data) == _sha256(data)


def test_hash_input_is_string_stable():
    h1 = _hash_input("test input")
    h2 = _hash_input("test input")
    assert h1 == h2 and len(h1) == 64


# ── AuditAgent tests ───────────────────────────────────────────────────────────

def _make_audit_agent() -> tuple[AuditAgent, MagicMock]:
    mock_chain = MagicMock(spec=AuditChain)
    mock_entry = MagicMock()
    mock_entry.block_hash = "abc123"
    mock_entry.id = "entry-uuid"
    mock_chain.log.return_value = mock_entry
    return AuditAgent(chain=mock_chain), mock_chain


def test_audit_agent_logs_result_to_chain():
    agent, mock_chain = _make_audit_agent()
    result_to_audit = AgentResult.passed(agent="mission_planner", payload={"x": 1})
    context = AgentContext(input="test", metadata={"result_to_audit": result_to_audit})

    outcome = agent.run(context)

    assert outcome.status == AgentStatus.PASS
    assert outcome.agent == "audit_agent"
    mock_chain.log.assert_called_once()


def test_audit_agent_blocks_if_no_result_to_audit():
    agent, mock_chain = _make_audit_agent()
    context = AgentContext(input="test")

    outcome = agent.run(context)

    assert outcome.status == AgentStatus.BLOCK
    mock_chain.log.assert_not_called()


def test_audit_agent_never_calls_llm():
    agent, _ = _make_audit_agent()
    # AuditAgent must not have an LLM path — _deterministic_logic always resolves
    context = AgentContext(input="x", metadata={"result_to_audit": AgentResult.passed("a")})
    result = agent._deterministic_logic(context)
    assert result.is_resolved
    assert result.decision_source == DecisionSource.CODE
