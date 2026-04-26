from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from swarm_core.base import AgentContext, AgentResult, AgentStatus, DecisionSource
from swarm_core.rules.engine import RuleEngine, _evaluate_condition, _parse_literal
from swarm_core.rules.llm_bridge import LLMBridge


# ── condition evaluator ────────────────────────────────────────────────────────

def test_evaluate_numeric_gt_true():
    assert _evaluate_condition("risk_score > 0.8", {"risk_score": 0.9}) is True


def test_evaluate_numeric_gt_false():
    assert _evaluate_condition("risk_score > 0.8", {"risk_score": 0.5}) is False


def test_evaluate_numeric_lte():
    assert _evaluate_condition("risk_score <= 0.5", {"risk_score": 0.5}) is True


def test_evaluate_string_equality():
    assert _evaluate_condition("action == delete", {"action": "delete"}) is True


def test_evaluate_string_inequality():
    assert _evaluate_condition("action != delete", {"action": "read"}) is True


def test_evaluate_missing_field_returns_false():
    assert _evaluate_condition("risk_score > 0.8", {"other_key": 1.0}) is False


def test_evaluate_malformed_condition_returns_false():
    assert _evaluate_condition("not a valid condition!!!", {"x": 1}) is False


# ── rule engine helpers ────────────────────────────────────────────────────────

def _make_engine(extra_rules: list[dict] | None = None) -> RuleEngine:
    """Build a RuleEngine from a temporary rules.yaml with a mocked LLM bridge."""
    # NOTE: must use `is not None` — `[] or defaults` would silently load default rules
    rules = extra_rules if extra_rules is not None else [
        {"id": "block_high", "condition": "risk_score > 0.8", "action": "BLOCK", "priority": 1, "reason": "High risk"},
        {"id": "escalate_med", "condition": "risk_score > 0.5", "action": "ESCALATE", "priority": 2, "reason": "Med risk"},
        {"id": "pass_low", "condition": "risk_score <= 0.5", "action": "PASS", "priority": 10, "reason": "Low risk"},
    ]
    data = {"rule_engine": {"rules": rules}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        tmp_path = f.name

    mock_bridge = MagicMock()
    engine = RuleEngine(rules_path=tmp_path, llm_bridge=mock_bridge)
    os.unlink(tmp_path)
    return engine


# ── rule engine tests ──────────────────────────────────────────────────────────

def test_block_rule_resolves_via_code():
    engine = _make_engine()
    result = engine.run(AgentContext(input={"risk_score": 0.9}))
    assert result.status == AgentStatus.BLOCK
    assert result.decision_source == DecisionSource.CODE
    engine._llm_bridge.classify.assert_not_called()


def test_escalate_rule_resolves_via_code():
    engine = _make_engine()
    result = engine.run(AgentContext(input={"risk_score": 0.65}))
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.CODE
    engine._llm_bridge.classify.assert_not_called()


def test_pass_rule_resolves_via_code():
    engine = _make_engine()
    result = engine.run(AgentContext(input={"risk_score": 0.3}))
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.CODE
    engine._llm_bridge.classify.assert_not_called()


def test_priority_ordering_block_beats_escalate():
    # risk_score=0.9 matches both block (>0.8, p=1) and escalate (>0.5, p=2); block must win
    engine = _make_engine()
    result = engine._deterministic_logic(AgentContext(input={"risk_score": 0.9}))
    assert result.status == AgentStatus.BLOCK


def test_unknown_field_falls_back_to_llm():
    engine = _make_engine()
    engine._llm_bridge.classify.return_value = AgentResult.exception(
        agent="rule_engine", reason="LLM fallback test"
    )
    result = engine.run(AgentContext(input={"unknown_field": 999}))
    engine._llm_bridge.classify.assert_called_once()
    assert result.status == AgentStatus.EXCEPTION


def test_non_dict_input_returns_exception_without_llm():
    engine = _make_engine()
    result = engine._deterministic_logic(AgentContext(input="plain string"))
    assert result.status == AgentStatus.EXCEPTION
    engine._llm_bridge.classify.assert_not_called()


def test_empty_rules_file_always_falls_back_to_llm():
    engine = _make_engine(extra_rules=[])
    engine._llm_bridge.classify.return_value = AgentResult.passed(
        agent="rule_engine", payload={"llm_reason": "ok"}
    )
    result = engine.run(AgentContext(input={"risk_score": 0.1}))
    engine._llm_bridge.classify.assert_called_once()


# ── LLM bridge tests ───────────────────────────────────────────────────────────

def _make_bridge(max_retries: int = 3) -> LLMBridge:
    with patch("swarm_core.rules.llm_bridge.ollama"):
        with patch("swarm_core.rules.llm_bridge.OLLAMA_HOST", "http://fake"):
            with patch("swarm_core.rules.llm_bridge.OLLAMA_MODEL", "fake-model"):
                bridge = LLMBridge(max_retries=max_retries)
    bridge._client = MagicMock()
    bridge._model = "fake-model"
    return bridge


def test_llm_bridge_parses_block_json():
    bridge = _make_bridge()
    bridge._client.chat.return_value = {
        "message": {"content": '{"decision": "BLOCK", "reason": "too risky"}'}
    }
    result = bridge.classify(AgentContext(input={"x": 1}), "rule_engine")
    assert result.status == AgentStatus.BLOCK
    assert result.decision_source == DecisionSource.LLM


def test_llm_bridge_parses_pass_json():
    bridge = _make_bridge()
    bridge._client.chat.return_value = {
        "message": {"content": '{"decision": "PASS", "reason": "all good"}'}
    }
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.PASS
    assert result.decision_source == DecisionSource.LLM


def test_llm_bridge_parses_escalate_json():
    bridge = _make_bridge()
    bridge._client.chat.return_value = {
        "message": {"content": '{"decision": "ESCALATE", "reason": "needs review"}'}
    }
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.LLM


def test_llm_bridge_handles_unstructured_keyword_response():
    bridge = _make_bridge()
    bridge._client.chat.return_value = {
        "message": {"content": "After analysis I think this should be ESCALATE because it's unusual."}
    }
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.ESCALATE


def test_llm_bridge_connection_error_exhausts_retries_and_escalates():
    # All 3 attempts fail → ESCALATE, not EXCEPTION (pipeline keeps running)
    bridge = _make_bridge(max_retries=3)
    bridge._client.chat.side_effect = ConnectionError("Ollama not running")
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.LLM
    assert bridge._client.chat.call_count == 3


def test_llm_bridge_unrecognized_response_exhausts_retries_and_escalates():
    # Garbage response on every attempt → ESCALATE after all retries
    bridge = _make_bridge(max_retries=2)
    bridge._client.chat.return_value = {
        "message": {"content": "I cannot determine the answer to this question."}
    }
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.LLM
    assert bridge._client.chat.call_count == 2


def test_llm_bridge_succeeds_on_second_attempt():
    # First call raises, second succeeds → returns PASS, not an error
    bridge = _make_bridge(max_retries=3)
    good_response = {"message": {"content": '{"decision": "PASS", "reason": "ok"}'}}
    bridge._client.chat.side_effect = [ConnectionError("timeout"), good_response]
    result = bridge.classify(AgentContext(input={}), "rule_engine")
    assert result.status == AgentStatus.PASS
    assert bridge._client.chat.call_count == 2
