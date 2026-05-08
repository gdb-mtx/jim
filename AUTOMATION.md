# FIRE Automation — A4 (Crypto) Daily Rebalance

This document describes the full picture of how Account 4's daily rebalance
is automated: what runs automatically, what requires the server to be up,
what the fallback layers are, and what manual actions (if any) you need to
take day-to-day.

## What's automated

**A launchd job fires daily at 8:05 PM laptop-local time** — Hour=20,
Minute=5 in [scripts/com.fire.daily-crypto-rebalance.plist](scripts/com.fire.daily-crypto-rebalance.plist),
which runs [scripts/daily_crypto_rebalance.py](scripts/daily_crypto_rebalance.py).
**The server does not need to be running** — the script imports the same
modules directly.

When the laptop is in EDT (UTC-4), 8:05 PM EDT = 00:05 UTC and the fire
lands at the start of a new UTC trading day. When traveling to other
timezones, the schedule drifts (e.g. UTC+1 → fires at 19:05 UTC, UTC+3
→ fires at 17:05 UTC). The strategy uses 21-day momentum on crypto so
a few-hour intraday offset is signal noise. Update Hour to match local
evening if settling in a new TZ for >1 week.

**Why not Hour=0 + TZ=UTC?** That was the original design, but two
launchd quirks defeat it:
1. `StartCalendarInterval` is interpreted in the **laptop's local TZ**,
   not the `TZ` env var set in the plist. The env var only affects the
   child script's environment (so the script's logs are in UTC, useful
   for journal correlation), not launchd's own scheduler.
2. **LaunchAgents queue `StartCalendarInterval` during darkwake** and
   only fire on next FullWake. caffeinate `-is` prevents deep sleep but
   doesn't keep the system in FullWake — observed 2026-05-06: scheduled
   00:05 EDT (= 04:05 UTC), queued through darkwake, fired at 02:05 EDT
   (= 06:05 UTC) on next FullWake transition.

Hour=20 sidesteps both issues by firing while the laptop is reliably in
FullWake (typical evening computer use). The TZ env var is kept as
`TZ=UTC` purely so the child script's logs use UTC timestamps, which
matches the rebalance journal's UTC timestamps.

Cloud target post-Fly migration is Fly Cron Machines, which honor
schedule TZ properly and don't depend on laptop power state. See
DEPLOYMENT_PLAN.md.

This replaced an in-process APScheduler job on 2026-05-05 after a
long-uptime drift incident: APScheduler's AsyncIOScheduler silently
missed a fire after 5 days of uptime, while the asyncio loop kept
serving requests normally. The wakeup chain had broken without raising.
Restart cleared it, but "restart every few days" is incompatible with a
multi-month uptime target. launchd is the same primitive the filter
monitor already uses reliably; the long-uptime failure mode is
structurally absent.

On each tick, [`scripts/daily_crypto_rebalance.py`](scripts/daily_crypto_rebalance.py)
runs the following steps:

1. `require_validated(4)` — checks `data/risk_state/validation_state.json`,
   skips if A4's record isn't passing or has expired.
2. Acquires the per-account file rebalance lock (cross-process, non-blocking
   via `fcntl` — serializes against the API and filter cron).
3. `compute_rebalance(strategy_id="crypto_momentum_filtered")` — ranks the
   9 coins in the universe by 21d momentum, picks top 2, applies the BTC
   125d SMA trend filter, applies the vol-scaling overlay.
4. Checks for price staleness (>2% drift between cached and live Alpaca
   quotes).
5. Submits orders through the same `execute_rebalance` path that the
   dashboard uses manually — including the crypto-specific notional
   sizing and `time_in_force="gtc"` plumbing.
6. Takes a daily snapshot for A4.
7. Journals everything to `data/rebalance_log.jsonl` with `source="scheduled"`
   (kept the same source tag for journal continuity).
8. Syncs `filter_state.json` with the live BTC scalar so the launchd
   filter monitor doesn't fire a no-op rebalance later from a stale value.
9. Retries up to 3× with exponential backoff on failure (60s, then 120s).

**Sleep / darkwake behavior:** if the laptop is asleep or in darkwake at
8:05 PM laptop-local (the typical case where the laptop is actively in
use), launchd queues the `StartCalendarInterval` event and fires it on
next FullWake. The 8:05 PM choice is specifically to be inside the
user's normal evening laptop use, when FullWake is reliable. If the user
is away from the laptop in the evening, expect the fire to slip to the
next FullWake. Daily-cadence + 21d momentum signal tolerates this.

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

Separate from the daily rebalance job, [scripts/filter_check.py](scripts/filter_check.py)
runs via macOS launchd. **This runs even when the server is down** —
it is a separate process launched by launchd, not a thread inside
uvicorn. Same architectural model as the daily rebalance job above
(both are server-independent launchd-fired Python scripts).

Its job is narrow: detect BTC or SPY filter *flips*. It fires on a
schedule, but the rebalance only runs when the newly computed filter
scalar differs from the last-saved scalar in
`data/risk_state/filter_state.json`. Most runs log
`"No filter changes detected"` and exit. On a flip run, it calls
`rebalance_account()` — which internally calls the *same*
`compute_rebalance()` function the daily rebalance script uses. That
means a launchd-triggered rebalance does the full pipeline: signal
ranking (top 2 by 21d momentum for crypto), filter application,
vol-scaling, and order generation. It is **not** an "exposure-only"
tweak.

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

| Layer | Trigger | Work done when triggered | Requires server? | Requires laptop on? |
|---|---|---|---|---|
| Daily rebalance (launchd) | Fires every day at 8:05 PM laptop-local (= 00:05 UTC in EDT, drifts on travel; queued and deferred-fired on next FullWake if asleep/darkwake) | Full rebalance on A4: signal + filter + vol scaling | No | Yes |
| Filter monitor — equity (launchd) | Fires at 4:30 PM laptop-local daily; rebalance only if SPY scalar differs from saved state | Full rebalance on A1/A2 (same `compute_rebalance` path) | No | Yes |
| Filter monitor — crypto (launchd) | Fires every 4 hours; rebalance only if BTC scalar differs from saved state | Full rebalance on A4 (same `compute_rebalance` path) | No | Yes |
| Travel watcher (GitHub Actions) | Fires every ~30 min at `:07/:37` UTC | **Notifies phone only** (ntfy push on crossing + daily heartbeat) — does not trade | No | No |

The crypto filter monitor is now mostly redundant with the daily
rebalance (both launchd-fired, both call `compute_rebalance` for A4) —
its remaining role is to catch a mid-day BTC flip within ~4h instead of
waiting for the next 00:05 UTC daily fire (worst-case detection lag of
24h without the monitor). The travel watcher is the safety net for a
filter flip happening while **the laptop is also off** — it turns the
failure mode from "silent miss" into "phone buzz + 2-hour human-
triggered rebalance."

### Closing the double-rebalance gap

After any successful rebalance, the writer updates
`data/risk_state/filter_state.json` with the scalar it traded against.
As of 2026-04-23 there are **three** writers, all file-locked via the
shared `data/filter_state.py` module:

- `filter_check.py` (launchd) — writes BTC + SPY scalars after its
  own flip-triggered rebalance.
- `scripts/daily_crypto_rebalance.py` (launchd) — writes `btc_scalar`
  for A4 after the daily evening fire.
- `/api/orders/rebalance/execute` in `api/routes/orders.py` — writes
  `spy_scalar` for A1/A2 manual rebalances, `btc_scalar` for A4
  manual rebalances. **This matters most during travel**: when the
  GitHub Actions watcher pings your phone and you open the laptop
  to manually execute, the state file stays fresh without launchd
  having to run.

The three writers serialize via `fcntl` so concurrent updates cannot
race. This closes the double-rebalance gap: if the daily rebalance
at 00:05 UTC already acted on a BTC flip, the next crypto filter
monitor run sees `btc_scalar` already matches live and exits as a
no-op — no duplicate trade. Symmetric across all three writers.

**Important subtlety (fixed 2026-04-23):** both the daily rebalance
script and the manual endpoint **recompute the filter live** instead
of reading `result.btc_filter_scalar`. The `crypto_momentum_filtered`
portfolio config sets `btc_filter=False` at the portfolio level (filter
is internal to CryptoMomentum to avoid double-filtering), which leaves
`result.btc_filter_scalar` at its default `1.0` even when BTC is below
the MA. A pre-2026-04-23 scheduled run during a BTC bear would have
silently written `btc_scalar=1.0` to the state file; the launchd
4-hourly corrected it, masking the bug. Both writers now mirror
`filter_check.py:compute_filters` and recompute against live prices.

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
- `data/rebalance_log.jsonl` (`source=scheduled` → daily rebalance script wrote)
- `data/daily_rebalance.log` + `data/daily_rebalance_stderr.log` (daily rebalance script + launchd stderr)

Lesson: always `git log --follow` the file whose behavior is confusing
before assuming a deep bug in the current code.

## Travel-window safety net: GitHub Actions + ntfy.sh

Added 2026-04-23. The launchd filter monitor still needs the laptop
to be awake — a digital-nomad day where the laptop spends 24h in a
bag means launchd misses the SPY/BTC check entirely, and the
APScheduler 00:05 UTC rebalance never fires either. This is the
failure mode that matters most when traveling: **an undetected BTC
filter flip during a 7-day trip could leave A4 fully exposed through
a crypto bear market start.**

To cover that gap, a GitHub Actions workflow polls BTC and SPY prices
every ~30 minutes, compares them to MA thresholds checked in to the
repo, and pushes a phone notification via [ntfy.sh](https://ntfy.sh)
on a state transition (above ↔ below MA). The runner is in GitHub's
infrastructure, so it runs regardless of laptop state.

(Note: with the daily rebalance script now launchd-fired rather than
in-process, the "server must be up overnight" failure mode is gone for
*non-travel* days where the laptop is awake but the server happens to
be down. The travel watcher is still the only safety net for the
laptop-fully-off case — that's what `DEPLOYMENT_PLAN.md` Fly migration
ultimately solves.)

### Architecture

| Component | File | Role |
|---|---|---|
| Cron runner | [.github/workflows/filter_watch.yml](.github/workflows/filter_watch.yml) | GitHub-hosted schedule, fires at `7,37 * * * *` UTC (off-peak slots — the `*/30` pattern fires at the most congested moments of every hour per GitHub's docs) |
| Checker script | [scripts/watch_filters.py](scripts/watch_filters.py) | Stdlib only (no uv install needed in the runner). Fetches BTC from CoinGecko (free, no key) and SPY from Alpaca data API, compares to thresholds, pushes ntfy on crossing |
| Thresholds | [scripts/filter_watch_thresholds.json](scripts/filter_watch_thresholds.json) | `btc_125_ma` + `spy_200_ma`, refreshed before each trip by `travel_prep.sh` |
| State cache | `scripts/filter_watch_state.json` (not committed — persisted across runs via `actions/cache@v4`) | `last_btc_above` / `last_spy_above` flags so a crossing alert fires exactly once, not every 30 min while still-below |
| Pre-travel helper | [scripts/travel_prep.sh](scripts/travel_prep.sh) | Copies today's MAs from `filter_state.json` into the watcher's threshold file, commits, pushes. Refuses to run off `main` or with unrelated uncommitted changes |

### Three kinds of notifications

| Trigger | Priority | When | Purpose |
|---|---|---|---|
| **Crossing** (above → below, below → above) | `high` (bypasses phone DND) | Immediately on the first cron tick that observes the transition | Wake the user — they need to open the laptop within ~2h and rebalance |
| **Daily heartbeat** | `low` (silent in-app) | One cron tick per UTC day in the 14:00-14:30 window | Positive "system alive" confirmation so the user knows the watcher is running when nothing has crossed |
| **Manual `workflow_dispatch` test** | `default` | Anytime the user triggers via GitHub UI with `force_test=true` | Verify end-to-end pipeline is healthy |

Heartbeat de-dup: `last_heartbeat_date` in the state cache. Second
cron tick in the same UTC-day window silently skips.

### Travel-day flow

1. **Pre-travel**: run `bash scripts/travel_prep.sh` to refresh the
   MA thresholds and push. The GitHub Actions watcher picks up the
   new thresholds on its next run (within 30 min).
2. **Laptop goes dark** (plane, hotel Wi-Fi off, etc.). No launchd,
   no APScheduler. The GitHub runner keeps polling every ~30 min.
3. **Daily 14:00 UTC**: phone gets a quiet heartbeat ping ("all
   green, BTC $X above MA, SPY $Y above MA"). Reassurance.
4. **Crossing happens** (e.g. BTC drops below 125d MA during NY
   evening): phone buzzes with a high-priority ntfy within 0-30
   minutes. Bypasses DND.
5. **User opens laptop within ~2h**, opens the dashboard, clicks
   Preview → Execute on the affected account. The new filter_state
   sync (see previous section) keeps everything consistent so
   post-travel launchd runs don't misdetect.
6. **Daily A4 rotation that the user wants to keep collecting data
   on**: user opens laptop whenever convenient each travel day and
   manually triggers the A4 rebalance. The signal is 21d momentum
   and barely shifts intraday — a ~20h offset vs. the 00:05 UTC
   scheduled fire is well inside the noise (~0.1-0.3% cumulative
   timing drift over a week).

### What it doesn't cover

- **It does not trade.** It only notifies. You still have to open
  the laptop and press Execute. If you can't open the laptop within
  ~24h of a crossing, A4 sits in its old positions through a bear
  start. Bounded risk by design — the real fix for 24/7 unattended
  trading is the Fly.io deployment in `DEPLOYMENT_PLAN.md`.
- **GitHub Actions scheduled triggers have a documented warm-up
  delay.** When the workflow was first added on 2026-04-23 at 16:09
  UTC, the first scheduled run didn't fire until 18:44 UTC — ~2.5
  hours after creation. This appears to be GitHub's scheduler being
  lazy about new workflows on private free-tier repos; unrelated to
  our YAML. Once activated, subsequent runs fire near-schedule (~7
  min delay typical).
- **Minute-precision is not guaranteed.** GitHub's own docs note
  that scheduled workflows may be delayed during periods of high
  load, especially at :00 and :30 of each hour. We use `:07` and
  `:37` specifically to dodge those slots.

### Pre-travel one-command

```
bash scripts/travel_prep.sh
```

Or alias it: `alias fire-travel-prep='/Users/george/Desktop/Projects/FIRE/scripts/travel_prep.sh'`
in `~/.zshrc`. The script is a no-op when thresholds haven't drifted,
so running it repeatedly is safe.

### GitHub secrets required (one-time setup)

In repo Settings → Secrets:
- `NTFY_TOPIC` — the unguessable topic string you subscribed to in
  the ntfy phone app.
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — any account's data-API
  credentials; needed to fetch the SPY trade. A1's keys are fine.

### Verifying the watcher is healthy

From the laptop:
```
gh run list --workflow filter_watch.yml --limit 10
gh run view <run-id> --log | grep "crossings\|Sent"
```

Or in the GitHub Actions tab in VS Code (with the GitHub Actions
extension) → `filter_watch` workflow → most recent runs.

### Post-travel checklist: clear the launchd TZ cache

When you cross timezones, macOS updates the system clock and `date`
output immediately, but **launchd itself caches the system timezone at
boot and does not refresh it on TZ changes**. launchd is PID 1 — the
macOS init process — and only restarts on a full system reboot.
Logout/login restarts user-domain LaunchAgents and UserEventAgent, but
NOT PID 1, so it does not clear this cache. Reboot is the only fix.

Documented in community threads since at least 2013 (see
[Apple Discussions thread/5137946](https://discussions.apple.com/thread/5137946),
[thread/6389388](https://discussions.apple.com/thread/6389388),
[launchd.info](https://www.launchd.info/), and
[alvinalexander.com](https://alvinalexander.com/mac-os-x/launchd-plist-examples-startinterval-startcalendarinterval/)).
Apple has not addressed it.

The job still fires while the cache is stale — just at the wrong
wall-clock time. With Hour=20 in the plist and a MDT-cached launchd
on an EDT-current laptop, the fire lands at 22:05 EDT (= 20:05 MDT),
not 20:05 EDT.

How to detect:
```
date && launchctl print gui/$(id -u)/com.fire.daily-crypto-rebalance | grep -A1 calendarinterval
# Then verify by reading data/rebalance_log.jsonl after the next fire —
# the timestamp should be within a few minutes of the intended slot
# (8:05 PM laptop-local for daily, equivalent to 00:05 UTC in EDT).
# If it's off by a multiple of an hour matching your old TZ, the cache
# is stale.
```

The fix is **Apple menu → Restart** (full reboot). Confirmed working
2026-05-06: a test plist scheduled 2 minutes out fired within 5 seconds
of its slot post-reboot.

Lighter-touch approaches we tried, all ineffective:
- `launchctl kickstart -k gui/$(id -u)/com.apple.UserEventAgent-Aqua`
  fails with "Operation not permitted while System Integrity Protection
  is engaged" — SIP protects Apple's user-domain agents from user-level
  kicks. Disabling SIP is not worth it.
- `notifyutil -p com.apple.system.timezone` posts the same notification
  the OS would fire on a real TZ change — ignored by launchd PID 1.
- `launchctl bootout` + `launchctl bootstrap` of the affected plist
  re-registers the job but inherits the same cached TZ from PID-1
  launchd.

Untested, likely not worth trying:
- **Apple menu → Log Out** (different from Restart) might cycle the
  user-session launchd that manages user-domain LaunchAgents — but the
  community sources we found are ambiguous about whether the relevant
  TZ cache lives in the user-session launchd or PID 1. We didn't test
  it; reboot is faster than logging out, restarting all your apps,
  testing, and rebooting anyway if logout didn't work. Default to
  reboot.

Diagnosed and confirmed 2026-05-06 after a MDT → EDT trip — three daily
A4 fires landed at 22:05 EDT instead of 20:05 EDT (= MDT-cached
interpretation of Hour=20). Reboot cleared it; a follow-up test plist
fired on time within 5 seconds of its scheduled slot.

The structural fix is the cloud migration — Fly Cron Machines accept an
explicit `CRON_TZ` parameter and don't share macOS's `UserEventAgent`
caching. Until then this is a known operational gotcha; bake the reboot
into your post-travel arrival routine.

## What you have to do

**Nothing, as long as the laptop is in FullWake at 8:05 PM laptop-local.**
launchd fires the script independently of the server, so even a fully-down
uvicorn doesn't break the job. The 8:05 PM choice lands inside typical
evening computer use, which is when FullWake is reliable. If you've
stepped away from the laptop in the evening, expect the fire to slip
to next FullWake.

### To verify the job fired (the next morning)

1. Open the **Ops** dashboard tab — the Scheduler Panel shows the
   `daily_crypto_rebalance` job under "Scheduled rebalance (launchd)"
   with its last-run / next-run and status (success / partial / failed
   / skipped). The Event Timeline below lists the scheduled rebalance
   alongside any filter flips.
2. Or, from the CLI: grep `data/rebalance_log.jsonl` for a fresh entry
   with `"source": "scheduled"` and `"account": 4`.
3. Tail `data/daily_rebalance.log` for `"Daily crypto rebalance starting"`
   + `"Final outcome: ..."` lines from the most recent fire.

### If the laptop was asleep at 00:05 UTC

launchd's `StartCalendarInterval` deferred-fire semantics handle this:
the job fires once on next wake. If you want to confirm, check
`data/daily_rebalance.log` for a "starting" timestamp shortly after wake.
If for any reason it didn't catch up, manually hit Execute on the A4
rebalance panel — same path as a manual first-time entry.

### During travel (laptop off for days)

1. Before leaving: `bash scripts/travel_prep.sh` — refreshes thresholds,
   commits, pushes. Confirm one scheduled GitHub Actions run fires
   afterwards (VS Code Actions panel or `gh run list ...`).
2. Subscribe to the ntfy topic on your phone if you haven't already.
3. During the trip:
   - Expect one daily heartbeat ntfy around 14:00 UTC (low priority,
     silent in-app).
   - On a crossing, high-priority ntfy bypasses DND — open the laptop
     within ~2h and click Execute on the affected account.
   - Each day, open the laptop once to manually trigger the A4
     rebalance (Preview → Execute). Takes 30 seconds and keeps the
     live-tracking data flowing.
4. After returning: launchd + APScheduler resume as normal. No state
   reconciliation needed — `filter_state.json` stayed fresh via the
   manual-rebalance sync path.

## Practical overnight checklist

1. Laptop plugged in and stays awake past 8:05 PM ET (= 00:05 UTC during
   EDT). The server can be up or down — launchd doesn't care.
2. The next morning: check `data/rebalance_log.jsonl` for the scheduled
   entry, or open the Ops dashboard tab.
3. Expect small drift trades (not a full swap) on any given day where
   the top 2 coins remain the same.

## Installing / reinstalling launchd

First-time install, or after pulling new plist changes:

```
# Remove the old single plist, if present
launchctl unload ~/Library/LaunchAgents/com.fire.filter-check.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.fire.filter-check.plist

# Copy the three plists in and load them
cp scripts/com.fire.filter-check-equity.plist \
   scripts/com.fire.filter-check-crypto.plist \
   scripts/com.fire.daily-crypto-rebalance.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fire.filter-check-equity.plist
launchctl load ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist
launchctl load ~/Library/LaunchAgents/com.fire.daily-crypto-rebalance.plist

# Verify (expect 3 entries)
launchctl list | grep fire
```

To uninstall all three:
```
launchctl unload ~/Library/LaunchAgents/com.fire.filter-check-equity.plist \
                 ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist \
                 ~/Library/LaunchAgents/com.fire.daily-crypto-rebalance.plist
```

Manual invocation:
```
# Daily rebalance — one fire, same code path as the launchd job
uv run python3 scripts/daily_crypto_rebalance.py            # real
uv run python3 scripts/daily_crypto_rebalance.py --dry-run  # dry, no orders

# Filter monitor — any scope
uv run python3 scripts/filter_check.py --filter all --dry-run   # check everything, no trades
uv run python3 scripts/filter_check.py --filter btc             # crypto-only real run
uv run python3 scripts/filter_check.py --filter spy             # equity-only real run
```

## Related files

- [scripts/daily_crypto_rebalance.py](scripts/daily_crypto_rebalance.py)
  — daily A4 rebalance script (launchd-fired, replaces the in-process
  APScheduler job retired 2026-05-05); writes `filter_state.json`
  after each successful run.
- [scripts/com.fire.daily-crypto-rebalance.plist](scripts/com.fire.daily-crypto-rebalance.plist)
  — launchd plist, `StartCalendarInterval` hour=20 minute=5 laptop-local
  (= 00:05 UTC in EDT). `TZ=UTC` env var affects child script timestamps
  only, not the schedule.
- [scripts/filter_check.py](scripts/filter_check.py) — launchd filter
  monitor (scope-aware via `--filter`)
- [scripts/com.fire.filter-check-equity.plist](scripts/com.fire.filter-check-equity.plist)
  — SPY filter, every 4 hours
- [scripts/com.fire.filter-check-crypto.plist](scripts/com.fire.filter-check-crypto.plist)
  — BTC filter, every 4 hours
- [api/main.py](api/main.py) — FastAPI lifespan only; no in-process
  scheduler (retired 2026-05-05).
- [data/filter_state.py](data/filter_state.py) — shared accessor for
  `filter_state.json` (load + atomic update with `fcntl` file lock);
  used by `filter_check.py`, `daily_crypto_rebalance.py`, and the API.
- [execution/rebalance.py](execution/rebalance.py) — shared
  `compute_rebalance` / `execute_rebalance` path used by all entry
  points
- [execution/validation_gate.py](execution/validation_gate.py) — gate
  that blocks rebalance for accounts lacking a passing validation
  record
- [api/locks.py](api/locks.py) — per-account locks that serialize the
  three entry points (API, daily rebalance script, filter cron)
- `data/risk_state/validation_state.json` — per-account validation
  status; the daily rebalance script skips if A4 is not passing
- `data/risk_state/filter_state.json` — current SPY/BTC scalars +
  last-flip timestamps; written by all three rebalance entry points
- `data/rebalance_log.jsonl` — structured audit log of every rebalance
  event (manual, scheduled, and filter-monitor-triggered)
- `data/daily_rebalance.log` / `data/daily_rebalance_stderr.log` —
  daily rebalance script logs (the script's own log + launchd stderr)
- `DEPLOYMENT_PLAN.md` — plan to migrate the scheduler to 24/7 cloud
  hosting so the "laptop must be awake" constraint goes away
- [.github/workflows/filter_watch.yml](.github/workflows/filter_watch.yml)
  — GitHub Actions cron (added 2026-04-23) that runs the
  travel-window watcher regardless of laptop state
- [scripts/watch_filters.py](scripts/watch_filters.py) — stdlib-only
  BTC/SPY threshold checker that pushes ntfy on crossings + daily
  heartbeat; invoked by the workflow
- [scripts/filter_watch_thresholds.json](scripts/filter_watch_thresholds.json)
  — committed MA thresholds, refreshed per trip
- [scripts/travel_prep.sh](scripts/travel_prep.sh) — one-command
  pre-travel refresh helper (copies thresholds from filter_state.json,
  commits, pushes)
- [api/routes/orders.py](api/routes/orders.py) — manual
  `/rebalance/execute` endpoint; added filter_state.json sync
  (2026-04-23) so travel-window manual trades keep state consistent
- `docs/archive/OPS_DASHBOARD_PLAN.md` + Ops dashboard tab — built 2026-04-22
  (commits `79b957e` backend, `8f23750` frontend, `6b0d78b` cleanup).
  Single pane covering scheduled rebalance (launchd) + filter monitors
  (launchd) + validation status + a merged rebalance / filter-flip
  event timeline. Endpoints at `/api/ops/*`; panels under
  [dashboard/src/components/ops/](dashboard/src/components/ops/).
  Will absorb cloud-scheduler status post-Fly migration.
