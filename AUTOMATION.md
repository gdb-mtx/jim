# FIRE Automation — A4 (Crypto) Daily Rebalance + Filter Monitors

This document describes how Account 4's daily rebalance and the SPY/BTC filter
monitors are automated: what runs automatically, the fallback layers, and what
manual actions (if any) you take day-to-day.

**Scheduler: cron.** Migrated from launchd on 2026-05-28 (see "History" at the
bottom — macOS Background Task Management kept silently disabling the launchd
agents). Before launchd it was an in-process APScheduler job, retired
2026-05-05. The Python scripts are unchanged across all three eras; only the
thing that fires them changed.

## What's automated

Three cron entries (system crontab — `crontab -l`). **Cron fires at
laptop-local wall-clock time and the laptop travels** — so no time-of-day
invariant lives in the crontab. The daily rebalance entry is an hourly *trigger*;
the script itself decides (in UTC) whether today's run is due:

```
# Daily crypto rebalance (A4): hourly trigger; script runs at most once per
# UTC day via --if-due (first awake hour after 00:00 UTC)
10 * * * *             ~/.fire-cron/cron_crypto_rebalance.sh

# Filter check — SPY (A1/A2): every 4h on the hour
0 0,4,8,12,16,20 * * * ~/.fire-cron/cron_filter_check.sh spy

# Filter check — BTC (A4): every 4h, offset 5 min
5 1,5,9,13,17,21 * * * ~/.fire-cron/cron_filter_check.sh btc
```

**Why hourly + `--if-due` instead of a fixed daily minute (failure mode #5,
diagnosed 2026-06-09).** The original `5 20 * * *` entry encoded "00:05 UTC"
as "8:05 PM ET" — correct only while the system TZ was EDT. When the laptop
moved to MDT (UTC-6), the same entry silently fired at 02:05 UTC; worse, three
consecutive days were skipped entirely because the laptop was asleep at the
one daily fire minute (cron has no catch-up). The fix moves the invariant into
the script: cron fires `cron_crypto_rebalance.sh` every hour at :10, the
wrapper passes `--if-due`, and the script exits silently unless
`data/risk_state/daily_rebalance_state.json` shows today's UTC date hasn't run
yet. Net effect: the run lands on the **first awake hour after UTC midnight**,
in any timezone, and a failed run is retried the next hour instead of giving up
until tomorrow. Signal parity holds for late runs — the strategy reads settled
daily bars, so the computed weights are identical at 00:10 or 14:10 UTC. The
:10 minute avoids the rebalance-lock collision with the :05 BTC filter check.
(macOS cron is Vixie 3.0 with no `CRON_TZ` support, so pinning the schedule to
UTC wasn't an option — and wouldn't have fixed the sleep-skip anyway.)

Each entry runs a thin bash wrapper because cron gives a process almost no
environment. The wrappers set `HOME`, `cd` into the project, invoke `uv` by
absolute path (`/Users/george/.local/bin/uv`), and redirect output to
`data/*_stdout.log` / `data/*_stderr.log`. The filter wrapper also sets
`FIRE_FILTER_CHECK_SOURCE=cron-spy` / `cron-btc` so the log distinguishes
scheduled runs from manual ones (a terminal run with no env var logs
`source=manual`). **The server does not need to be running** — the wrappers
call the scripts directly.

**Why the wrappers live in `~/.fire-cron/`, not in `scripts/` (TCC, diagnosed
2026-05-29).** The repo is the canonical source of the wrappers
(`scripts/cron_*.sh`, version-controlled), but cron runs *deployed copies* from
`~/.fire-cron/`. Reason: the project lives under `~/Desktop`, a TCC-protected
location. With Full Disk Access granted to `/usr/sbin/cron`, cron can read and
launch a wrapper from `~/Desktop` — but the spawned process is then tainted by
its `~/Desktop` provenance, and `uv`'s `getcwd()` on the `~/Desktop` working
directory is denied with the bare error `Current directory does not exist`
(before Python even starts — no traceback, no log). The *identical* wrapper run
from outside `~/Desktop` works perfectly. FDA is necessary (pre-FDA cron can't
read the wrapper at all) but **not sufficient** — the wrapper's own location
must be outside the protected tree. Confirmed by running byte-identical wrappers
from `~/Desktop` (fails every fire) and `/tmp` (succeeds every fire) in the same
minutes. **Redeploy after editing a wrapper:**
`cp scripts/cron_*.sh ~/.fire-cron/`. (The wrappers are static, so this is
rare.) The durable fix remains getting the project out of `~/Desktop` entirely
(Fly.io — see `DEPLOYMENT_PLAN.md`).

The daily run lands shortly after 00:00 UTC (the crypto trading-day boundary)
whenever the laptop is awake then, and otherwise on the first awake hour after.
The strategy uses 21d crypto momentum on settled daily bars, so the exact hour
within the UTC day doesn't change the computed weights.

### The daily rebalance pipeline

On each fire, [`scripts/daily_crypto_rebalance.py`](scripts/daily_crypto_rebalance.py)
runs:

1. `require_validated(4)` — checks `data/risk_state/validation_state.json`,
   skips if A4's record isn't passing or has expired.
2. Acquires the per-account file rebalance lock (cross-process, non-blocking
   via `fcntl` — serializes against the API and the filter cron).
3. `compute_rebalance("crypto_momentum_filtered")` — ranks the 9-coin universe
   by 21d momentum, picks top 2, applies the BTC 125d SMA trend filter, applies
   the vol-scaling overlay.
4. Reconciles broker positions against saved `expected_positions`; **skips** on
   a large mismatch (journals the skip with
   `execute_error="position_reconciliation_failed"`).
5. Checks price staleness (>2% drift between cached and live Alpaca quotes).
6. Submits orders through the same `execute_rebalance` path the dashboard uses
   (crypto notional sizing, `time_in_force="gtc"`).
7. Takes a daily snapshot for A4.
8. Journals to `data/rebalance_log.jsonl` with `source="scheduled"`.
9. Syncs `filter_state.json` with the live BTC scalar so the filter monitor
   doesn't later fire a no-op rebalance from a stale value.
10. Retries up to 3× with exponential backoff (60s, then 120s) on failure.

### ⚠ Cron does not catch up missed fires

launchd's `StartCalendarInterval` queued a missed fire during darkwake and ran
it on the next FullWake. **Cron does neither** — if the laptop is asleep, off,
or offline at the scheduled minute, that fire is simply skipped. There is no
deferred catch-up.

How each job absorbs this:
- **Daily A4 rebalance** → self-healing since 2026-06-09: the hourly
  `--if-due` trigger means a sleep gap delays the run to the first awake hour
  of the UTC day instead of skipping the day. A full laptop-dark *day* still
  skips (21d momentum tolerates a one-day rotation gap — noise).
- **Laptop asleep across a filter flip** → the real exposure. While asleep, the
  4h filter checks don't run either, so a BTC cross-down isn't acted on until
  the laptop is awake at the *next* scheduled cron minute (the next slot — not
  a catch-up of the missed ones).

Mitigations in place:
- The 4h filter cadence means that *while the laptop is awake*, a flip is caught
  within ~4h.
- The Ops panel flags the daily rebalance as **stale if it hasn't fired in
  >26h** (sourced from `daily_rebalance.log`) — a silent miss surfaces instead
  of being discovered by accident.
- The travel watcher (below) pushes a phone alert on a flip when the laptop is
  fully off.

## What to expect day-to-day

- **Most days**: tiny adjustment trades as the 50/50 weight drifts. Dollar
  amounts are small (fractions of 1%).
- **Top-2 change** (e.g. SOL overtakes ETH): full swap — sell the loser, buy the
  new winner. Larger turnover that one day.
- **BTC drops below the 125d MA**: filter → 0.0, strategy rotates to cash.
- **BTC crosses back above**: filter → 1.0, redeploy into the current top 2.

## Filter monitors

Separate from the daily rebalance, [`scripts/filter_check.py`](scripts/filter_check.py)
runs every 4h via cron to detect BTC or SPY filter *flips*. It is
server-independent (a separate process, not a uvicorn thread). It fires on
schedule but rebalances only when the newly computed scalar differs from the
last-saved scalar in `data/risk_state/filter_state.json`. Most runs log
`"No filter changes detected"` and exit. On a flip it calls `rebalance_account()`,
which runs the *same* `compute_rebalance()` full pipeline (signal ranking +
filter + vol-scaling) — **not** an exposure-only tweak.

Two scopes, both on the 4h cadence:
- **`cron_filter_check.sh spy`** — SPY 200d MA filter; rebalances A1/A2 on flip.
  (Under launchd this ran once daily at 4:30 PM; cron runs it every 4h now —
  harmless, since SPY only moves on trading days and off-hours checks are no-ops.)
- **`cron_filter_check.sh btc`** — BTC 125d SMA filter; rebalances A4 on flip.
  The 4h cadence matches crypto's 24/7 nature — a cross is caught within ~4h
  instead of waiting for the next daily fire.

Both pass `force_refresh=True` to the data layer — filter decisions are never
made against a stale cached price.

### Trigger vs work-done

| Layer | Trigger | Work when triggered | Needs server? | Needs laptop awake? |
|---|---|---|---|---|
| Daily rebalance (cron) | Hourly at :10; runs at most once per UTC day (`--if-due`). Sleep delays to first awake hour, doesn't skip. | Full A4 rebalance: signal + filter + vol-scaling | No | Yes (any hour that UTC day) |
| Filter monitor — SPY (cron) | Every 4h; rebalance only if SPY scalar changed | Full A1/A2 rebalance (same `compute_rebalance`) | No | Yes |
| Filter monitor — BTC (cron) | Every 4h; rebalance only if BTC scalar changed | Full A4 rebalance (same `compute_rebalance`) | No | Yes |
| Travel watcher (GitHub Actions) | Every ~30 min at `:07/:37` UTC | **Notifies phone only** (ntfy on cross + daily heartbeat) — does not trade | No | No |

The BTC filter monitor is mostly redundant with the daily rebalance (both call
`compute_rebalance` for A4); its remaining role is catching a mid-day BTC flip
within ~4h instead of waiting up to 24h for the next daily fire.

### filter_state.json writers (closing the double-rebalance gap)

After any successful rebalance, the writer updates `filter_state.json` with the
scalar it traded against. Three writers, all `fcntl`-locked via
[`data/filter_state.py`](data/filter_state.py):

- `filter_check.py` (cron) — writes BTC + SPY scalars after a flip-triggered
  rebalance.
- `scripts/daily_crypto_rebalance.py` (cron) — writes `btc_scalar` after the
  daily fire, via `_sync_btc_filter_state` (which writes **the scalar only**,
  not `btc_price`/`btc_ma125` — so after a daily fire those two fields can lag
  until the next full `filter_check.py` run; the scalar is the field that gates
  trading).
- `/api/orders/rebalance/execute` in `api/routes/orders.py` — writes scalars for
  manual rebalances. Matters most during travel: when the watcher pings your
  phone and you open the laptop to press Execute, the state stays fresh without
  cron having to run.

Serialized via `fcntl` so concurrent updates can't race. If the daily fire
already acted on a BTC flip, the next 4h filter check sees the scalar already
matches and exits as a no-op — no duplicate trade.

**Subtlety (fixed 2026-04-23):** both the daily script and the manual endpoint
**recompute the filter live** instead of reading `result.btc_filter_scalar`.
The `crypto_momentum_filtered` config sets `btc_filter=False` at the portfolio
level (the filter is internal to CryptoMomentum, to avoid double-filtering),
which leaves `result.btc_filter_scalar` at its default `1.0` even when BTC is
below the MA. A related seam was fixed 2026-05-28: the strategy's *internal* BTC
filter was reading yesterday's close because the C9 partial-bar drop hid today's
live-augmented price from it — it now forwards today's live decision to the last
signal date. See `HISTORY.md`.

**Forensic note (2026-04-22):** a phantom `filter_state.json` write was traced
to pre-`3acc646` `filter_check.py`, which persisted state even on `--dry-run`.
The `if not args.dry_run:` gate (commit `3acc646`) fixed it. Lesson:
`git log --follow` the file whose behavior is confusing before assuming a deep
bug in the current code.

## Travel-window safety net: GitHub Actions + ntfy.sh

Added 2026-04-23. The cron filter monitor still needs the laptop to be awake —
a digital-nomad day where the laptop spends 24h in a bag means cron misses the
SPY/BTC check and the 8:05 PM ET rebalance entirely (cron does not catch up).
This is the failure mode that matters most when traveling: **an undetected BTC
filter flip during a multi-day trip could leave A4 fully exposed through the
start of a crypto bear market.**

To cover that gap, a GitHub Actions workflow polls BTC and SPY prices every ~30
minutes, compares them to MA thresholds checked into the repo, and pushes a
phone notification via [ntfy.sh](https://ntfy.sh) on a state transition (above
↔ below MA). The runner is in GitHub's infrastructure, so it runs regardless of
laptop state.

### Architecture

| Component | File | Role |
|---|---|---|
| Cron runner | [.github/workflows/filter_watch.yml](.github/workflows/filter_watch.yml) | GitHub-hosted schedule, fires at `7,37 * * * *` UTC (off-peak slots — `*/30` fires at the most congested moments per GitHub's docs) |
| Checker script | [scripts/watch_filters.py](scripts/watch_filters.py) | Stdlib only (no uv install needed in the runner). Fetches BTC from CoinGecko (free, no key) and SPY from Alpaca, compares to thresholds, pushes ntfy on crossing |
| Thresholds | [scripts/filter_watch_thresholds.json](scripts/filter_watch_thresholds.json) | `btc_125_ma` + `spy_200_ma`, refreshed before each trip by `travel_prep.sh` |
| State cache | `scripts/filter_watch_state.json` (not committed — persisted across runs via `actions/cache@v4`) | `last_btc_above` / `last_spy_above` so a crossing alert fires once, not every 30 min |
| Pre-travel helper | [scripts/travel_prep.sh](scripts/travel_prep.sh) | Copies today's MAs from `filter_state.json` into the watcher's threshold file, commits, pushes. Refuses to run off `main` or with unrelated uncommitted changes |

### Three kinds of notifications

| Trigger | Priority | When | Purpose |
|---|---|---|---|
| **Crossing** (above → below, below → above) | `high` (bypasses DND) | First cron tick that observes the transition | Wake the user — open the laptop within ~2h and rebalance |
| **Daily heartbeat** | `low` (silent in-app) | One tick per UTC day in the 14:00-14:30 window | "System alive" confirmation when nothing has crossed |
| **Manual `workflow_dispatch` test** | `default` | Anytime via GitHub UI with `force_test=true` | Verify end-to-end pipeline health |

Heartbeat de-dup: `last_heartbeat_date` in the state cache.

### Travel-day flow

1. **Pre-travel**: `bash scripts/travel_prep.sh` refreshes MA thresholds and
   pushes. The watcher picks up new thresholds on its next run (within 30 min).
2. **Laptop goes dark** (plane, hotel Wi-Fi off). No cron. The GitHub runner
   keeps polling every ~30 min.
3. **Daily 14:00 UTC**: phone gets a quiet heartbeat ("all green, BTC $X above
   MA, SPY $Y above MA").
4. **Crossing happens**: phone buzzes with a high-priority ntfy within 0-30 min,
   bypassing DND.
5. **User opens laptop within ~2h**, opens the dashboard, clicks Preview →
   Execute on the affected account. The `filter_state` sync keeps everything
   consistent so post-travel cron runs don't misdetect.
6. **Daily A4 rotation**: just open the laptop at some point each travel day —
   the hourly `--if-due` trigger runs the day's rebalance at the next :10 with
   no manual step. 21d momentum barely shifts intraday — a late-in-the-day run
   vs 00:10 UTC is well inside the noise.

### What it doesn't cover

- **It does not trade.** It only notifies. If you can't open the laptop within
  ~24h of a crossing, A4 sits in its old positions through a bear start. Bounded
  by design — the real fix for 24/7 unattended trading is the Fly.io deployment
  in `DEPLOYMENT_PLAN.md`.
- **GitHub Actions scheduled triggers have a warm-up delay** on new workflows
  (~2.5h was observed once on first activation) and may be delayed at `:00`/`:30`
  under load — which is why we use `:07`/`:37`.

### Pre-travel one-command

```
bash scripts/travel_prep.sh
```

Safe to run repeatedly (no-op when thresholds haven't drifted).

### GitHub secrets (one-time)

In repo Settings → Secrets: `NTFY_TOPIC` (your subscribed topic), and
`ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (any account's data-API creds — A1's are
fine) to fetch the SPY trade.

### Verifying the watcher

```
gh run list --workflow filter_watch.yml --limit 10
gh run view <run-id> --log | grep "crossings\|Sent"
```

Or the GitHub Actions tab in VS Code → `filter_watch` workflow.

> **Travel + TZ:** cron follows the system timezone, which macOS updates on
> arrival. This is exactly why the daily entry is an hourly trigger with the
> UTC due-check in the script — a fixed local fire minute silently drifts off
> 00:05 UTC on travel (the 2026-06-09 incident). The 4h filter cadence is
> phase-shifted by a TZ change but its frequency is unchanged, so it needs no
> special handling. (The old launchd TZ-cache-requires-reboot gotcha no longer
> applies — it was specific to PID-1 launchd caching the boot-time zone.)

## Alert signals — operator runbook (added 2026-07-18)

The 4h SPY filter run computes two **alert-only** signals on top of the
trade-triggering filters. They notify (macOS) and persist to
`filter_state.json`; they never place trades. These are the only two
automations that ask for a human decision.

**"FIRE Tail Signal"** — VIX9D/VIX3M crosses 1.10 (deep backwardation =
crash posture; historically long-vol pays ~+14%/day on SPY's worst days).
*Your standing decision when it fires:* buy the insurance or not — ~5% of
book into VIXY while the ratio stays ≥ 1.10, sell on exit signal. Costs
premium in false alarms; pays multiples in real crashes. Numbers in
`docs/research/EVENT_KILLTESTS_JUL2026.md`.

**"FIRE Macro Composite"** — five price-based stress sensors (credit
HYG/IEF, dollar UUP, VIX curve, S&P breadth, XLU/SPY rotation) vote every
run; alert fires when the count crosses 2 in either direction. Led the
SPY-200d filter by 34-56 days in 2018/2020/2022. *What to do:* storm
warning, not fire alarm — the book de-risks itself; tighten attention,
skip discretionary risk-adds. **3+ votes AND Tail Signal on = the
strongest "buy VIXY now" configuration.** Deliberately not wired to trade
(pre-registered eval rejected it: `docs/research/MACRO_COMPOSITE_EVAL.md`).

Current state of both is always visible in `data/risk_state/filter_state.json`
(`vix_ratio`, `vix_backwardation`, `macro_votes`, `macro_scalar`, per-sensor
fields) and in the filter_check log lines.

## Monitoring health (Ops dashboard)

The **Ops** tab → Scheduler panel surfaces two health signals:

- **Entries present** — parses `crontab -l` for the three expected wrappers; red
  banner ("Scheduled jobs missing") if any are absent.
- **Staleness** — flags the daily rebalance if its last fire (the
  `Daily crypto rebalance starting` line in `daily_rebalance.log`) is **>26h**
  old: the case where the entry exists but the job silently stopped firing (the
  2026-05-28 BTM failure mode). Red banner: "Scheduler stopped firing". Sourced
  from the run log, **not** the trade journal, so cash / no-trade days (which
  don't journal) never false-positive.

## What you have to do

**Nothing, as long as the laptop is awake at some point each UTC day.** Cron
fires the scripts independently of the server, and the hourly `--if-due`
trigger runs the daily rebalance on the first awake hour after 00:00 UTC. Only
a full laptop-dark UTC day skips a rotation; the strategy tolerates a one-day
gap, and the Ops staleness banner flags a longer outage.

### Verify the daily job fired (next morning)

1. **Ops** tab → Scheduler panel — last-run / next-run / status for the daily
   rebalance, plus the merged event timeline.
2. CLI: grep `data/rebalance_log.jsonl` for a fresh `"source": "scheduled"`,
   `"account": 4` entry.
3. Tail `data/daily_rebalance.log` for `"Daily crypto rebalance starting"` +
   `"Final outcome: ..."`.

### During travel (laptop off for days)

1. Before leaving: `bash scripts/travel_prep.sh` (refresh thresholds, push).
   Confirm one watcher run fires afterward.
2. Subscribe to the ntfy topic on your phone.
3. During the trip: expect a daily heartbeat ~14:00 UTC; on a crossing, a
   high-priority ntfy bypasses DND — open the laptop within ~2h and Execute on
   the affected account. Optionally trigger the A4 rebalance manually each day to
   keep the live-tracking data flowing.
4. After returning: cron resumes as normal. No state reconciliation needed —
   `filter_state.json` stayed fresh via the manual-rebalance sync path.

## Practical overnight checklist

1. Laptop awake at some point each UTC day (the run lands at the first awake
   :10 after 00:00 UTC). Server up or down — cron doesn't care.
2. Next morning: check `data/rebalance_log.jsonl` or the Ops tab.
3. Expect small drift trades (not a full swap) on days the top 2 are unchanged.

## Install / reinstall cron

Edit the crontab:
```
crontab -e
```
and ensure these three lines are present (pointing at the **deployed** wrappers
in `~/.fire-cron/`, never at `scripts/` under `~/Desktop` — see the TCC note
above):
```
10 * * * * /Users/george/.fire-cron/cron_crypto_rebalance.sh
0 0,4,8,12,16,20 * * * /Users/george/.fire-cron/cron_filter_check.sh spy
5 1,5,9,13,17,21 * * * /Users/george/.fire-cron/cron_filter_check.sh btc
```
Deploy the wrappers (`cp scripts/cron_*.sh ~/.fire-cron/`) and keep them
executable (`chmod +x`). Verify with `crontab -l`, then confirm via the Ops
panel (entries-present + staleness) or by tailing the logs after the next fire.

To remove: `crontab -e` and delete the lines (or `crontab -r` to clear all).

## Manual invocation

```
# Daily rebalance — one fire, same code path as the cron job. A manual real
# run marks today's UTC date done, so the hourly cron won't re-run it.
uv run python3 scripts/daily_crypto_rebalance.py            # real, unconditional
uv run python3 scripts/daily_crypto_rebalance.py --if-due   # real, but skip if today already ran (cron mode)
uv run python3 scripts/daily_crypto_rebalance.py --dry-run  # dry, no orders, doesn't mark the day done

# Filter monitor — any scope
uv run python3 scripts/filter_check.py --filter all --dry-run   # check all, no trades
uv run python3 scripts/filter_check.py --filter btc             # crypto-only real run
uv run python3 scripts/filter_check.py --filter spy             # equity-only real run
```

## Related files

- [scripts/daily_crypto_rebalance.py](scripts/daily_crypto_rebalance.py) — daily
  A4 rebalance script; writes `filter_state.json` after each successful run.
- [scripts/cron_crypto_rebalance.sh](scripts/cron_crypto_rebalance.sh) — cron
  wrapper (sets `HOME`, `cd`, absolute `uv`, log redirection).
- [scripts/filter_check.py](scripts/filter_check.py) — filter monitor
  (scope-aware via `--filter`).
- [scripts/cron_filter_check.sh](scripts/cron_filter_check.sh) — cron wrapper;
  sets `FIRE_FILTER_CHECK_SOURCE=cron-<scope>`.
- [api/main.py](api/main.py) — FastAPI lifespan only; no in-process scheduler
  (APScheduler retired 2026-05-05).
- [data/filter_state.py](data/filter_state.py) — shared accessor for
  `filter_state.json` (load + atomic update with `fcntl` lock); used by all three
  rebalance entry points.
- [execution/rebalance.py](execution/rebalance.py) — shared
  `compute_rebalance` / `execute_rebalance` path used by all entry points.
- [execution/validation_gate.py](execution/validation_gate.py) — blocks
  rebalance for accounts lacking a passing validation record.
- [api/routes/ops.py](api/routes/ops.py) — Ops endpoints, incl. cron
  entries-present + staleness health checks.
- `data/risk_state/filter_state.json` — current SPY/BTC scalars + last-flip
  timestamps; written by all three rebalance entry points.
- `data/rebalance_log.jsonl` — structured audit log of every rebalance event
  (manual, scheduled, filter-monitor-triggered).
- `data/daily_rebalance.log` (+ `_stdout.log` / `_stderr.log`) — daily rebalance
  script logs; the `"starting"` line is the staleness check's source of truth.
- `data/filter_check.log` (+ `_stdout.log` / `_stderr.log`) — filter check logs
  with `source` tags.
- `DEPLOYMENT_PLAN.md` — plan to migrate the scheduler to 24/7 cloud hosting so
  the "laptop must be awake" constraint goes away.
- Travel watcher: [.github/workflows/filter_watch.yml](.github/workflows/filter_watch.yml),
  [scripts/watch_filters.py](scripts/watch_filters.py),
  [scripts/filter_watch_thresholds.json](scripts/filter_watch_thresholds.json),
  [scripts/travel_prep.sh](scripts/travel_prep.sh).
- `scripts/com.fire.*.plist` — **historical** launchd templates, no longer
  loaded (migrated to cron 2026-05-28). Kept for reference only.

## History: APScheduler → launchd → cron

- **APScheduler** (in-process `AsyncIOScheduler` in the FastAPI lifespan) —
  retired **2026-05-05** after a long-uptime drift incident: it silently missed
  a fire after ~5 days' uptime while the event loop kept serving requests
  normally. "Restart every few days" is incompatible with a multi-month uptime
  target.
- **launchd** — 2026-05-05 → 2026-05-28. Server-independent, no uptime drift.
  Killed by macOS **Background Task Management (BTM)**: after a Sequoia security
  update, all three `com.fire.*` agents were silently disabled (exit code 78,
  "service inactive") with no notification. Unload/load, a bash-wrapper, and
  `bootout`/`bootstrap` all failed — BTM blocks at the service-label level and
  `uv` is an unsigned executable. Orphaned installed plists were removed from
  `~/Library/LaunchAgents/` on 2026-05-28.
- **cron** — since **2026-05-28**. Not gated by BTM, indifferent to code
  signing, survives reboots and macOS updates. Trade-off: **no catch-up on
  missed fires** (see above).
- **cron sleep + TZ drift (failure mode #5)** — diagnosed **2026-06-09** after
  three consecutive missed daily fires. The once-daily `5 20 * * *` entry fired
  at laptop-local 20:05; a move to MDT shifted the fire to 02:05 UTC, and the
  laptop being asleep at that minute skipped the day entirely. Fixed by the
  hourly `--if-due` trigger (UTC due-check inside the script, see top of this
  doc). Cumulative laptop-scheduler failure tally: APScheduler uptime drift →
  launchd/BTM disable → cron FDA sandbox-denial → cron Desktop-provenance TCC
  denial → cron sleep+TZ. The durable end-state remains the Fly.io migration in
  `DEPLOYMENT_PLAN.md` — a 24/7 UTC host removes both the laptop-awake and the
  local-timezone dependency that every laptop-bound scheduler shares.
