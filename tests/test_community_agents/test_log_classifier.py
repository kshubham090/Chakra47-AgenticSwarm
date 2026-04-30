from community_agents.log_classifier.agent import LogClassifier
from swarm_core.base import AgentContext, AgentStatus, DecisionSource


def _ctx(input_data) -> AgentContext:
    return AgentContext(input=input_data)


# ── known inputs must resolve via source == "code" ────────────────────────────


def test_critical_keyword_blocks():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "CRITICAL: kernel panic — not syncing"}))
    assert result.status == AgentStatus.BLOCK
    assert result.decision_source == DecisionSource.CODE


def test_fatal_keyword_blocks():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "FATAL error in thread main"}))
    assert result.status == AgentStatus.BLOCK


def test_panic_keyword_blocks():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "PANIC: out of memory"}))
    assert result.status == AgentStatus.BLOCK


def test_error_keyword_escalates():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "ERROR: connection refused"}))
    assert result.status == AgentStatus.ESCALATE
    assert result.decision_source == DecisionSource.CODE


def test_exception_keyword_escalates():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "Unhandled EXCEPTION in worker thread"}))
    assert result.status == AgentStatus.ESCALATE


def test_warn_keyword_passes_flagged():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "WARNING: deprecated API called"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["flagged"] is True
    assert result.payload["severity"] == "WARN"


def test_info_keyword_passes_clean():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "INFO: service started on port 8080"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["flagged"] is False
    assert result.payload["severity"] == "INFO"


def test_debug_line_passes_clean():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "DEBUG: cache hit ratio 0.97"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["severity"] == "INFO"


def test_case_insensitive_matching():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "critical: disk full"}))
    assert result.status == AgentStatus.BLOCK


# ── skip when log_line absent ─────────────────────────────────────────────────


def test_missing_log_line_skips():
    agent = LogClassifier()
    result = agent.run(_ctx({"other_key": "value"}))
    assert result.status == AgentStatus.PASS
    assert result.payload.get("skipped") is True


# ── bad input returns exception (not an LLM call) ─────────────────────────────


def test_non_dict_input_is_exception():
    agent = LogClassifier()
    result = agent.run(_ctx("bare string"))
    assert result.status == AgentStatus.EXCEPTION
    assert result.decision_source == DecisionSource.CODE


def test_non_string_log_line_is_exception():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": 42}))
    assert result.status == AgentStatus.EXCEPTION


# ── custom keyword config ─────────────────────────────────────────────────────


def test_custom_critical_keyword():
    agent = LogClassifier(config={"critical_keywords": ["MELTDOWN"]})
    result = agent.run(_ctx({"log_line": "MELTDOWN detected in reactor core"}))
    assert result.status == AgentStatus.BLOCK


def test_custom_error_keyword():
    agent = LogClassifier(config={"error_keywords": ["TIMEOUT"]})
    result = agent.run(_ctx({"log_line": "TIMEOUT after 30s waiting for lock"}))
    assert result.status == AgentStatus.ESCALATE


def test_custom_warn_keyword():
    agent = LogClassifier(config={"warn_keywords": ["SLOW"]})
    result = agent.run(_ctx({"log_line": "SLOW query detected: 4200ms"}))
    assert result.status == AgentStatus.PASS
    assert result.payload["flagged"] is True


# ── critical takes priority over error ────────────────────────────────────────


def test_critical_beats_error_in_same_line():
    agent = LogClassifier()
    result = agent.run(_ctx({"log_line": "CRITICAL ERROR: storage subsystem failed"}))
    assert result.status == AgentStatus.BLOCK
