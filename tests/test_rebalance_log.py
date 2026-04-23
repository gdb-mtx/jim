"""Tests for execution/rebalance_log.py — JSONL journal writer.

The journal is the audit trail for every rebalance event across all three
call sites (API execute, APScheduler A4 job, filter_check cron). The
AUDIT_MONTH2 R4 fix added `execute_error` so entries still persist when
`execute_rebalance` raises mid-flight; these tests verify the field makes
it into the on-disk record end-to-end.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from execution.rebalance_log import get_recent_rebalances, log_rebalance


def test_log_rebalance_success_path(tmp_path):
    """Happy path — journal row has all expected fields."""
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=1,
            strategy_id="sm_filtered",
            portfolio_value=100_000.0,
            orders_submitted=3,
            orders_failed=0,
            order_details=[
                {"symbol": "AAPL", "side": "buy", "qty": 10, "status": "filled"},
            ],
            spy_filter_active=True,
            spy_filter_scalar=1.0,
            vol_scalar=0.79,
            source="manual",
        )

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["account"] == 1
        assert entry["strategy_id"] == "sm_filtered"
        assert entry["source"] == "manual"
        assert entry["orders_submitted"] == 3
        assert entry["vol_scalar"] == 0.79
        assert entry["execute_error"] is None


def test_log_rebalance_with_execute_error(tmp_path):
    """R4: execute_error captured when the execute step raised."""
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=4,
            strategy_id="crypto_momentum_filtered",
            portfolio_value=100_000.0,
            orders_submitted=0,
            orders_failed=0,
            order_details=[],
            vol_scalar=1.0,
            execute_error="ConnectionError: Alpaca API timeout",
            source="scheduled",
        )

        entry = json.loads(log_file.read_text().strip())
        assert entry["execute_error"] == "ConnectionError: Alpaca API timeout"
        assert entry["orders_submitted"] == 0
        assert entry["source"] == "scheduled"


def test_log_rebalance_preserves_partial_orders_on_error(tmp_path):
    """If execute raised AFTER partial order submission, the partial
    results are still journaled alongside the error — no silent loss."""
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=1,
            strategy_id="sm_filtered",
            portfolio_value=100_000.0,
            orders_submitted=2,
            orders_failed=0,
            order_details=[
                {"symbol": "AAPL", "side": "sell", "qty": 5, "status": "filled"},
                {"symbol": "MSFT", "side": "buy", "qty": 3, "status": "filled"},
            ],
            execute_error="RuntimeError: market closed mid-rebalance",
            source="filter_monitor",
        )

        entry = json.loads(log_file.read_text().strip())
        assert entry["execute_error"].startswith("RuntimeError")
        assert entry["orders_submitted"] == 2
        assert len(entry["orders"]) == 2
        assert entry["orders"][0]["symbol"] == "AAPL"


def test_get_recent_rebalances_roundtrip(tmp_path):
    """Write + read produces the fields we wrote."""
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=2,
            strategy_id="trend_lowvol",
            portfolio_value=99_000.0,
            orders_submitted=0,
            orders_failed=0,
            order_details=[],
            source="manual",
        )
        entries = get_recent_rebalances(limit=5, account=2)
        assert len(entries) == 1
        assert entries[0]["account"] == 2
        assert entries[0]["execute_error"] is None


# ---- N4: raw + post-filter weight capture for post-mortem reconstruction ----


def test_log_rebalance_captures_raw_and_post_filter_weights(tmp_path):
    """N4: journal persists both the raw strategy output and the post-filter
    weights so a future incident can reconstruct what the signal said before
    any overlay, without re-running generate_signals against a cache that
    has since been overwritten.
    """
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=1,
            strategy_id="sm_filtered",
            portfolio_value=100_000.0,
            orders_submitted=2,
            orders_failed=0,
            order_details=[],
            spy_filter_active=True,
            spy_filter_scalar=0.5,
            vol_scalar=1.0,
            raw_signal_weights={"AAPL": 0.08, "MSFT": 0.08, "TSLA": 0.08},
            post_filter_weights={"AAPL": 0.04, "MSFT": 0.04, "TSLA": 0.04},
            source="manual",
        )

        entry = json.loads(log_file.read_text().strip())
        assert entry["raw_signal_weights"] == {
            "AAPL": 0.08, "MSFT": 0.08, "TSLA": 0.08
        }
        assert entry["post_filter_weights"] == {
            "AAPL": 0.04, "MSFT": 0.04, "TSLA": 0.04
        }
        # Ratio between raw and post_filter should recover spy_filter_scalar (0.5).
        assert entry["post_filter_weights"]["AAPL"] == entry["raw_signal_weights"]["AAPL"] * 0.5


def test_log_rebalance_omits_weights_gracefully_when_none(tmp_path):
    """Backwards-compat: old callers that don't pass the new kwargs still
    work, and the field persists as null in the journal."""
    log_file = tmp_path / "rebalance_log.jsonl"
    with patch("execution.rebalance_log.LOG_FILE", log_file):
        log_rebalance(
            account=2,
            strategy_id="trend_lowvol",
            portfolio_value=99_000.0,
            orders_submitted=0,
            orders_failed=0,
            order_details=[],
            source="manual",
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["raw_signal_weights"] is None
        assert entry["post_filter_weights"] is None
