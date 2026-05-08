"""Tests for the pre-rebalance position reconciliation guard."""

import json
from pathlib import Path

import pytest

from execution.position_reconciliation import (
    ReconciliationResult,
    check_position_consistency,
    save_expected_positions,
)


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "execution.position_reconciliation.STATE_DIR", tmp_path
    )
    return tmp_path


def test_no_prior_state_passes(state_dir):
    result = check_position_consistency(4, {"BTC/USD": 0.5, "LINK/USD": 3000})
    assert result.consistent is True
    assert "no prior state" in result.details


def test_matching_positions_pass(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.5, "LINK/USD": 3000.0})
    result = check_position_consistency(4, {"BTC/USD": 0.5, "LINK/USD": 3000.0})
    assert result.consistent is True


def test_small_drift_within_tolerance_passes(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.500, "LINK/USD": 3000.0})
    result = check_position_consistency(
        4, {"BTC/USD": 0.502, "LINK/USD": 3010.0}
    )
    assert result.consistent is True


def test_unexpected_symbol_detected(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.5, "LINK/USD": 3000.0})
    result = check_position_consistency(
        4,
        {"BTC/USD": 0.5, "LINK/USD": 3000.0, "ADA/USD": 175000.0},
    )
    assert result.consistent is False
    assert any(m["type"] == "unexpected" for m in result.mismatches)
    assert any(m["symbol"] == "ADA/USD" for m in result.mismatches)


def test_missing_symbol_detected(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.5, "LINK/USD": 3000.0})
    result = check_position_consistency(
        4,
        {"BTC/USD": 0.5},
        prices={"LINK/USD": 10.0},
    )
    assert result.consistent is False
    assert any(m["type"] == "missing" and m["symbol"] == "LINK/USD" for m in result.mismatches)


def test_missing_dust_ignored(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.5, "DOT/USD": 0.5})
    result = check_position_consistency(
        4,
        {"BTC/USD": 0.5},
        prices={"DOT/USD": 1.50},
    )
    assert result.consistent is True


def test_qty_drift_detected(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.58})
    result = check_position_consistency(4, {"BTC/USD": 0.018})
    assert result.consistent is False
    assert any(m["type"] == "qty_drift" for m in result.mismatches)


def test_phantom_short_detected(state_dir):
    save_expected_positions(4, {"BTC/USD": 0.5, "DOT/USD": 40.0})
    result = check_position_consistency(4, {"BTC/USD": 0.5, "DOT/USD": -490.0})
    assert result.consistent is False
    assert any(m["type"] == "phantom_short" for m in result.mismatches)


def test_override_env_bypasses(state_dir, monkeypatch):
    save_expected_positions(4, {"BTC/USD": 0.5})
    monkeypatch.setenv("FIRE_SKIP_RECONCILIATION", "1")
    result = check_position_consistency(4, {"BTC/USD": 0.018, "ADA/USD": 175000.0})
    assert result.consistent is True
    assert "skipped" in result.details


def test_corrupt_state_file_passes(state_dir):
    path = state_dir / "expected_positions_acct4.json"
    path.write_text("not json{{{")
    result = check_position_consistency(4, {"BTC/USD": 0.5})
    assert result.consistent is True
    assert "corrupt" in result.details


def test_save_and_load_roundtrip(state_dir):
    positions = {"BTC/USD": 0.447206823, "LINK/USD": 3471.315346716}
    save_expected_positions(4, positions, portfolio_value=93280.84)

    path = state_dir / "expected_positions_acct4.json"
    state = json.loads(path.read_text())
    assert state["positions"] == positions
    assert state["portfolio_value"] == 93280.84
    assert "timestamp" in state
