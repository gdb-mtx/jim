# FIRE Automation — A4 (Crypto) Daily Rebalance

This document describes the full picture of how Account 4's daily rebalance
is automated: what runs automatically, what requires the server to be up,
what the fallback layers are, and what manual actions (if any) you need to
take day-to-day.

## What's automated

**An APScheduler job fires daily at 00:05 UTC** (= 8:05 PM ET during EDT,
7:05 PM ET during EST). It's defined in [api/main.py:250-259](api/main.py#L250-L259)
as part of the FastAPI lifespan — meaning it only runs while the uvicorn
process is alive. The scheduler instance is held at module scope so the
Ops dashboard (see below) can introspect jobs + last-run state without
re-starting the scheduler.

On each tick, [_daily_crypto_rebalance()](api/main.py#L54) runs the
following steps:

1. `require_validated(4)` — checks `data/risk_state/validation_state.json`,
   skips if A4's record isn't passing or has expired.
2. Acquires the per-account rebalance lock (async + file lock, prevents
   concurrent trades from other entry points).
3. `compute_rebalance(strategy_id="crypto_momentum_filtered")` — ranks the
   9 coins in the universe by 21d momentum, picks top 2, applies the BTC
   125d SMA trend filter, applies the vol-scaling overlay.
4. Checks for price staleness (>2% drift between cached and live Alpaca
   quotes).
5. Submits orders through the same `execute_rebalance` path that the
   dashboard uses manually — including the crypto-specific notional
   sizing and `time_in_force="gtc"` plumbing.
6. Takes a daily snapshot for A4.
7. Journals everything to `data/rebalance_log.jsonl` with `source="scheduled"`.
8. Retries up to 3× with exponential backoff on failure (60s, then 120s).

**The catch: the server must be running at 00:05 UTC.** APScheduler lives
inside the uvicorn process. If your laptop is asleep or the server is
down at 8:05 PM ET, the job silently does not fire. No trade happens that
day. This is a known operational gap — see `DEPLOYMENT_PLAN.md` for the
Fly.io cloud migration plan that closes it.

## What to expect day-to-day

- **Most days**: tiny adjustment trades. Prices move, so the 50/50 weight
  drifts slightly. The system trims the overweight coin and tops up the
  underweight one. Dollar amounts are small (fractions of 1%).
- **Day where the top 2 change** (e.g. SOL overtakes ETH): full swap.
  Sell the loser, buy the new winner. Larger turnover for that one day.
- **BTC drops below the 125d MA**: filter goes to 0.0, the strategy
  rotates everything to cash.
- **BTC crosses back above**: filter goes to 1.0, full redeploy into the
  current top 2. If the server is up overnight, this happens automatically.

## Backup layer: the launchd filter monitor

Separate from the APScheduler job, [scripts/filter_check.py](scripts/filter_check.py)
runs via macOS launchd. **This runs even when the server is down** —
it is a separate process launched by launchd, not a thread inside
uvicorn.

Its job is narrow: detect BTC or SPY filter *flips*. It fires on a
schedule, but the rebalance only runs when the newly computed filter
scalar differs from the last-saved scalar in
`data/risk_state/filter_state.json`. Most runs log
`"No filter changes detected"` and exit. On a flip run, it calls
`rebalance_account()` — which internally calls the *same*
`compute_rebalance()` function APScheduler uses. That means a
launchd-triggered rebalance does the full pipeline: signal ranking
(top 2 by 21d momentum for crypto), filter application, vol-scaling,
and order generation. It is **not** an "exposure-only" tweak.

### Two plists, two cadences

The filter monitor is split into two launchd jobs, each with a
`--filter` scope:

- **Equity** ([scripts/com.fire.filter-check-equity.plist](scripts/com.fire.filter-check-equity.plist))
  — runs once daily at 4:30 PM laptop-local time, invokes
  `filter_check.py --filter spy`. Only computes the SPY 200d MA
  filter, only considers rebalancing A1/A2 on flip.
- **Crypto** ([scripts/com.fire.filter-check-crypto.plist](scripts/com.fire.filter-check-crypto.plist))
  — runs every 4 hours (`StartInterval=14400`), invokes
  `filter_check.py --filter btc`. Only computes the BTC 125d SMA
  filter, only considers rebalancing A4 on flip. 4-hour cadence
  matches crypto's 24/7 nature — a BTC cross can be caught within
  ~4 hours instead of waiting for a single end-of-NYSE run.

Both jobs set `FIRE_FILTER_CHECK_SOURCE` via launchd env vars
(`launchd-equity` and `launchd-crypto`) so the log distinguishes
scheduled vs manual invocations. A terminal run without the env var
logs `source=manual`.

Both jobs also pass `force_refresh=True` to yfinance under the hood —
filter decisions are never made against a stale cached price. The
16-hour cache TTL still applies to the API/dashboard consumers, so
this has no impact on other code paths.

### Trigger vs work-done distinction

| Layer | Trigger | Work done when triggered | Requires server? |
|---|---|---|---|
| APScheduler (in uvicorn) | Fires every day at 00:05 UTC, unconditionally | Full rebalance on A4: signal + filter + vol scaling | Yes |
| Filter monitor — equity (launchd) | Fires at 4:30 PM laptop-local daily; rebalance only if SPY scalar differs from saved state | Full rebalance on A1/A2 (same `compute_rebalance` path) | No |
| Filter monitor — crypto (launchd) | Fires every 4 hours; rebalance only if BTC scalar differs from saved state | Full rebalance on A4 (same `compute_rebalance` path) | No |

The crypto filter monitor is the safety net for the scenario that
matters most: a BTC filter *flip* happening while the server was
down. Worst-case detection lag is ~4 hours, not 24+.

### Closing the double-rebalance gap

After any successful rebalance, the writer updates
`data/risk_state/filter_state.json` with the BTC scalar it traded
against. This is done by:

- `filter_check.py` directly (via the shared `data/filter_state.py`
  module), and
- the APScheduler job in `api/main.py` (added 2026-04-22) after
  `_daily_crypto_rebalance` completes successfully.

The write is serialized by a `fcntl` file lock, so concurrent writers
(the two plists + APScheduler) cannot race. This closes the
double-rebalance gap: if APScheduler at 00:05 UTC already acted on a
BTC flip, the next crypto filter monitor run sees `btc_scalar` already
matches live and exits as a no-op — no duplicate trade on the flip
day. Symmetric for the reverse case (launchd fires first).

### Solved oddity (2026-04-22) — the pre-3acc646 dry-run write

**Solved 2026-04-22 evening.** On 2026-04-22 at 12:27:49 MDT, `filter_state.json`
was written (btc_scalar 0.0 → 1.0, `last_btc_flip` stamped — field
was named `last_btc_change` at the time, renamed later that day).
Initial investigation couldn't attribute it — see `git log --follow`
for the detective work.

**Root cause:** pre-`3acc646` `filter_check.py` had an
unconditional `save_state(current)` call at the end of the
flip-detection branch (original commit `a710ac2`:292). Dry-runs
correctly skipped order submission but **still wrote state**. On a
`--dry-run --filter btc` invocation with a detected flip, the script
would log "DRY RUN — skipping execution" (correct) but then persist
`current` to `filter_state.json` (bug), stamping `last_btc_change = now`.

- Commit `3acc646` (2026-04-22 12:54:23 MDT) added the
  `if not args.dry_run:` gate that fixes this — 27 minutes after the
  mystery write at 12:27:49 MDT.
- The dry-run at 12:27:49 was running the old buggy code; the gates
  in sandbox-verified code today only exist in the post-`3acc646`
  version.

**Side effects:** only cosmetic — the written value (btc_scalar=1.0)
matched what the next real-code run would have computed anyway, so
A4 automation wasn't misled. The sole confusing artifact was the
phantom `last_btc_change` timestamp we spent an afternoon chasing.

**Defense against recurrence:** the gate exists, and both new launchd
plists set `FIRE_FILTER_CHECK_SOURCE` env vars, so any launchd-triggered
run tags itself `launchd-crypto` or `launchd-equity` in
`data/filter_check.log`. Any future "where did this write come from?"
question can cross-reference:
- `data/filter_check.log` (user + launchd filter_check.py runs with
  source tags)
- `data/filter_check_stderr.log` / `_stdout.log` (launchd stderr/stdout)
- `data/rebalance_log.jsonl` (`source=scheduled` → APScheduler wrote)
- uvicorn server log (APScheduler `_daily_crypto_rebalance` entry/exit)

Lesson: always `git log --follow` the file whose behavior is confusing
before assuming a deep bug in the current code.

## What you have to do

**Nothing, as long as the server stays up overnight.** Keep uvicorn
running, laptop plugged in and awake, and the 00:05 UTC rebalance
happens hands-free.

### To verify the job fired (the next morning)

1. Open the **Ops** dashboard tab — the Scheduler Panel shows
   APScheduler's `daily_crypto_rebalance` job with its last-run /
   next-run and status (success / skipped / failed). The Event
   Timeline below lists the scheduled rebalance alongside any filter
   flips.
2. Or, from the CLI: grep `data/rebalance_log.jsonl` for a fresh entry
   with `"source": "scheduled"` and `"account": 4`.
3. Server logs still emit `"Daily crypto rebalance complete"` on success.

### If the server was down at 00:05 UTC

If you realize the next morning that the server was off overnight: just
restart it and manually hit Execute on the A4 rebalance panel — same
path as a manual first-time entry. You are at most one day late on the
signal.

## Practical overnight checklist

1. `./scripts/start.sh` is running (backend + frontend both up).
2. Laptop plugged in and stays awake past 8:05 PM ET.
3. The next morning: check `data/rebalance_log.jsonl` for the scheduled
   entry.
4. Expect small drift trades (not a full swap) on any given day where
   the top 2 coins remain the same.

## Installing / reinstalling launchd

First-time install, or when migrating from the old single plist:

```
# Remove the old single plist, if present
launchctl unload ~/Library/LaunchAgents/com.fire.filter-check.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.fire.filter-check.plist

# Copy the two new plists in and load them
cp scripts/com.fire.filter-check-equity.plist scripts/com.fire.filter-check-crypto.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fire.filter-check-equity.plist
launchctl load ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist

# Verify
launchctl list | grep fire
```

To uninstall both:
```
launchctl unload ~/Library/LaunchAgents/com.fire.filter-check-equity.plist \
                 ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist
```

Manual invocation (any scope):
```
uv run python3 scripts/filter_check.py --filter all --dry-run   # check everything, no trades
uv run python3 scripts/filter_check.py --filter btc             # crypto-only real run
uv run python3 scripts/filter_check.py --filter spy             # equity-only real run
```

## Related files

- [api/main.py](api/main.py) — APScheduler job definition (lifespan
  context + `_daily_crypto_rebalance`); writes `filter_state.json`
  after each successful A4 rebalance.
- [scripts/filter_check.py](scripts/filter_check.py) — launchd filter
  monitor (scope-aware via `--filter`)
- [scripts/com.fire.filter-check-equity.plist](scripts/com.fire.filter-check-equity.plist)
  — SPY filter, 4:30 PM laptop-local daily
- [scripts/com.fire.filter-check-crypto.plist](scripts/com.fire.filter-check-crypto.plist)
  — BTC filter, every 4 hours
- [data/filter_state.py](data/filter_state.py) — shared accessor for
  `filter_state.json` (load + atomic update with `fcntl` file lock);
  used by both `filter_check.py` and APScheduler
- [execution/rebalance.py](execution/rebalance.py) — shared
  `compute_rebalance` / `execute_rebalance` path used by both the
  scheduler and the manual dashboard button
- [execution/validation_gate.py](execution/validation_gate.py) — gate
  that blocks rebalance for accounts lacking a passing validation
  record
- [api/locks.py](api/locks.py) — per-account locks that serialize the
  three entry points (API, scheduler, launchd cron)
- `data/risk_state/validation_state.json` — per-account validation
  status; scheduler skips if A4 is not passing
- `data/risk_state/filter_state.json` — current SPY/BTC scalars +
  last-flip timestamps; written by both filter_check.py and APScheduler
- `data/rebalance_log.jsonl` — structured audit log of every rebalance
  event (manual, scheduled, and filter-monitor-triggered)
- `DEPLOYMENT_PLAN.md` — plan to migrate the scheduler to 24/7 cloud
  hosting so the "laptop must be awake" constraint goes away
- `OPS_DASHBOARD_PLAN.md` + Ops dashboard tab — built 2026-04-22
  (commits `79b957e` backend, `8f23750` frontend, `6b0d78b` cleanup).
  Single pane covering APScheduler jobs + launchd filter monitors +
  validation status + a merged rebalance / filter-flip event timeline.
  Endpoints at `/api/ops/*`; panels under
  [dashboard/src/components/ops/](dashboard/src/components/ops/).
  Will absorb cloud-scheduler status post-Fly migration.
