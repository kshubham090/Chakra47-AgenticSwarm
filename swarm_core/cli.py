from __future__ import annotations

import argparse
import dataclasses
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from swarm_core.utils import get_logger

logger = get_logger(__name__)

_OLLAMA_HOST = "127.0.0.1"
_OLLAMA_PORT = 11434
_OLLAMA_STARTUP_TIMEOUT = 12  # seconds


# ── audit chain stub ───────────────────────────────────────────────────────────


@dataclasses.dataclass
class _NoOpEntry:
    id: str = "no-audit"
    block_hash: str = "0" * 64


class _NoOpChain:
    """Audit chain stub for local runs without Supabase credentials."""

    def log(
        self,
        task_id: str,
        agent: str,
        status: str,
        decision_source: str,
        raw_input: Any,
        reason: str = "",
        extra_payload: dict[str, Any] | None = None,
    ) -> _NoOpEntry:
        return _NoOpEntry()

    def verify_chain(self) -> bool:
        return True


# ── Ollama lifecycle ───────────────────────────────────────────────────────────


def _ollama_running() -> bool:
    try:
        sock = socket.create_connection((_OLLAMA_HOST, _OLLAMA_PORT), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


def ensure_ollama(model: str) -> bool:
    """
    Start Ollama server if not already running, then verify the model is available.
    Returns True if Ollama is ready, False if it couldn't be started.
    """
    if _ollama_running():
        logger.info("cli: Ollama already running on port %d", _OLLAMA_PORT)
        return True

    print("[swarm] Ollama not detected — starting server...", flush=True)
    popen_flags: dict[str, Any] = {}
    if sys.platform == "win32":
        popen_flags["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **popen_flags,
        )
    except FileNotFoundError:
        print(
            "[swarm] 'ollama' not found in PATH. Install from https://ollama.com/download",
            file=sys.stderr,
        )
        return False

    for elapsed in range(_OLLAMA_STARTUP_TIMEOUT):
        time.sleep(1)
        if _ollama_running():
            print(f"[swarm] Ollama ready ({elapsed + 1}s). Model: {model}", flush=True)
            return True

    print("[swarm] Warning: Ollama didn't respond in time — LLM path may fail.", file=sys.stderr)
    return False


# ── argument parser ────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarm",
        description="Chakra47 AgenticSwarm — governed, code-first multi-agent pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser(
        "run",
        help="Run a mission (omit mission to enter interactive mode)",
    )
    run_p.add_argument(
        "mission",
        nargs="?",
        default=None,
        help="Mission as JSON or plain text. Omit to start interactive mode.",
    )
    run_p.add_argument("--task-id", default=None, metavar="ID", help="Optional task ID")
    run_p.add_argument(
        "--no-audit",
        action="store_true",
        help="Skip Supabase audit chain (for local testing without credentials)",
    )
    run_p.add_argument(
        "--rules",
        default=None,
        metavar="PATH",
        help="Path to a custom rules.yaml (defaults to the built-in one)",
    )
    run_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Ollama model name (overrides OLLAMA_MODEL env var)",
    )
    return parser


# ── mission input ──────────────────────────────────────────────────────────────


def _parse_mission(raw: str) -> Any:
    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return stripped


def _read_mission_interactive() -> str | None:
    """Read one mission from stdin. Returns None on EOF or exit command."""
    try:
        raw = input("[swarm] > ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if raw.lower() in ("exit", "quit", "q", ""):
        return None
    return raw


# ── result rendering ───────────────────────────────────────────────────────────


def _print_result(result: Any) -> None:
    status = result.final_status.value
    status_icon = {"PASS": "[OK]", "BLOCK": "[BLOCK]", "ESCALATE": "[FLAG]"}.get(status, status)
    print(f"\n{status_icon} {status}  |  task: {result.task_id}")
    if result.blocked_by:
        print(f"    Blocked by: {result.blocked_by}")
    if result.escalations:
        print(f"    Flags     : {', '.join(result.escalations)}")
    print()
    for r in result.agent_results:
        src = r.decision_source.value.upper()
        note = f"  <- {r.reason}" if r.reason else ""
        print(f"  [{src:3s}] {r.agent:<24s} {r.status.value}{note}")
    print()


def _print_banner(model: str, audit: bool) -> None:
    print()
    print("  Chakra47 AgenticSwarm  v0.1.0")
    print("  Code decides. LLM advises.")
    print(f"  Model : {model}")
    print(f"  Audit : {'enabled (Supabase)' if audit else 'disabled (--no-audit)'}")
    print()
    print("  Type a mission and press Enter. JSON or plain text both work.")
    print("  Type 'exit' or press Ctrl+C to quit.")
    print()


# ── command handler ────────────────────────────────────────────────────────────


def _build_chain(args: argparse.Namespace) -> tuple[Any, int]:
    """Return (chain, exit_code). exit_code != 0 means fatal error."""
    if args.no_audit:
        return _NoOpChain(), 0
    try:
        from swarm_core.audit.chain import AuditChain

        return AuditChain(), 0
    except Exception as exc:
        print(f"[swarm] Audit chain error: {exc}", file=sys.stderr)
        print(
            "[swarm] Tip: set SUPABASE_URL and SUPABASE_KEY in .env, or pass --no-audit",
            file=sys.stderr,
        )
        return None, 2


def _run_command(args: argparse.Namespace) -> int:
    from swarm_core.config import OLLAMA_MODEL
    from swarm_core.orchestrator import Orchestrator

    model = args.model or OLLAMA_MODEL
    ensure_ollama(model)

    chain, err = _build_chain(args)
    if err:
        return err

    rules_path = Path(args.rules) if args.rules else None
    orch = Orchestrator(audit_chain=chain, rules_path=rules_path)

    if args.mission is None:
        _print_banner(model, not args.no_audit)
        return _repl(orch, args)

    mission = _parse_mission(args.mission)
    if not isinstance(mission, dict):
        print(
            f"[swarm] Warning: input parsed as {type(mission).__name__}, not dict.\n"
            "        In PowerShell store JSON in a variable first:\n"
            '          $m = \'{"key": "val"}\'; python -m swarm_core run $m --no-audit',
            file=sys.stderr,
        )
    result = orch.run(mission, task_id=args.task_id)
    _print_result(result)
    return 0 if result.passed else 1


def _repl(orch: Any, args: argparse.Namespace) -> int:
    """Interactive REPL loop — read missions from stdin until exit."""
    while True:
        raw = _read_mission_interactive()
        if raw is None:
            print("[swarm] Goodbye.")
            break
        mission = _parse_mission(raw)
        result = orch.run(mission, task_id=args.task_id)
        _print_result(result)
    return 0


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(_run_command(args))
