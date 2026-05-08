# Ops Dashboard — Design & Implementation Plan

**Status:** ✅ **Built 2026-04-22.** Commits:
- `79b957e` — backend (`api/routes/ops.py`, APScheduler refactor, log parser + tests)
- `8f23750` — frontend (Ops tab + 4 panels)
- `6b0d78b` — Live Portfolio cleanup (remove `RebalanceHistory`)

Day-to-day runbook info lives in [AUTOMATION.md](AUTOMATION.md). This
document is preserved as the design record — §1–§9 below are the
as-planned spec. **The section immediately below** captures what
actually shipped vs. what was planned.

## 0. As-built — deltas vs. this plan

### Shipped as designed
- Ops tab alongside Live Portfolio + Backtests
- SchedulerPanel (APScheduler jobs + 2 launchd rows with last-run
  relative times, flip badges, account-result summaries)
- FilterStatePanel (SPY 200d + BTC 125d cards, plausibility banner
  when active, `last_checked_relative` server-side)
- ValidationPanel (4 accounts, status dots, days-remaining with
  amber <30d / red if expired, expandable row showing OOS metrics +
  reason + report path resolved via `account_N_YYYYMMDD_*.md` glob)
- EventTimeline (rebalance + filter_flip merge, Type + Account
  dropdowns, expandable JSON per row, tie-breaker puts `filter_flip`
  above the rebalance it triggered on shared timestamps)
- Four endpoints at `/api/ops/{scheduler,filters,validation,events}`
- APScheduler scheduler + `_last_run_info` promoted to module scope
  in `api/main.py` (visible at [L28-L32](api/main.py#L28-L32) and
  [L54-L144](api/main.py#L54-L144))
- `data/filter_check_log.py` parser with 10 fixture tests (all green)
- `data/filter_state.py::load_with_plausibility()` shared helper

### Deferred (present in plan, not shipped)
- **Server health indicator** (amber-if-slow, red-if-unreachable) —
  current state is binary running/not-running from
  `scheduler.running`. Good enough for MVP.
- **"Validation refreshes" as an event type** — would need a
  `validation_state.json` mtime watcher. Not wired.
- **APScheduler fire events as a third timeline source** —
  `rebalance_log.jsonl` with `source=scheduled` already covers this
  for A4 daily. Per plan §6, deferred.
- **`next_cursor` pagination on /events** — endpoint returns
  `{events, total}` with a `limit` cap. Good for now; revisit if
  event history grows.

### Shipped differently
- **`/api/ops/filters` response shape** — flat JSON mirroring raw
  `filter_state.json` fields (`spy_scalar`, `spy_price`, `spy_ma200`,
  `last_spy_flip`, etc.), *not* nested under `spy`/`btc` keys as
  sketched in §3. Simpler, no type wrangling on the frontend.
  Note: `last_btc_change` / `last_spy_change` were renamed to
  `last_btc_flip` / `last_spy_flip` 2026-04-22 for clarity.
- **FilterStatusBanner NOT migrated** — per user preference, the
  banner stays on Live Portfolio as-is. The compact one-liner
  described in §2.2 / §5 was not built; instead the Ops tab
  duplicates the filter info in richer form.
- **RebalanceHistory removed, not replaced with a compact view** —
  no "last 3 rebalances" preview on Live Portfolio. Full history
  lives in Ops EventTimeline. The `fetchRebalanceHistory` helper
  and `RebalanceHistoryEntry` type are retained because
  `EquityHistoryChart` marks rebalance events on the equity curve.

### Open questions — resolved
1. **Auth gate on Ops tab** — unchanged. Dashboard stays
   localhost-only, no auth. Manual-trigger buttons remain deferred
   per §6.
2. **Settings area for env vars** — not built.
3. **Compact "recent events" on Live Portfolio** — no (per user).
4. **"Run re-validation" button** — not built. Defer to CLI.

### Known oddity flagged during build
The 2026-04-22 12:27:49 MDT unexplained `filter_state.json` write —
ruled out every automated path via sandbox harness + mtime checks.
Documented in [AUTOMATION.md → Known oddity](AUTOMATION.md#known-oddity-2026-04-22--one-unexplained-filter_statejson-write)
with a diagnosis recipe for next time.

---

## 1. Motivation

Today the system's automation and monitoring surface is spread across:
- macOS notifications (useless, going away — Script Editor pops up on click,
  and they don't migrate to cloud anyway)
- The server console log (invisible unless you're tailing it)
- `data/filter_check.log` (requires `tail` from the terminal)
- Assorted banners and panels scattered across the Live Portfolio view
  (`FilterStatusBanner`, `RiskStatusPanel`, `DataFreshnessPill`,
  `RebalanceHistory`)

When A4 went live on 2026-04-22 and we hit five cascading bugs before the
first fill cleared, almost all of the debugging happened via
`curl`/`cat`/`tail` in a terminal. The dashboard had status info but it
was siloed per-concern and not sufficient by itself to answer
"is everything running, and when did it last run?" — the single most
important operational question.

Two incoming changes make now the right time to consolidate:
1. We're killing macOS notifications (they were the stopgap).
2. We're migrating live ops to Fly.io cloud hosting soon (per
   `DEPLOYMENT_PLAN.md`). Cloud automation won't push macOS
   notifications, so the dashboard *must* become the single pane of
   glass before that migration.

The goal of this build: after it ships, you should be able to answer
"is the system healthy and when did it last do anything?" from a single
dashboard tab, without opening a terminal.

## 2. Scope — four panels in one new "Ops" tab

Add a top-level tab "Ops" (or "Automation") alongside Live Portfolio and
Backtests. Four modules inside:

### 2.1 Scheduler Panel

Shows the state of every automation trigger:

- **APScheduler (in uvicorn)**: job name, cron schedule, next fire time,
  last fire time, last status (success / failed / skipped). Introspected
  from the `AsyncIOScheduler` instance in `api/main.py`.
- **Launchd monitors** (per plist): for each of
  `com.fire.filter-check-equity` and `com.fire.filter-check-crypto`,
  show last run time (from `filter_check.log`), the `source` tag,
  the `scope`, last outcome (flip / no change / error), and
  time-since-last-run. Parse the log file — don't shell out to
  `launchctl`, so this code works unchanged post-cloud migration (where
  Fly cron replaces launchd).
- **Server health indicator**: green if APScheduler is reachable and
  alive, amber if responding slowly, red if the server can't be reached
  (dashboard falls back to polling state).

Layout suggestion: one row per trigger, with columns for "trigger",
"last run", "next run", "status". Color-code status (green/amber/red).

### 2.2 Filter State Panel

Current state of SPY and BTC filters, plus flip history:

- SPY: current price vs 200d MA, current scalar (1.0 / 0.5), last flip
  timestamp.
- BTC: current price vs 125d MA, current scalar (1.0 / 0.0), last flip
  timestamp.
- Reads `data/risk_state/filter_state.json` via a new
  `GET /api/ops/filters` endpoint (or reuse `GET /api/portfolio/filters`
  with extended fields).

Migration: this replaces [dashboard/src/components/FilterStatusBanner.tsx](dashboard/src/components/FilterStatusBanner.tsx)
entirely. That component has grown to cover plausibility warnings,
filter monitor last-check time, and the SPY/BTC banners; all of that
moves here. On the Live Portfolio page, keep a compact one-line
filter-status indicator (current scalars only) — details live in Ops.

### 2.3 Validation Panel

Per-account validation status:

- Table: Account | Strategy | Status (PASS / MARGINAL / FAIL / RETIRED /
  unvalidated) | Valid until | Days remaining | Link to report.
- Amber highlight when days remaining < 30.
- Red highlight when expired or FAIL.
- Reads `data/risk_state/validation_state.json` via a new
  `GET /api/ops/validation` endpoint.

This surfaces a concern that's currently invisible to the dashboard: the
quarterly re-validation gate. A4 is currently PASS, but if we forget to
re-run `scripts/run_validation.py --account 4` before the 90-day expiry,
every rebalance will 403 silently. The panel makes this a visible,
countdown-able item.

### 2.4 Event Timeline

Unified stream of automation events:

- **Rebalance events** — from `data/rebalance_log.jsonl` (manual,
  scheduled, and filter-monitor-triggered, distinguished by the
  `source` field).
- **Filter flips** — parsed from `data/filter_check.log` lines
  containing "filter changed".
- **APScheduler fire events** — parsed from the uvicorn log (either
  `data/api.log` if we start writing one, or a new in-memory ring
  buffer exposed via API).
- **Validation refreshes** — from `validation_state.json` mtime + content
  diff over time (or by watching the file via a simple in-process
  watcher).

UI: reverse-chronological list with timestamp, source badge, event type,
account, summary. Filterable by account, source, and event type.
Expandable per row to show the full JSON payload.

Migration: this replaces [dashboard/src/components/RebalanceHistory.tsx](dashboard/src/components/RebalanceHistory.tsx)
with a broader scope. The existing component is rebalance-only; the
new one is automation-event-wide.

## 3. Backend endpoints

All under `/api/ops/` (new prefix). New file: `api/routes/ops.py`.

### `GET /api/ops/scheduler`

```json
{
  "apscheduler": {
    "running": true,
    "jobs": [
      {
        "id": "daily_crypto_rebalance",
        "name": "Daily crypto momentum rebalance (00:05 UTC)",
        "next_run_time": "2026-04-23T00:05:00+00:00",
        "last_run_time": "2026-04-22T00:05:00+00:00",
        "last_status": "success"
      }
    ]
  },
  "launchd": [
    {
      "label": "com.fire.filter-check-equity",
      "scope": "spy",
      "last_run": "2026-04-22T20:30:05+00:00",
      "last_source": "launchd-equity",
      "last_outcome": "no_change",
      "last_scalar_observed": {"spy": 1.0}
    },
    {
      "label": "com.fire.filter-check-crypto",
      "scope": "btc",
      "last_run": "2026-04-22T16:25:00+00:00",
      "last_source": "launchd-crypto",
      "last_outcome": "no_change",
      "last_scalar_observed": {"btc": 1.0}
    }
  ]
}
```

Implementation notes:
- APScheduler introspection: hold a module-level reference to the
  scheduler in `api/main.py`, expose `scheduler.get_jobs()`.
- Last-run/last-status for APScheduler: we don't currently track this.
  Add a simple in-process dict `_last_run_info[job_id] = {time, status}`
  updated inside `_daily_crypto_rebalance` at entry + exit, and expose
  via the endpoint.
- Launchd state: parse `data/filter_check.log`, group by `source=` tag
  found in the `FIRE Filter Check starting` lines, take the last entry
  per source, extract outcome from subsequent log lines of the same run.
  Wrap in a helper `parse_filter_check_log() -> list[dict]`.

### `GET /api/ops/filters`

Passthrough of `filter_state.json` plus plausibility state:

```json
{
  "spy": {"scalar": 1.0, "price": 709.66, "ma_200": 664.57, "last_change": "2026-04-14T03:37:22+00:00"},
  "btc": {"scalar": 1.0, "price": 78945.96, "ma_125": 76977.92, "last_change": "2026-04-22T18:27:49+00:00"},
  "last_checked": "2026-04-22T18:27:49+00:00",
  "plausibility": { /* from data/plausibility.py */ }
}
```

### `GET /api/ops/validation`

```json
{
  "accounts": [
    {
      "account": 1,
      "strategy": "sm_filtered",
      "status": "pass",
      "valid_until": "2026-07-20",
      "days_remaining": 89,
      "report_path": "data/validation_reports/2026-04-21_acct1.md",
      "last_run": "2026-04-21T15:30:00+00:00"
    },
    ...
  ]
}
```

Reads `data/risk_state/validation_state.json`, enriches with
`days_remaining` computed from today, and exposes the markdown report
path for the frontend to link (dashboard serves it as static asset if we
add a static-file route, or provides a `GET /api/ops/validation/report?account=N`
endpoint that returns the markdown content).

### `GET /api/ops/events?limit=50&since=<iso>&source=<filter>&type=<filter>`

Unified event stream:

```json
{
  "events": [
    {
      "timestamp": "2026-04-22T15:30:29+00:00",
      "type": "rebalance",
      "source": "manual",
      "account": 4,
      "summary": "2 orders submitted, 0 failed",
      "details": { /* full rebalance_log.jsonl entry */ }
    },
    {
      "timestamp": "2026-04-22T18:27:49+00:00",
      "type": "filter_flip",
      "source": "launchd-crypto",
      "summary": "BTC filter 0.0 → 1.0 (BULLISH)",
      "details": { "from": 0.0, "to": 1.0, "price": 78967.74, "ma": 76977.92 }
    }
  ],
  "next_cursor": "..."
}
```

Implementation:
- Read `rebalance_log.jsonl` line-by-line, reverse order, filter by
  timestamp/account/source, map each line to the event shape.
- Parse `filter_check.log` for flip events (lines containing
  `"filter changed"`) similarly.
- Merge both streams by timestamp, apply `limit` + filters.
- Later: add APScheduler fire events from a new in-memory ring buffer
  or a dedicated JSONL log file.

## 4. Frontend component sketch

New directory/files under `dashboard/src/`:

```
dashboard/src/
  pages/
    OpsPage.tsx                          # the new top-level tab
  components/ops/
    SchedulerPanel.tsx                    # 2.1
    FilterStatePanel.tsx                  # 2.2 (replaces FilterStatusBanner)
    ValidationPanel.tsx                   # 2.3
    EventTimeline.tsx                     # 2.4 (replaces RebalanceHistory)
    StatusDot.tsx                         # small shared status pill
  api.ts                                  # add fetchOpsScheduler, fetchOpsFilters, etc.
  types.ts                                # add OpsSchedulerResponse, OpsEvent, etc.
```

State flow:
- Each panel polls its own endpoint on mount + every 30s (same cadence
  as the existing dashboard).
- No cross-panel state — each is independent for testability.
- Use `React.memo` per panel as we do elsewhere to avoid re-renders from
  sibling polls.

Routing / tab integration:
- The app currently uses a simple tab-state in `App.tsx` (or similar).
  Add `"ops"` as a new tab value. Render `<OpsPage />` when active.

## 5. Migration plan

### Components that move to Ops

- `FilterStatusBanner.tsx` → `components/ops/FilterStatePanel.tsx`
  (rewrite with extended info). Replace the Live Portfolio usage with
  a compact one-line indicator that shows only current SPY/BTC scalars,
  and links to the Ops tab for details.
- `RebalanceHistory.tsx` → `components/ops/EventTimeline.tsx`
  (broader scope). Keep a compact "recent rebalances" list on Live
  Portfolio if desired (last 3 entries with a "see all in Ops" link).

### Components that stay

- `RiskStatusPanel.tsx` — stays on Live Portfolio. Drawdown state is
  about current money, not automation. Optionally mirror a read-only
  snapshot in Ops under a "Risk" sub-section.
- `DataFreshnessPill.tsx` — stays on Live Portfolio.
  Same reasoning.

### Backend

- New file `api/routes/ops.py` with the four endpoints above.
- Register in `api/main.py`: `app.include_router(ops.router, prefix="/api/ops", tags=["ops"])`.
- APScheduler introspection: expose the scheduler instance as a
  module-level global in `api/main.py` so `ops.router` can import it.
- Add `_last_run_info` dict + updates in `_daily_crypto_rebalance`.

## 6. Out of scope (deferred)

These could be added in a later pass; not blocking the MVP:

- Log tail streaming (SSE/websocket of live `filter_check.log` tail).
- Manual-trigger buttons in the Ops UI to fire APScheduler /
  filter_check jobs on demand (security consideration — could be
  nice, but needs auth story first).
- Performance graphs (how long each rebalance takes, queue depth,
  etc.). Nice-to-have, not MVP.
- Cross-account correlation monitor stays where it is; not
  automation-scoped.

## 7. Sizing

Rough estimates, can be more precise once started:

| Item | Effort |
|---|---|
| `api/routes/ops.py` with 4 endpoints + helpers | 1.5–2h |
| `filter_check.log` parser + test coverage | 0.5h |
| APScheduler introspection hook in `api/main.py` | 0.5h |
| `OpsPage.tsx` + 4 component files + API client additions | 3h |
| Migration of existing `FilterStatusBanner` + `RebalanceHistory` | 1h |
| Polish, integration testing, dashboard routing wiring | 0.5–1h |
| **Total** | **6–8h** (one focused day) |

## 8. Open questions for next session

1. Should the Ops tab require any kind of read-only gate, or is the
   whole dashboard still localhost-only / no-auth? Answer shapes
   whether manual-trigger buttons are in MVP scope.
2. Do we want a settings area in Ops for toggling things like
   `FIRE_DISABLE_NOTIFICATIONS` at runtime, or does that stay env-var-only?
3. Is a "recent events" compact view on the Live Portfolio still
   valuable after Ops exists? Probably yes — users will live there
   most of the time.
4. Should the Validation Panel include a "run re-validation" button
   (long-running task, needs backgrounding)? Or defer to CLI?

## 9. Post-cloud-migration notes

After the Fly.io migration per `DEPLOYMENT_PLAN.md`:

- The `launchd` block of the Scheduler Panel becomes a "Fly cron" block.
  Data source changes (Fly's REST API or a cron-status endpoint we'd
  add), but the panel structure stays the same.
- The Event Timeline keeps working as-is — log files become
  Fly-persisted logs, `rebalance_log.jsonl` lives on the Fly volume.
- APScheduler section unchanged — same code runs on Fly.

So the Ops tab design is cloud-portable by construction. Only the
launchd-specific data plumbing gets swapped out.
