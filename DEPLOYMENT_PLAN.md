# DEPLOYMENT_PLAN.md — Live Module Cloud Deployment

**Opened:** 2026-04-20
**Status:** Working document. Actual Fly deployment is 3-4 weeks out, possibly months. Near-term work is the **Phase 0 refactor** (decouple live from backtest) done locally. But the overall schedule is tighter than it looks: the 3-month paper-trading clock was reset on 2026-04-20, and real money requires meaningful deployed-paper time (not just local-paper time) before the June/July real-money window. Planning deployment sooner — not because we need to ship fast, but because running paper on Fly is the only way to surface infrastructure bugs before they have real blast radius. See "Timeline — the 3-month paper clock" below.
**Context:** FIRE currently runs on George's MacBook. launchd fires the filter monitor at 4:30 PM ET; FastAPI + APScheduler runs when George is working. For paper it's fine; for real money it's not. Also: George is a digital nomad and his laptop is not always on/connected, so the live trading path shouldn't depend on it.

---

## Guiding principles

1. **ET is the system reference timezone.** Codified in CLAUDE.md. All scheduled times use `TZ=America/New_York` or `CRON_TZ=America/New_York`. Only A4's crypto APScheduler stays on UTC (crypto is 24/7 — UTC is the honest anchor there).
2. **Local dev keeps working unchanged.** Cloud deployment is additive, not a replacement. `VITE_API_BASE_URL` + `FIRE_SCHEDULER_ENABLED` flags toggle between local-only and cloud-backed.
3. **Boring tech.** Prefer documented, well-trodden tools over shiny. One CLI, one Dockerfile, one config file.
4. **Every phase is reversible.** No one-way doors until Phase 5 pre-real-money split.
5. **Paper-first — and paper *on the deployed infra* is itself a validation phase, not just a rehearsal.** The whole point of running paper on Fly before real money is that infrastructure bugs (cron fires at wrong time, volume unmounts, log drain silently breaks, auth middleware has a bypass, `fly scale count 2` slips through) only surface on production infra. We already found that our local backtest and local live didn't agree (AUDIT_MONTH2 C4). The equivalent for deployment is: laptop-paper and Fly-paper won't agree in ways we can't predict until Fly-paper has been running for weeks. **Real money requires deployed-paper time, not just laptop-paper time.**
6. **Timeline alignment.** Paper-trading clock was reset 2026-04-20 after the stale-data bug invalidated the Mar 10 → Apr 17 window (see CLAUDE.md). Minimum 3 months of clean paper before real money is considered → **earliest real-money date: ~2026-07-20.** That's the backstop; the actual trigger is the deployed-paper validation gate in Phase 5, whichever is later.

---

## Timeline — the 3-month paper clock

Dates are approximate. The goal is not to be fast; it's to be honest about the schedule so we don't accidentally short-change the deployed-paper phase.

| Anchor | Date | Meaning |
|---|---|---|
| Paper clock reset | **2026-04-20** | Post-audit, stale-data window invalidated. Fresh paper trading starts here. |
| 3-month minimum paper window | **2026-07-20** | Earliest calendar date real money can be considered per CLAUDE.md policy. |
| Phase 0 refactor complete | ~2026-04-27 | Split `strategies/portfolio.py`, audit imports, 1 week of laptop validation. |
| Phase 1 target (deploy API to Fly) | ~2026-05-04 | 2 weeks from today. Aggressive but doable. |
| Phase 2 target (APScheduler on Fly) | ~2026-05-11 | |
| Phase 3 target (filter cron on Fly) | ~2026-05-18 | Laptop launchd unloaded same day. |
| Phase 4 target (observability wired) | ~2026-05-25 | |
| **Deployed-paper window begins** | ~2026-05-25 | Fly runs paper with full observability. This is when infra bugs have a chance to surface. |
| Minimum deployed-paper duration | **≥8 weeks** | Calibrated against 3-month total paper clock and the fact that monthly rebalance (A1/A2) gives only ~2 monthly cycles inside 8 weeks. Want at least 2 full rebalance months, 2 filter flips if possible, one Alpaca weekend gap, one Fly deploy during live hours that we then test rollback on. |
| Phase 5 pre-real-money hardening | ~2026-07-20+ | Earliest start. Paper/live app split, runbook drilled, volume restore drilled. |
| Real money | **2026-08-01+** | Not before. Gated on C4/C5/C6 fixed AND ≥8 weeks clean deployed-paper AND runbook drilled. |

**What this math means:** if Phase 1 slips past mid-May, deployed-paper time compresses and real money slips to September. That's fine — the timeline should bend to the evidence, not the other way. But it also means the current "3-4 weeks" estimate for *starting* deployment is load-bearing. The Phase 0 refactor should not balloon.

---

## Vercel evaluation (the "why not" section)

George's initial ask was "deploy to Vercel." Vercel is serverless functions + edge static hosting. It **cannot** host the live service. Specifics:

- **No long-running daemon.** `api/main.py` uses `AsyncIOScheduler` in the FastAPI lifespan — it must stay resident. Vercel functions terminate after each request. Vercel Cron exists but only triggers an HTTP function invocation; the scheduler itself can't live there.
- **Execution-time caps.** Hobby 10s, Pro 60s default / 300s fluid / 900s background. Crypto rebalance (yfinance pull → vol calc → Alpaca order submission → snapshot) routinely pushes past 60s, especially with retries. `/api/backtests` endpoints are much worse.
- **Ephemeral filesystem.** Everything in `data/risk_state/` and `data/raw/` vanishes between invocations. **Circuit-breaker state silently resetting is a real-money-graduation disqualifier** — we explicitly chose file-persistence for this in S3.
- **`fcntl.flock` is meaningless in serverless.** `api/locks.py` relies on flock to serialize FastAPI + APScheduler + filter_check across processes. Serverless spawns parallel isolated instances with independent tmpfs — the lock protects nothing.

**Verdict:** Vercel is good for the **dashboard static bundle only**. Wrong for API + scheduler + cron.

---

## Platform choice — Fly.io (primary)

**Recommendation:** Fly.io, single app, single machine, 1GB persistent volume mounted at `/data`.

Why:
- Linux container → `fcntl.flock` works as-is on ext4 volume; APScheduler runs 24/7; Python 3.12 via standard Dockerfile or uv-friendly buildpack.
- First-class persistent volumes (`fly volumes create`). Survives deploys.
- Native secrets (`fly secrets set ALPACA_API_KEY=...`), native scheduled machines, native log drains.
- Cost: `shared-cpu-1x` + 512MB RAM + 1GB volume ≈ **$5–8/month**. Well inside budget.
- Ops simplicity: one CLI (`flyctl`), one `Dockerfile`, one `fly.toml`.

**Data sizing (corrected from initial estimate):** parquet caches are **~14MB total**, not "hundreds of MB." The smallest Fly tier easily handles it.

**Alternatives considered:**
- **Hetzner CX11 VPS (€4.5/mo)** — cheaper, but you own systemd, Caddy, ufw, upgrades, backups. Pick this only for ops practice. Rejected for Phase 1.
- **Railway** — similar DX to Fly, slightly pricier, fine fallback. Rejected because Fly's primitives map cleaner (volumes, scheduled machines).
- **Render** — free tier sleeps; paid doesn't have usable volumes on cheapest plan. Rejected.
- **Google Cloud Run + Cloud Scheduler** — same cold-start + scheduler issues as Vercel unless you pay for min-instances (erases cost advantage). Rejected.
- **AWS Lightsail / EC2** — too much manual setup for a solo side-project at this stage. Rejected.

---

## Architecture — split deployment (Option C)

- **Dashboard** (static Vite build): Vercel or Cloudflare Pages. Either works; Vercel is fine for this role.
- **API + scheduler + filter cron**: Fly.io with `/data` volume.
- **Local dev**: unchanged. `VITE_API_BASE_URL` picks backend (`http://localhost:8000` or `https://fire.fly.dev`).

Why split:
- Static dashboard on edge CDN is cheap, fast, trivially reliable.
- Trading logic on always-on Linux box is the right primitive for APScheduler + fcntl + file state.
- Clear failure domains. CDN blip ≠ trading halt; Fly deploy ≠ dashboard shell broken.

Rejected:
- **Option A (single VPS, everything):** simpler but doesn't leverage the right tools for each job. Fine fallback if the split adds too much cognitive load.
- **Option B (live on cloud, API+dashboard local):** strictly worse. API needs to be where state is, otherwise every dashboard request tunnels into a server that may be off.

**Dashboard target: Vercel (decided).** George has used Vercel extensively and prefers the DX. Cloudflare Pages was functionally equivalent but Vercel wins on familiarity. Dashboard stays a static Vite build — none of the Vercel-incompatible pieces (APScheduler, fcntl, persistent disk) are in the dashboard anyway.

---

## Live vs. backtest surface — what ships to the cloud

Key insight (2026-04-20): the live module does not depend on `backtesting/` at runtime. Zero imports. They share a repo but not a call graph. The cloud image is a **strict subset** of the codebase, not a mirror.

**Live module (ships to Fly):**
- `execution/` — rebalance, broker, risk manager, validation gate, rebalance log
- `strategies/*.py` — but only `generate_signals()` methods + the filter functions + PORTFOLIOS config
- `data/pipeline.py`, `data/crypto.py`, `data/sp500.py`, `data/snapshots.py`, `data/trading_dates.py`, `data/correlation.py`
- `api/main.py` (trimmed), `api/locks.py`, `api/routes/portfolio.py`, `api/routes/orders.py`, `api/routes/strategies.py`
- `scripts/filter_check.py`
- `data/risk_state/*.json` + relevant `data/raw/*.parquet` on the persistent volume

**Research-only (stays laptop-local, excluded from the cloud image):**
- `backtesting/` — all of it (metrics, validation, bootstrap, account_adapters)
- `scripts/run_validation.py`, `scripts/walk_forward_refit_*.py`, `scripts/crypto_robust_opt.py`
- `mode2/` — PEAD research, separate workstream
- `api/routes/backtests.py` — dashboard's interactive backtest runner; hit the laptop API from the Backtests tab, not the cloud API
- `data/validation_reports/*.md` — produced by backtest, not read by live
- `References/`

**The one artifact that crosses the boundary:**
- `data/risk_state/validation_state.json` — produced by `scripts/run_validation.py` (laptop), read by `execution/validation_gate.py` (cloud). The gate blocks any account without a passing record, so the file *must* exist in the Fly volume.
- Workflow: run validation quarterly on laptop → commit or `fly volumes` sync the JSON → cloud picks it up on next rebalance.
- This is the right shape: **research on laptop, execution in cloud, one flat file as the contract.**

**Implied cleanup (Phase 0, below):** `strategies/portfolio.py` currently mixes live code (PORTFOLIOS config, `compute_spy_trend_filter`, `compute_btc_trend_filter`) with backtest code (`run_combined_portfolio`, `apply_vol_scaling`, `_generate_strategy_returns`, `run_equity_core`). Split into `strategies/portfolio_config.py` (live) + `strategies/portfolio_backtest.py` (research) so the dependency graph is legible and the cloud image doesn't pull in pandas ops it never executes.

---

## State migration — everything to the Fly volume

Fly volume mounted at `/data`. Existing paths:

| Current path | Destination | Notes |
|---|---|---|
| `data/risk_state/filter_state.json` | `/data/risk_state/` | Keep. Atomic tmp-rename already handles crash safety. |
| `data/risk_state/circuit_breaker_acct*.json` | `/data/risk_state/` | Keep. Must survive deploys — that's the whole point. |
| `data/risk_state/validation_state.json` | `/data/risk_state/` | Keep. Regenerated by `run_validation.py` anyway. |
| `data/risk_state/rebalance_lock_acct*.lock` | `/data/risk_state/` | `fcntl.flock` works on ext4. **Do not** use network-mounted FS. |
| `data/risk_state/snapshot_lock_acct*.lock` | `/data/risk_state/` | Same. |
| `data/rebalance_log.jsonl` | `/data/` (+ weekly R2 snapshot) | Audit trail. Append-only, fine on disk. |
| `data/raw/*.parquet`, `data/processed/*.parquet` | `/data/` | 14MB total. `write_parquet_atomic` already safe. Live uses these for same-day signal generation; not backtest-specific. |
| `data/validation_reports/*.md` | **Stays laptop-only** | Backtest output, not read by live. No need to ship. |
| `data/filter_check.log` | `/data/` + log drain to Better Stack | See Observability. |

**Deliberately skip Postgres for Phase 1.** Introducing a DB means rewriting `log_rebalance`, `RiskManager` breaker persistence, `validation_gate`, `snapshots.py` — multi-week refactor for zero benefit on a single machine. Revisit only if we go multi-region or multi-writer (unlikely).

**`fcntl.flock` constraint — HARD CAP AT ONE MACHINE.** File locks only protect within one machine's kernel. `fly scale count 2` would silently bypass `dual_rebalance_lock` — two machines could enter `compute_rebalance` simultaneously and double-submit orders. The Phase 5 hardening MUST include either:
- (a) `fly.toml` config that forbids scaling past 1, documented in the runbook, OR
- (b) Swap `api/locks.py` for Postgres advisory locks (non-trivial refactor; flag as future work).

---

## Secrets

- **Local dev:** `.env` stays as-is. `python-dotenv` loads it. Confirm `.env` is `.gitignore`d.
- **Cloud:** `fly secrets set ALPACA_API_KEY=... ALPACA_API_KEY_2=... ALPACA_API_KEY_3=... ALPACA_API_KEY_4=... FINNHUB_API_KEY=... ALPHA_VANTAGE_API_KEY=... ALPACA_SECRET_KEY=... ALPACA_SECRET_KEY_2=... ...`. Injected as env vars at runtime; no code changes needed since `alpaca_broker.py` already reads from `os.environ`.
- One tiny code tweak: `scripts/filter_check.py` currently calls `load_dotenv()` unconditionally. Fine — `load_dotenv` is a no-op when `.env` is absent, and on Fly the env is already populated.
- **Phase 5 split (paper vs live):** separate Fly apps (`fire-paper`, `fire-live`), separate secret stores, separate Alpaca keys. Never share secrets across paper and live.

---

## Observability / alerting

Laptop uses `osascript` macOS notifications. Server needs:

- **Logs:** Fly's built-in log stream → **Better Stack (Logtail)** free tier (1GB/mo, 3-day retention) or **Grafana Cloud Logs** free tier (50GB/mo). Both accept Fly log drains directly.
- **Uptime:** Better Stack Uptime free tier (10 monitors, 3-min checks) hitting `/api/health` every 3 min. Alert on 2 consecutive failures.
- **Event alerts:** structured log lines `event=filter_flip`, `event=circuit_breaker_tripped`, `event=rebalance_failed`, `event=order_failed`. Log-based alerts → webhook → **Pushover** ($5 one-time) or **Telegram bot** (free).
- **Cron heartbeat — don't skip this.** **healthchecks.io** free tier. Both the crypto rebalance and the filter_check cron `curl $HC_URL/ping` on success. Miss the window → healthchecks pages. This catches "scheduler silently didn't run" — the failure mode the current laptop setup can't detect.
- **Rebalance journal offsite copy:** optional weekly rsync of `rebalance_log.jsonl` to Cloudflare R2 (free tier) for audit.

---

## API authentication — open concern, must address in Phase 1

Current FastAPI runs on localhost with **no auth**. Once it's on Fly on a public URL, anyone with the URL can hit `POST /api/orders/rebalance/execute` and trigger trades. This is a real security gap. Options:

- **Simplest:** shared secret in header (`X-API-Key`), checked by FastAPI middleware. Dashboard sends it from `VITE_API_KEY` env. Not great (key in browser), but bounded blast radius on paper.
- **Better:** OAuth via Cloudflare Access or Tailscale Funnel in front of Fly. Dashboard still public, API gated by identity provider.
- **Pre-real-money:** required. Cannot graduate without it. Cloudflare Access free tier covers one user.

**Decision needed before Phase 1.** Flag: add an auth layer even for paper — it's practice for the real-money discipline and costs nothing now.

---

## Migration phases

### Phase 0 — Decouple live from backtest (local only, no cloud yet)
This is the near-term work. Everything happens on the laptop; the existing stack keeps running throughout. Purpose is to make the live surface explicit *before* we ever touch Fly — so that when we do, the Dockerfile copy-list writes itself and we're not also debugging a refactor at the same time we're debugging a deploy.

- **Split `strategies/portfolio.py`** into `portfolio_config.py` (live: PORTFOLIOS dict, `compute_spy_trend_filter`, `compute_btc_trend_filter`) and `portfolio_backtest.py` (research: `run_combined_portfolio`, `apply_vol_scaling`, `run_equity_core`, `marginal_portfolio_contribution`, `_generate_strategy_returns`). Keep `strategies/portfolio.py` as a re-export shim during the transition so nothing breaks.
- **Audit live imports.** Grep every file under `execution/`, `api/`, `scripts/filter_check.py` for any import from `backtesting/`, `mode2/`, or the backtest half of `portfolio.py`. There should be zero after the split. (AUDIT_MONTH2.md C4 is a reminder that the two halves used to differ silently — this audit closes the other direction: the live half doesn't accidentally depend on the research half.)
- **Document the laptop↔cloud contract.** `data/risk_state/validation_state.json` is the only file that has to move from one side to the other. Add a sync step to `scripts/run_validation.py` that copies the fresh file to a predictable path, and later a runbook entry for uploading it to the Fly volume.
- **Keep running locally as-is** for as long as we want. The refactor should be 100% behavior-preserving — nothing about how the live book trades changes. The only deliverable is "you can now draw a clean line around the live surface."
- **Success:** all tests + dashboard still green; grep proves no live→backtest imports; laptop continues executing scheduled rebalances correctly for at least 2 weeks post-refactor before we start Phase 1.
- **Reversible:** the split is pure refactor; a single git revert undoes it.

### Phase 1 — Dockerize + deploy API to Fly, keep local cron
- Write `Dockerfile` using `python:3.12-slim` + `uv sync`.
- `fly launch --no-deploy`, create 1GB volume at `/data`, set secrets, set TZ, deploy.
- Copy current `data/risk_state/` state files onto the Fly volume (one-time seeding — otherwise filter_state.json is empty on first run and the cron will "seed" it without triggering rebalance, which is actually the desired first-run behavior; pick one).
- Add auth middleware (see above).
- Point dashboard at Fly URL via `VITE_API_BASE_URL` feature flag.
- **Success:** dashboard loads portfolio data from Fly; `/api/health` returns 200; APScheduler log shows 00:05 UTC job registered; auth rejects unauthed requests.
- **Reversible:** flip `VITE_API_BASE_URL=http://localhost:8000`. Nothing destructive.

### Phase 2 — Cut over APScheduler crypto rebalance
- Add env flag `FIRE_SCHEDULER_ENABLED=0` (disables APScheduler on laptop dev runs, keeps it on in Fly).
- Watch one scheduled firing (00:05 UTC). Compare `rebalance_log.jsonl` entry to local format.
- **Success:** one successful scheduled rebalance from Fly; `take_snapshot(4)` ran; heartbeat pinged healthchecks.io.
- **Reversible:** flip the env flag back.

### Phase 3 — Move `filter_check.py` from launchd to Fly cron
- Add Fly scheduled machine OR `supercronic` inside container with `CRON_TZ=America/New_York 30 16 * * *` (= 16:30 ET, DST-aware).
- **Risk: dual-run during cutover.** If both laptop launchd and Fly cron fire, `file_rebalance_lock` only protects within one machine — both could execute. Mitigation: unload launchd plist the same day Fly cron goes live. Don't run both in parallel for "safety."
- **Success:** two consecutive daily runs on Fly, `filter_state.json` updated, no duplicate orders visible in Alpaca.
- **Reversible:** re-`launchctl load` the plist, disable Fly cron.

### Phase 4 — Observability hardening
- Wire Fly log drain → Better Stack.
- Add healthchecks.io pings in both cron paths.
- Add log-based alerts: `circuit_breaker_tripped`, `rebalance_failed`, `filter_flip`, `order_failed` → Pushover/Telegram.
- **Success:** deliberately trip an alert (force a validation-gate block in a test path) and receive notification within 60s.

### Phase 5 — Pre-real-money hardening
**Gates — ALL must be satisfied before graduating to real money:**
1. AUDIT_MONTH2 Tier 1 items C4 (vol-scaling), C5 (circuit breaker sim), C6 (fee model) fixed and validation reports re-issued.
2. **≥8 weeks of clean deployed-paper trading on Fly** with no unresolved incidents. "Clean" = all scheduled rebalances fired on time, no circuit breakers tripped by infrastructure flakes (only real signals), no duplicate orders, no silent cron misses caught by healthchecks.io.
3. Calendar date ≥ 2026-07-20 (3 months post paper-clock reset).
4. Runbook drilled end-to-end (not just written).
5. Volume restore flow drilled on a staging app (not just the production one).

**Work in this phase:**
- Split into `fire-paper` and `fire-live` Fly apps. Separate volumes, separate secrets, separate Alpaca keys. `fire-paper` stays running in parallel as the ongoing validation target.
- Daily volume snapshots (`fly volumes snapshots create`). Weekly offsite copy of `rebalance_log.jsonl` to R2.
- Enforce `fly scale count 1` via config + runbook. Ideally add a startup assertion (`fly machines list` call at boot, refuse to start if >1).
- Write the runbook: reset circuit breaker remotely, force-liquidate an account, rollback a deploy, restore from snapshot, rotate Alpaca keys, recover from volume corruption. Lives in-repo as `RUNBOOK.md`.
- Drill the restore flow: snapshot → fresh app → reconstitute `validation_state.json` + `filter_state.json` + `circuit_breaker_acct*.json` + verify `dual_rebalance_lock` serializes post-restore.
- Drill the deploy-during-market-hours flow: trigger a deploy at 16:25 ET, confirm the filter cron at 16:30 ET either fires on the new machine or gets skipped cleanly (and healthchecks.io pages if skipped).

---

## Risks and open questions

**Decided:**
- ✅ ET is the reference timezone (codified in CLAUDE.md).
- ✅ Fly.io as primary platform for the live service.
- ✅ Vercel for the dashboard static bundle (user preference, good DX fit).
- ✅ Option C split architecture (dashboard on Vercel, live on Fly, local dev unchanged).
- ✅ File-based state on Fly volume; skip Postgres in Phase 1.
- ✅ Phase 0 refactor (decouple live from backtest) happens locally first; no cloud work until that's stable for weeks.
- ✅ Timeline: cloud deployment is weeks out. Refactor + local validation first.

**Open — need decisions before Phase 1 (not Phase 0):**

1. **API authentication mechanism.** Shared secret header for Phase 1, or invest in Cloudflare Access / Tailscale Funnel from the start? Cloudflare Access is free for one user and is the right long-term answer; shared secret is ~15 min of work.
2. **Alerting channel.** Pushover ($5 one-time, reliable push notifications to phone) or Telegram bot (free, but requires installed Telegram app)? Need to pick one to implement in Phase 4.
3. **CI/CD for deploys.** Manual `flyctl deploy` from laptop, or GitHub Actions on push to `main`? Manual is fine for Phase 1–2; automation is a Phase 4/5 polish item.
4. **Budget ceiling.** Estimated $5-8/mo Fly + free tiers for everything else. Any hard cap?
5. **When to split paper/live.** Phase 5 = pre-real-money. Is that driven by a calendar date, by the AUDIT_MONTH2 Tier 1 C4/C5/C6 fixes landing, or by a separate gate?

**New concerns raised in discussion — folded in:**
- **Deployed-paper is its own validation phase**, not a rehearsal. Phase 5 gate now requires ≥8 weeks of clean deployed-paper time. Infrastructure bugs (wrong-TZ cron, silent volume unmount, stale log drain, auth bypass) only surface in production.
- **Dockerfile & uv.** Use the official `ghcr.io/astral-sh/uv` base image or install uv in `python:3.12-slim`. Run `uv sync --frozen` in the build so the container uses the locked dependency versions. Multi-stage build keeps the final image small (exclude `backtesting/`, `mode2/`, `scripts/run_validation.py`, `References/`, `data/validation_reports/` per the decoupling section).
- **Log rotation.** `data/filter_check.log` grows unbounded. Fine for weeks, not forever. Either (a) rely on the Better Stack log drain and truncate the local file monthly, or (b) add `logging.handlers.RotatingFileHandler` (10MB × 5 files). Pick (a) — simpler.
- **Dashboard auth on mobile.** If we go Cloudflare Access, make sure George's phone can authenticate without friction when he's nomading. Cloudflare has a WARP client that handles this, but worth a 15-min test before committing to that auth path.
- **Runbook draft can start in Phase 4.** No need to wait for Phase 5. The skeleton (how to reset a breaker, how to disable a scheduler) is writable the moment the endpoints exist on Fly.

**Sharp edges flagged:**
- **Single-machine constraint** (fcntl limitation). Must never `fly scale count 2`. Documented in runbook; ideally enforced in `fly.toml`.
- **Dual-run window during Phase 3.** Laptop launchd + Fly cron overlap = potential double-rebalance. Cut over in a single session, don't run in parallel.
- **Timezone at the container layer.** Must install `tzdata` in the Dockerfile and either use `CRON_TZ=America/New_York` with supercronic, or set `TZ=America/New_York` in `fly.toml` env. Missing either = cron fires at wrong UTC time.
- **APScheduler clock drift.** Fly Machines sync via NTP — fine. Worth a startup assertion (`assert abs(datetime.utcnow() - ntp_time) < 1s`) to catch misconfigured containers.
- **Alpaca latency / region.** Fly region default `iad` (Virginia) is ~ms from Alpaca us-east. Don't pick EU/APAC.
- **Deploy during cron window.** Fly deploys stop + replace the machine. In-flight locks release (good), but backfill-on-startup re-runs (acceptable, logs a lot). Don't `flyctl deploy` at 00:04 UTC or 16:29 ET.
- **Dashboard mobile UX.** Digital-nomad user sees laptop-local time. Dashboard should surface current ET time and the next rebalance window — otherwise `first Monday of month` is cognitively expensive when you're in Lisbon. Minor UX item.

---

## References

- `CLAUDE.md` — system overview, ET time convention, current schedule
- `AUDIT_MONTH2.md` — C4/C5/C6 sim-live parity findings gating the Phase 5 real-money graduation
- `api/main.py` — APScheduler lifespan to be cut over in Phase 2
- `scripts/filter_check.py` + `scripts/com.fire.filter-check.plist` — launchd cron to be migrated in Phase 3
- `api/locks.py` — fcntl lock implementation, single-machine constraint source
- `data/trading_dates.py` — ET-stable date helpers (already in place from Tier 3 D1/D2 fixes)
