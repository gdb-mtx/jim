"""Tests for `_backfill_last_run_from_journal` in api/main.py.

The function reads the most recent `source=scheduled` entry from
`rebalance_log.jsonl` and populates the module-level `_last_run_info`
dict so the Ops panel's APScheduler row survives uvicorn reloads.
"""

from unittest.mock import patch

from api import main as api_main


def _reset():
    api_main._last_run_info.clear()


def test_backfill_populates_from_scheduled_success():
    _reset()
    entries = [
        {
            "timestamp": "2026-04-23T00:05:03.337872+00:00",
            "source": "scheduled",
            "account": 4,
            "orders_submitted": 2,
            "orders_failed": 0,
            "execute_error": None,
        },
    ]
    with patch(
        "execution.rebalance_log.get_recent_rebalances", return_value=entries
    ):
        api_main._backfill_last_run_from_journal()

    info = api_main._last_run_info.get("daily_crypto_rebalance")
    assert info is not None
    assert info["started"] == "2026-04-23T00:05:03.337872+00:00"
    assert info["finished"] == "2026-04-23T00:05:03.337872+00:00"
    assert info["status"] == "success"
    assert info["error"] is None


def test_backfill_skips_non_scheduled_sources():
    _reset()
    entries = [
        {"timestamp": "2026-04-22T15:30:29+00:00", "source": "manual",
         "orders_submitted": 2, "orders_failed": 0},
        {"timestamp": "2026-04-21T21:37:53+00:00", "source": "halt_reset",
         "orders_submitted": 0, "orders_failed": 0},
        {"timestamp": "2026-04-23T00:05:03+00:00", "source": "scheduled",
         "orders_submitted": 2, "orders_failed": 0},
    ]
    with patch(
        "execution.rebalance_log.get_recent_rebalances", return_value=entries
    ):
        api_main._backfill_last_run_from_journal()

    # Should pick the scheduled entry, not the first one in the list.
    info = api_main._last_run_info.get("daily_crypto_rebalance")
    assert info is not None
    assert info["started"] == "2026-04-23T00:05:03+00:00"
    assert info["status"] == "success"


def test_backfill_marks_failed_when_orders_failed():
    _reset()
    entries = [
        {
            "timestamp": "2026-04-23T00:05:03+00:00",
            "source": "scheduled",
            "orders_submitted": 2,
            "orders_failed": 1,  # partial failure
            "execute_error": None,
        },
    ]
    with patch(
        "execution.rebalance_log.get_recent_rebalances", return_value=entries
    ):
        api_main._backfill_last_run_from_journal()

    assert api_main._last_run_info["daily_crypto_rebalance"]["status"] == "failed"


def test_backfill_marks_failed_when_execute_error():
    _reset()
    entries = [
        {
            "timestamp": "2026-04-23T00:05:03+00:00",
            "source": "scheduled",
            "orders_submitted": 0,
            "orders_failed": 0,
            "execute_error": "RuntimeError: Alpaca rejected",
        },
    ]
    with patch(
        "execution.rebalance_log.get_recent_rebalances", return_value=entries
    ):
        api_main._backfill_last_run_from_journal()

    info = api_main._last_run_info["daily_crypto_rebalance"]
    assert info["status"] == "failed"
    assert info["error"] == "RuntimeError: Alpaca rejected"


def test_backfill_no_scheduled_entries_leaves_dict_empty():
    _reset()
    entries = [
        {"timestamp": "2026-04-22T15:30:29+00:00", "source": "manual",
         "orders_submitted": 2, "orders_failed": 0},
    ]
    with patch(
        "execution.rebalance_log.get_recent_rebalances", return_value=entries
    ):
        api_main._backfill_last_run_from_journal()

    assert "daily_crypto_rebalance" not in api_main._last_run_info


def test_backfill_exception_non_fatal():
    _reset()
    with patch(
        "execution.rebalance_log.get_recent_rebalances",
        side_effect=OSError("disk error"),
    ):
        # Must not raise.
        api_main._backfill_last_run_from_journal()

    assert "daily_crypto_rebalance" not in api_main._last_run_info
