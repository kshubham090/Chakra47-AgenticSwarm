from __future__ import annotations

from pathlib import Path

import pytest

from swarm_core.base import AgentContext
from swarm_core.perception.ingester import Ingester, SourceType


@pytest.fixture
def ingester() -> Ingester:
    return Ingester()


# ── dict inputs ────────────────────────────────────────────────────────────────

def test_plain_dict_normalized(ingester: Ingester):
    ctx = ingester.ingest({"risk_score": 0.7, "action": "read"})
    assert ctx.input == {"risk_score": 0.7, "action": "read"}
    assert ctx.metadata["source_type"] == SourceType.DICT


def test_dict_with_input_key_extracts_payload(ingester: Ingester):
    ctx = ingester.ingest({"input": {"risk_score": 0.2}, "task_id": "t1"})
    assert ctx.input == {"risk_score": 0.2}
    assert ctx.task_id == "t1"


def test_dict_honors_task_id(ingester: Ingester):
    ctx = ingester.ingest({"value": 1, "task_id": "custom-id"})
    assert ctx.task_id == "custom-id"
    assert "task_id" not in ctx.input


def test_dict_extracts_metadata(ingester: Ingester):
    ctx = ingester.ingest({"value": 1, "metadata": {"origin": "sensor"}})
    assert ctx.metadata["origin"] == "sensor"
    assert "metadata" not in ctx.input


def test_explicit_task_id_overrides_generated(ingester: Ingester):
    ctx = ingester.ingest({"value": 1}, task_id="forced-id")
    assert ctx.task_id == "forced-id"


# ── string inputs ──────────────────────────────────────────────────────────────

def test_json_string_parsed_to_dict(ingester: Ingester):
    ctx = ingester.ingest('{"risk_score": 0.9}')
    assert ctx.input == {"risk_score": 0.9}
    assert ctx.metadata["source_type"] == SourceType.JSON


def test_plain_text_string_wrapped(ingester: Ingester):
    ctx = ingester.ingest("deploy service alpha")
    assert ctx.input == "deploy service alpha"
    assert ctx.metadata["source_type"] == SourceType.TEXT


def test_json_string_with_task_id_honored(ingester: Ingester):
    ctx = ingester.ingest('{"task_id": "j1", "value": 42}')
    assert ctx.task_id == "j1"
    assert ctx.metadata["source_type"] == SourceType.JSON


def test_malformed_json_treated_as_text(ingester: Ingester):
    ctx = ingester.ingest("{not valid json}")
    assert ctx.metadata["source_type"] == SourceType.TEXT
    assert "{not valid json}" in ctx.input


# ── bytes inputs ───────────────────────────────────────────────────────────────

def test_bytes_decoded_and_normalized(ingester: Ingester):
    ctx = ingester.ingest(b"hello swarm")
    assert ctx.input == "hello swarm"
    assert ctx.metadata["source_type"] == SourceType.BYTES


def test_bytes_containing_json_parsed(ingester: Ingester):
    ctx = ingester.ingest(b'{"risk_score": 0.4}')
    assert ctx.input == {"risk_score": 0.4}
    assert ctx.metadata["source_type"] == SourceType.BYTES


# ── Path inputs ────────────────────────────────────────────────────────────────

def test_path_reads_plain_text(ingester: Ingester, tmp_path: Path):
    f = tmp_path / "input.txt"
    f.write_text("mission: patrol sector 4")
    ctx = ingester.ingest(f)
    assert ctx.input == "mission: patrol sector 4"
    assert ctx.metadata["source_type"] == SourceType.FILE
    assert ctx.metadata["path"] == str(f)


def test_path_reads_json_file(ingester: Ingester, tmp_path: Path):
    f = tmp_path / "input.json"
    f.write_text('{"risk_score": 0.3, "action": "read"}')
    ctx = ingester.ingest(f)
    assert ctx.input == {"risk_score": 0.3, "action": "read"}
    assert ctx.metadata["source_type"] == SourceType.FILE


def test_path_missing_file_returns_error_context(ingester: Ingester, tmp_path: Path):
    missing = tmp_path / "ghost.txt"
    ctx = ingester.ingest(missing)
    assert ctx.metadata["source_type"] == SourceType.FILE
    assert ctx.metadata.get("error") is True
    assert "error" in ctx.input


# ── passthrough and unknown ────────────────────────────────────────────────────

def test_agentcontext_passthrough(ingester: Ingester):
    original = AgentContext(input={"x": 1}, task_id="keep-me")
    ctx = ingester.ingest(original)
    assert ctx is original  # same object, not a copy


def test_unknown_type_wrapped_with_metadata(ingester: Ingester):
    ctx = ingester.ingest(42)
    assert ctx.input == 42
    assert ctx.metadata["source_type"] == SourceType.UNKNOWN
    assert ctx.metadata["raw_type"] == "int"


def test_generated_task_id_is_uuid(ingester: Ingester):
    ctx = ingester.ingest("some input")
    import re
    assert re.match(r"[0-9a-f-]{36}", ctx.task_id)


def test_bytes_latin1_fallback(ingester: Ingester):
    # b'\xe9' is valid latin-1 ("é") but invalid UTF-8 → must fall back to latin-1 decode
    raw = b"caf\xe9"
    ctx = ingester.ingest(raw)
    assert ctx.metadata["source_type"] == SourceType.BYTES
    assert "caf" in ctx.input
