"""Tests for the validation gate — blocks unvalidated rebalances."""

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from execution import validation_gate
from execution.validation_gate import (
    GateResult,
    ValidationGateError,
    check,
    require_validated,
)


def _write_state(tmp_path, state: dict):
    path = tmp_path / "validation_state.json"
    path.write_text(json.dumps(state))
    return path


def test_no_record_blocks(tmp_path):
    path = _write_state(tmp_path, {})
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(1)
        assert r.allowed is False
        assert "no validation record" in r.reason


def test_missing_file_blocks(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with patch.object(validation_gate, "STATE_PATH", missing):
        r = check(1)
        assert r.allowed is False


def test_fail_status_blocks(tmp_path):
    expires = (date.today() + timedelta(days=30)).isoformat()
    state = {
        "account_4": {
            "status": "fail",
            "reason": "parameter instability",
            "expires": expires,
        }
    }
    path = _write_state(tmp_path, state)
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(4)
        assert r.allowed is False
        assert "FAILED" in r.reason


def test_marginal_status_allows(tmp_path):
    """MARGINAL is valid for paper — only FAIL and unvalidated block."""
    expires = (date.today() + timedelta(days=30)).isoformat()
    state = {
        "account_1": {
            "status": "marginal",
            "reason": "ratio below threshold",
            "expires": expires,
        }
    }
    path = _write_state(tmp_path, state)
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(1)
        assert r.allowed is True


def test_expired_pass_blocks(tmp_path):
    expires = (date.today() - timedelta(days=1)).isoformat()
    state = {
        "account_1": {
            "status": "pass",
            "oos_sharpe": 1.65,
            "expires": expires,
        }
    }
    path = _write_state(tmp_path, state)
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(1)
        assert r.allowed is False
        assert "expired" in r.reason


def test_valid_pass_allows(tmp_path):
    expires = (date.today() + timedelta(days=30)).isoformat()
    state = {
        "account_1": {
            "status": "pass",
            "oos_sharpe": 1.65,
            "expires": expires,
        }
    }
    path = _write_state(tmp_path, state)
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(1)
        assert r.allowed is True
        assert r.reason == "validated"


def test_override_env_allows_failed(tmp_path, monkeypatch):
    state = {"account_4": {"status": "fail", "reason": "x"}}
    path = _write_state(tmp_path, state)
    monkeypatch.setenv("FIRE_VALIDATION_OVERRIDE", "1")
    with patch.object(validation_gate, "STATE_PATH", path):
        r = check(4)
        assert r.allowed is True
        assert r.override_active is True


def test_require_validated_raises_on_block(tmp_path):
    path = _write_state(tmp_path, {})
    with patch.object(validation_gate, "STATE_PATH", path):
        with pytest.raises(ValidationGateError) as exc:
            require_validated(1)
        assert exc.value.detail["account"] == 1


def test_require_validated_returns_on_allow(tmp_path):
    expires = (date.today() + timedelta(days=30)).isoformat()
    state = {"account_1": {"status": "pass", "expires": expires, "oos_sharpe": 1.4}}
    path = _write_state(tmp_path, state)
    with patch.object(validation_gate, "STATE_PATH", path):
        result = require_validated(1)
        assert isinstance(result, GateResult)
        assert result.allowed is True
