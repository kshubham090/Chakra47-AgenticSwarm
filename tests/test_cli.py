from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from swarm_core.base import AgentResult, AgentStatus
from swarm_core.cli import (
    _build_parser,
    _NoOpChain,
    _NoOpEntry,
    _ollama_running,
    _parse_mission,
    _print_result,
    _read_mission_interactive,
    _run_command,
    ensure_ollama,
)
from swarm_core.orchestrator import SwarmResult

# ── _parse_mission ─────────────────────────────────────────────────────────────


def test_parse_mission_json_object():
    assert _parse_mission('{"risk_score": 0.3, "action": "read"}') == {
        "risk_score": 0.3,
        "action": "read",
    }


def test_parse_mission_plain_string():
    assert _parse_mission("deploy service alpha") == "deploy service alpha"


def test_parse_mission_json_array():
    assert _parse_mission("[1, 2, 3]") == [1, 2, 3]


def test_parse_mission_strips_whitespace():
    assert _parse_mission('  {"x": 1}  ') == {"x": 1}


def test_parse_mission_non_json_braces():
    assert _parse_mission("{not valid}") == "{not valid}"


# ── _NoOpChain ─────────────────────────────────────────────────────────────────


def test_noop_chain_log_returns_entry():
    chain = _NoOpChain()
    entry = chain.log(
        task_id="t1",
        agent="test",
        status="PASS",
        decision_source="code",
        raw_input={},
        reason="",
        extra_payload=None,
    )
    assert isinstance(entry, _NoOpEntry)
    assert entry.id == "no-audit"
    assert len(entry.block_hash) == 64


def test_noop_chain_verify_always_true():
    assert _NoOpChain().verify_chain() is True


# ── _ollama_running / ensure_ollama ───────────────────────────────────────────


def test_ollama_running_returns_true_when_port_open():
    with patch("swarm_core.cli.socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        assert _ollama_running() is True


def test_ollama_running_returns_false_on_connection_error():
    with patch("swarm_core.cli.socket.create_connection", side_effect=OSError):
        assert _ollama_running() is False


def test_ensure_ollama_skips_when_already_running(capsys):
    with patch("swarm_core.cli._ollama_running", return_value=True):
        result = ensure_ollama("qwen3:30b-a3b")
    assert result is True


def test_ensure_ollama_starts_server_when_not_running(capsys):
    call_count = 0

    def _running_after_start():
        nonlocal call_count
        call_count += 1
        return call_count > 1  # False on first call (before start), True after

    with patch("swarm_core.cli._ollama_running", side_effect=_running_after_start):
        with patch("swarm_core.cli.subprocess.Popen"):
            with patch("swarm_core.cli.time.sleep"):
                result = ensure_ollama("qwen3:30b-a3b")

    assert result is True


def test_ensure_ollama_returns_false_when_binary_missing(capsys):
    with patch("swarm_core.cli._ollama_running", return_value=False):
        with patch("swarm_core.cli.subprocess.Popen", side_effect=FileNotFoundError):
            result = ensure_ollama("qwen3:30b-a3b")
    assert result is False
    assert "not found" in capsys.readouterr().err


def test_ensure_ollama_returns_false_on_timeout(capsys):
    with patch("swarm_core.cli._ollama_running", return_value=False):
        with patch("swarm_core.cli.subprocess.Popen"):
            with patch("swarm_core.cli.time.sleep"):
                result = ensure_ollama("qwen3:30b-a3b")
    assert result is False


# ── _build_parser ──────────────────────────────────────────────────────────────


def test_parser_run_no_mission_defaults_to_none():
    parser = _build_parser()
    args = parser.parse_args(["run", "--no-audit"])
    assert args.mission is None
    assert args.no_audit is True


def test_parser_run_with_mission():
    parser = _build_parser()
    args = parser.parse_args(["run", "patrol sector 4"])
    assert args.mission == "patrol sector 4"
    assert args.no_audit is False


def test_parser_run_with_all_flags():
    parser = _build_parser()
    args = parser.parse_args(
        ["run", "{}", "--no-audit", "--task-id", "t99", "--rules", "r.yaml", "--model", "qwen3:8b"]
    )
    assert args.no_audit is True
    assert args.task_id == "t99"
    assert args.rules == "r.yaml"
    assert args.model == "qwen3:8b"


def test_parser_requires_subcommand():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


# ── _read_mission_interactive ─────────────────────────────────────────────────


def test_read_mission_interactive_returns_input():
    with patch("builtins.input", return_value="patrol sector 4"):
        assert _read_mission_interactive() == "patrol sector 4"


def test_read_mission_interactive_returns_none_on_exit():
    with patch("builtins.input", return_value="exit"):
        assert _read_mission_interactive() is None


def test_read_mission_interactive_returns_none_on_eof():
    with patch("builtins.input", side_effect=EOFError):
        assert _read_mission_interactive() is None


def test_read_mission_interactive_returns_none_on_keyboard_interrupt():
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        assert _read_mission_interactive() is None


def test_read_mission_interactive_returns_none_on_empty():
    with patch("builtins.input", return_value="  "):
        assert _read_mission_interactive() is None


# ── _print_result ──────────────────────────────────────────────────────────────


def _make_swarm_result(
    status: AgentStatus = AgentStatus.PASS,
    blocked_by: str | None = None,
    escalations: list[str] | None = None,
    agent_results: list | None = None,
) -> SwarmResult:
    return SwarmResult(
        task_id="t-test",
        final_status=status,
        blocked_by=blocked_by,
        escalations=escalations or [],
        agent_results=agent_results or [],
    )


def test_print_result_pass(capsys):
    r = AgentResult.passed(agent="rule_engine")
    _print_result(_make_swarm_result(agent_results=[r]))
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "t-test" in out
    assert "rule_engine" in out


def test_print_result_blocked_shows_blocked_by(capsys):
    r = AgentResult.blocked(agent="anomaly_detector", reason="z=5.1")
    _print_result(
        _make_swarm_result(
            status=AgentStatus.BLOCK, blocked_by="anomaly_detector", agent_results=[r]
        )
    )
    out = capsys.readouterr().out
    assert "anomaly_detector" in out
    assert "Blocked" in out


def test_print_result_escalation_shows_flags(capsys):
    r = AgentResult.escalate(agent="risk_agent", reason="elevated")
    _print_result(
        _make_swarm_result(
            status=AgentStatus.ESCALATE, escalations=["risk_agent"], agent_results=[r]
        )
    )
    out = capsys.readouterr().out
    assert "Flags" in out
    assert "risk_agent" in out


def test_print_result_reason_in_pipeline(capsys):
    r = AgentResult.blocked(agent="rule_engine", reason="Risk score exceeds threshold")
    _print_result(_make_swarm_result(agent_results=[r]))
    assert "Risk score exceeds threshold" in capsys.readouterr().out


# ── _run_command (single-shot) ────────────────────────────────────────────────


def _args(
    mission: str | None = "{}",
    no_audit: bool = True,
    task_id: str | None = None,
    rules: str | None = None,
    model: str | None = None,
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.mission = mission
    ns.no_audit = no_audit
    ns.task_id = task_id
    ns.rules = rules
    ns.model = model
    return ns


def _mock_orchestrator(status: AgentStatus = AgentStatus.PASS) -> MagicMock:
    orch = MagicMock()
    orch.run.return_value = SwarmResult(
        task_id="t1",
        final_status=status,
        agent_results=[AgentResult.passed(agent="rule_engine")],
    )
    return orch


def _patched_run(args, orch_status=AgentStatus.PASS):
    """Helper: patch Orchestrator + Ollama check and run the command."""
    with patch(
        "swarm_core.orchestrator.Orchestrator", return_value=_mock_orchestrator(orch_status)
    ):
        with patch("swarm_core.cli.ensure_ollama"):
            return _run_command(args)


def test_run_command_returns_0_on_pass(capsys):
    assert _patched_run(_args(no_audit=True)) == 0


def test_run_command_returns_1_on_block(capsys):
    assert _patched_run(_args(no_audit=True), AgentStatus.BLOCK) == 1


def test_run_command_passes_task_id(capsys):
    mock_orch = _mock_orchestrator()
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch):
        with patch("swarm_core.cli.ensure_ollama"):
            _run_command(_args(task_id="my-task"))
    mock_orch.run.assert_called_once_with({}, task_id="my-task")


def test_run_command_passes_rules_path(capsys, tmp_path):
    rules = tmp_path / "r.yaml"
    rules.write_text("{}")
    mock_orch = _mock_orchestrator()
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch) as mock_cls:
        with patch("swarm_core.cli.ensure_ollama"):
            _run_command(_args(rules=str(rules)))
    _, kwargs = mock_cls.call_args
    assert kwargs["rules_path"] == rules


def test_run_command_audit_chain_failure_returns_2(capsys):
    with patch("swarm_core.audit.chain.AuditChain", side_effect=OSError("Missing SUPABASE_URL")):
        with patch("swarm_core.cli.ensure_ollama"):
            code = _run_command(_args(no_audit=False))
    assert code == 2
    err = capsys.readouterr().err
    assert "Audit chain error" in err
    assert "--no-audit" in err


def test_run_command_json_parsed(capsys):
    mock_orch = _mock_orchestrator()
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch):
        with patch("swarm_core.cli.ensure_ollama"):
            _run_command(_args(mission='{"risk_score": 0.1}'))
    mock_orch.run.assert_called_once_with({"risk_score": 0.1}, task_id=None)


def test_run_command_plain_text_warns(capsys):
    with patch("swarm_core.orchestrator.Orchestrator", return_value=_mock_orchestrator()):
        with patch("swarm_core.cli.ensure_ollama"):
            _run_command(_args(mission="plain text mission"))
    err = capsys.readouterr().err
    assert "Warning" in err


# ── interactive mode ──────────────────────────────────────────────────────────


def test_run_command_interactive_mode_starts_repl(capsys):
    mock_orch = _mock_orchestrator()
    inputs = iter(["patrol sector 4", "exit"])
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch):
        with patch("swarm_core.cli.ensure_ollama"):
            with patch("builtins.input", side_effect=inputs):
                code = _run_command(_args(mission=None))
    assert code == 0
    assert mock_orch.run.call_count == 1


def test_repl_exits_on_keyboard_interrupt(capsys):
    mock_orch = _mock_orchestrator()
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch):
        with patch("swarm_core.cli.ensure_ollama"):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                code = _run_command(_args(mission=None))
    assert code == 0
    assert mock_orch.run.call_count == 0


# ── main (integration) ────────────────────────────────────────────────────────


def test_main_exits_with_0_on_pass():
    mock_orch = _mock_orchestrator(AgentStatus.PASS)
    with patch("swarm_core.orchestrator.Orchestrator", return_value=mock_orch):
        with patch("swarm_core.cli.ensure_ollama"):
            with patch("sys.argv", ["swarm", "run", "{}", "--no-audit"]):
                from swarm_core.cli import main

                with pytest.raises(SystemExit) as exc_info:
                    main()
    assert exc_info.value.code == 0
