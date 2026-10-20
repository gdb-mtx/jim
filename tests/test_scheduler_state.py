"""Heartbeat + pre-flight state (execution/scheduler_state.py, 2026-10-20)."""

from datetime import datetime, timedelta, timezone

import pytest

from execution import scheduler_state as st


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_DIR", tmp_path)
    monkeypatch.setattr(st, "HEARTBEAT_PATH", tmp_path / "hb.json")
    monkeypatch.setattr(st, "PREFLIGHT_PATH", tmp_path / "pf.json")


def test_heartbeat_roundtrip_and_staleness(monkeypatch):
    assert st.read_heartbeat() is None
    st.write_heartbeat("not_due", "next 2026-11-18", next_rebalance="2026-11-18")
    hb = st.read_heartbeat()
    assert hb["decision"] == "not_due" and hb["stale"] is False and hb["age_s"] < 5
    old = (datetime.now(timezone.utc) - timedelta(seconds=st.HEARTBEAT_STALE_S + 60)).isoformat()
    st._write(st.HEARTBEAT_PATH, {"fired_at": old, "decision": "not_due", "reason": ""})
    assert st.read_heartbeat()["stale"] is True


def test_upcoming_rebalance_window():
    assert st.upcoming_rebalance("2026-11-18") == "2026-11-18"     # the day
    assert st.upcoming_rebalance("2026-11-17") == "2026-11-18"     # eve
    assert st.upcoming_rebalance("2026-11-16") == "2026-11-18"     # two sessions out
    assert st.upcoming_rebalance("2026-11-13") is None             # three sessions out (Fri -> Wed)
    assert st.upcoming_rebalance("2026-11-19") is None             # just after


def test_evaluate_and_notify_policy():
    ok = [{"name": "a", "ok": True, "detail": ""}]
    bad = [{"name": "a", "ok": True, "detail": ""}, {"name": "b", "ok": False, "detail": "x"}]
    assert st.evaluate(ok) == "ok" and st.evaluate(bad) == "fail"
    assert st.should_notify(None, "2026-11-18", "ok")
    prev = st.write_preflight("2026-11-18", "2026-11-17", ok, grid_bar_present=False, notified_status="ok")
    assert not st.should_notify(prev, "2026-11-18", "ok")          # same verdict, no repeat
    assert st.should_notify(prev, "2026-11-18", "fail")            # verdict changed
    assert st.should_notify(prev, "2026-12-18", "ok")              # new target


def test_recheck_when_grid_bar_lands_or_check_is_old():
    ok = [{"name": "a", "ok": True, "detail": ""}]
    prev = st.write_preflight("2026-11-18", "2026-11-17", ok, grid_bar_present=False, notified_status="ok")
    assert not st.recheck_due(prev, "2026-11-18", grid_bar_present=False)
    assert st.recheck_due(prev, "2026-11-18", grid_bar_present=True)
    prev["checked_at"] = (datetime.now(timezone.utc) - timedelta(seconds=st.PREFLIGHT_RECHECK_S + 1)).isoformat()
    assert st.recheck_due(prev, "2026-11-18", grid_bar_present=False)
