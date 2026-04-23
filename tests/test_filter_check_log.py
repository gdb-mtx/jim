"""Tests for `data/filter_check_log.py`.

Fixture strings mirror the real log format produced by
`scripts/filter_check.py` — exact prefixes, exact unicode arrow, exact
account-summary indentation.
"""

from datetime import datetime

from data.filter_check_log import (
    FilterCheckRun,
    parse_filter_check_log,
    latest_per_source,
)


NO_CHANGE_BLOCK = """2026-04-22 12:28:36,966 [INFO] ============================================================
2026-04-22 12:28:36,966 [INFO] FIRE Filter Check starting (source=launchd-crypto, scope=btc)
2026-04-22 12:28:37,712 [INFO] Filters computed in 0.7s: BTC=1.0 ($78962.22 vs MA $76978.05)
2026-04-22 12:28:37,712 [INFO] No filter changes detected
"""

FLIP_BLOCK = """2026-04-22 12:27:48,293 [INFO] ============================================================
2026-04-22 12:27:48,293 [INFO] FIRE Filter Check starting (source=launchd-crypto, scope=btc)
2026-04-22 12:27:49,997 [INFO] Filters computed in 1.7s: BTC=1.0 ($78967.74 vs MA $76978.09)
2026-04-22 12:27:49,997 [INFO] BTC filter changed: 0.0 → 1.0 (BULLISH)
2026-04-22 12:27:49,998 [INFO]   Account 4 (Crypto): rebalancing strategy=crypto_momentum_filtered
2026-04-22 12:27:49,998 [INFO]   Account 4: DRY RUN — skipping execution
2026-04-22 12:27:50,187 [INFO] Filter check complete: BTC → BULLISH
2026-04-22 12:27:50,187 [INFO]   Account 4: dry_run (0 orders)
"""

OLD_FORMAT_NO_SOURCE_BLOCK = """2026-04-13 21:37:08,345 [INFO] ============================================================
2026-04-13 21:37:08,345 [INFO] FIRE Filter Check starting
2026-04-13 21:37:08,393 [INFO] Filters computed in 0.0s: SPY=1.0 ($686.1 vs MA $661.39), BTC=0.0 ($69962.46 vs MA $94971.1)
2026-04-13 21:37:08,393 [INFO] No filter changes detected
"""

TRUNCATED_BLOCK = """2026-04-22 12:27:48,293 [INFO] ============================================================
2026-04-22 12:27:48,293 [INFO] FIRE Filter Check starting (source=manual, scope=all)
2026-04-22 12:27:49,997 [INFO] Filters computed in 1.7s: SPY=1.0 ($700 vs MA $665)
"""


def _write_log(tmp_path, *blocks):
    f = tmp_path / "filter_check.log"
    f.write_text("".join(blocks))
    return f


def test_parses_no_change_block(tmp_path):
    f = _write_log(tmp_path, NO_CHANGE_BLOCK)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    r = runs[0]
    assert r.source == "launchd-crypto"
    assert r.scope == "btc"
    assert r.outcome == "no_change"
    assert r.flips == []
    assert r.accounts == []
    assert r.started_at == datetime(2026, 4, 22, 12, 28, 36, 966_000)


def test_parses_flip_block(tmp_path):
    f = _write_log(tmp_path, FLIP_BLOCK)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    r = runs[0]
    assert r.outcome == "flip"
    assert r.flips == [
        {"filter": "btc", "from": 0.0, "to": 1.0, "direction": "BULLISH"}
    ]
    assert r.accounts == [
        {"account": 4, "status": "dry_run", "orders": 0}
    ]
    # Flip detected in a --dry-run block must be flagged so the timeline
    # can render it distinctly from production flips.
    assert r.is_dry_run is True


def test_is_dry_run_false_for_production_run(tmp_path):
    production_flip = """2026-04-22 16:57:12,059 [INFO] ============================================================
2026-04-22 16:57:12,065 [INFO] FIRE Filter Check starting (source=launchd-crypto, scope=btc)
2026-04-22 16:57:12,896 [INFO] Filters computed in 0.8s: BTC=1.0 ($78580 vs MA $76975)
2026-04-22 16:57:12,896 [INFO] BTC filter changed: 0.0 → 1.0 (BULLISH)
2026-04-22 16:57:13,000 [INFO] Filter check complete: BTC → BULLISH
2026-04-22 16:57:13,001 [INFO]   Account 4: executed (2 orders)
"""
    f = _write_log(tmp_path, production_flip)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    assert runs[0].is_dry_run is False
    assert runs[0].accounts == [
        {"account": 4, "status": "executed", "orders": 2}
    ]


def test_is_dry_run_true_for_harness_block(tmp_path):
    # The 2026-04-22 sandbox harness produced `blocked_by_harness` status —
    # a synthetic run, not a real flip. Flag it the same as dry_run so the
    # timeline visually groups both as "not production."
    harness = """2026-04-22 15:08:30,206 [INFO] ============================================================
2026-04-22 15:08:30,206 [INFO] FIRE Filter Check starting (source=manual, scope=btc)
2026-04-22 15:08:30,908 [INFO] Filters computed in 0.7s: BTC=1.0 ($78574 vs MA $76974)
2026-04-22 15:08:30,908 [INFO] BTC filter changed: 0.0 → 1.0 (BULLISH)
2026-04-22 15:08:31,095 [INFO] Filter check complete: BTC → BULLISH
2026-04-22 15:08:31,095 [INFO]   Account 4: blocked_by_harness (0 orders)
"""
    f = _write_log(tmp_path, harness)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    assert runs[0].is_dry_run is True
    assert runs[0].accounts == [
        {"account": 4, "status": "blocked_by_harness", "orders": 0}
    ]


def test_is_dry_run_false_for_no_change_run(tmp_path):
    f = _write_log(tmp_path, NO_CHANGE_BLOCK)
    runs = parse_filter_check_log(f)
    # No accounts section (no rebalance occurred); is_dry_run stays False.
    assert runs[0].is_dry_run is False


def test_parses_multi_block_log(tmp_path):
    # Two runs back-to-back — no_change then flip.
    f = _write_log(tmp_path, NO_CHANGE_BLOCK, FLIP_BLOCK)
    runs = parse_filter_check_log(f)
    assert len(runs) == 2
    assert runs[0].outcome == "no_change"
    assert runs[1].outcome == "flip"
    # Chronological order preserved (file order).
    assert runs[0].started_at < runs[1].started_at or \
        runs[0].started_at == datetime(2026, 4, 22, 12, 28, 36, 966_000)


def test_tolerates_old_format_without_source_scope(tmp_path):
    f = _write_log(tmp_path, OLD_FORMAT_NO_SOURCE_BLOCK)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    r = runs[0]
    assert r.source == "unknown"
    assert r.scope == "unknown"
    assert r.outcome == "no_change"


def test_truncated_block_does_not_raise(tmp_path):
    # Header present, no outcome line. Parser must return the run with
    # outcome="error" rather than crashing or omitting it.
    f = _write_log(tmp_path, TRUNCATED_BLOCK)
    runs = parse_filter_check_log(f)
    assert len(runs) == 1
    assert runs[0].outcome == "error"


def test_unparseable_junk_returns_empty(tmp_path):
    f = tmp_path / "filter_check.log"
    f.write_text("nothing here looks like a log line\nnor does this\n")
    runs = parse_filter_check_log(f)
    assert runs == []


def test_missing_file_returns_empty(tmp_path):
    f = tmp_path / "nonexistent.log"
    runs = parse_filter_check_log(f)
    assert runs == []


def test_latest_per_source_picks_newest(tmp_path):
    # Two runs under same source: latest_per_source returns the later one.
    older = """2026-04-22 08:00:00,000 [INFO] ============================================================
2026-04-22 08:00:00,000 [INFO] FIRE Filter Check starting (source=launchd-crypto, scope=btc)
2026-04-22 08:00:00,500 [INFO] Filters computed in 0.5s: BTC=1.0 ($78000 vs MA $76000)
2026-04-22 08:00:00,500 [INFO] No filter changes detected
"""
    newer = """2026-04-22 12:00:00,000 [INFO] ============================================================
2026-04-22 12:00:00,000 [INFO] FIRE Filter Check starting (source=launchd-crypto, scope=btc)
2026-04-22 12:00:00,500 [INFO] Filters computed in 0.5s: BTC=1.0 ($79000 vs MA $76000)
2026-04-22 12:00:00,500 [INFO] No filter changes detected
"""
    f = _write_log(tmp_path, older, newer)
    runs = parse_filter_check_log(f)
    latest = latest_per_source(runs)
    assert "launchd-crypto" in latest
    assert latest["launchd-crypto"].started_at == datetime(2026, 4, 22, 12, 0, 0, 0)


def test_stray_non_header_lines_ignored(tmp_path):
    # Emulate the 2026-04-20 14:53:42 orphan in the real log (an
    # `Account N: rebalancing` line not preceded by a separator). Parser
    # should skip these, not explode.
    content = NO_CHANGE_BLOCK + """2026-04-20 14:53:42,146 [INFO]   Account 4 (Crypto): rebalancing strategy=crypto_momentum_filtered
2026-04-20 14:53:42,147 [WARNING]   Account 4: locked by another process — skipping
""" + FLIP_BLOCK
    f = tmp_path / "filter_check.log"
    f.write_text(content)
    runs = parse_filter_check_log(f)
    # Two clean runs, orphan lines absorbed into the preceding block but
    # don't corrupt it (outcome stays `no_change`).
    assert len(runs) == 2
    assert runs[0].outcome == "no_change"
    assert runs[1].outcome == "flip"


def test_tail_bytes_honored(tmp_path):
    # Write many blocks so the file exceeds the tail cap, then parse with
    # a tight cap. Only the last few should come back.
    # Use minute offsets (00-39) to keep timestamps valid.
    f = tmp_path / "filter_check.log"
    with open(f, "w") as out:
        for i in range(40):
            block = NO_CHANGE_BLOCK.replace("12:28:36", f"12:{i:02d}:36")
            block = block.replace("12:28:37", f"12:{i:02d}:37")
            out.write(block)
    # Tail cap of 2000 bytes covers roughly the last 6-7 blocks.
    runs = parse_filter_check_log(f, tail_bytes=2000)
    assert 0 < len(runs) < 20
    # Full file parse should return all 40.
    full = parse_filter_check_log(f, tail_bytes=10_000_000)
    assert len(full) == 40
