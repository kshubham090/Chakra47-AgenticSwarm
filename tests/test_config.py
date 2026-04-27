from __future__ import annotations

import os

import pytest

from swarm_core.config import _require


def test_require_raises_on_missing_env_var():
    sentinel = "_CHAKRA47_TEST_VAR_DOES_NOT_EXIST_"
    os.environ.pop(sentinel, None)
    with pytest.raises(EnvironmentError, match="Missing required env var"):
        _require(sentinel)


def test_require_returns_value_when_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("_CHAKRA47_TEST_VAR_PRESENT_", "hello")
    assert _require("_CHAKRA47_TEST_VAR_PRESENT_") == "hello"
