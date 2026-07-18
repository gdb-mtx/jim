# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

**Bigger picture:** FIRE is one piece of George's bridge-to-59.5 financial plan. The full life picture — net worth, property sales, SEPP 72(t), income targets, risk tolerance — lives in **FIREMaster** (`/Users/george/Desktop/Projects/FIREMaster`). Not all research that touches FIRE is a factor-trading strategy. Some serves income generation, yield harvesting, or life-design objectives with different evaluation criteria. When George brings research from outside (Gemini sessions, personal analysis), engage with the thesis on its own terms before reaching for the CAGR/Calmar gates.

### Key Documents
- **`CAPABILITIES.md`** — standing system-capabilities brief (LP / operator / future-self framing). Inventory + honest limits + peer comparison in one place. Update as the system evolves.
- **`HISTORY.md`** — resolved fixes and decision deltas (April 2026 fix pack, A4 first-entry cascade, framework changes). Canonical per-item description for every C/S/D/R label referenced in code or commits. Look here first when a code path mentions "post-CN fix" and you want to know what changed. The verbose original audit cycle (status-threaded discovery + follow-up sessions) is at `docs/archive/AUDIT_MONTH2.md`; the 4.7-era re-review checklist is at `docs/archive/AUDIT_47.md`. Both are time-capsules — read for forensic context only.
- `STRATEGIES.md` — OOS scorecards, research strategy tables, universe definitions, filters & overlays, strategy source files
- `VALIDATION.md` — CAGR-first evaluation framework (v2, 2026-04-18)
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `BOOK_SHAPE.md` — what the book IS, what it ISN'T, and what functional components are missing (crisis alpha, non-price edge, regime adaptivity). The pivot from "hunt for A5" to "complete the book's architecture." Read before proposing new strategies.
- `docs/research/` — open research scoping. Active tracks:
  - `EVENT_KILLTESTS_JUL2026.md` — **2026-07-13 canonical record**: all four event streams (buybacks, deletions, spinoffs, insider clusters) KILLED/unfundable on 2022-26 data; A5-Events refuted as a concept; VIX tail leg priced; carry funding-trigger documented. Supersedes the event vectors in BREAKTHROUGH_VECTORS.
  - `MACRO_COMPOSITE_EVAL.md` — 2026-07-18 pre-registered eval: composite ships alert-only (34-56 day crisis leads); exposure-scaling rejected. Gap 3 closed.
  - `BREAKTHROUGH_VECTORS_MAY2026.md` — 2026-05-26 diagnostic. Partially superseded: insider clusters / spinoff drift / VIX carry killed or repriced by the two docs above. Still-open vectors: crypto on-chain microstructure, CEF discount reversion.
  - `HighYield_Strategy_STRC_NVDY_AMZY.md` — yield-harvesting flywheel (bridge-income strategy, different objective function than Mode 1 — see "Research Tracks" below)
  - `ML_REGIME_OVERLAY.md` — LSTM/XGBoost as standalone strategy (A5 candidate or A4 replacement) OR book-level regime overlay (Gap 3). Dual-role — kill gates determine which.
  - `RATE_VOL_SCOPE.md` — A5 candidate, MOVE-conditional TLT reversal (shelved: MOVE at multi-year lows)
  - `PLAN_MODE2.md` — Mode 1+2 strategic plan, Phase A live
- **FIREMaster** (`/Users/george/Desktop/Projects/FIREMaster`) — the full financial picture, bridge-plan projections. Yield strategy deep research docs (`STRATEGY_CAPSULE.md`, `BRIDGE_STRATEGY_REVIEW.md`, `SCOUT_REVIEW_MAY2026.md`) moved to `docs/archive/` here in FIRE as of 2026-05-13.
- `DEPLOYMENT_PLAN.md` — 24/7 cloud deployment research for the live trading module (Fly.io primary, 5-phase migration plan). Paper-first; pre-real-money hardening in Phase 5.
- `AUTOMATION.md` — reference for the A4 daily rebalance automation: cron job, cron filter monitors (equity + crypto), sleep behavior, install commands. (Scheduler migrated launchd→cron 2026-05-28 after macOS BTM kept silently disabling the agents; APScheduler before that, retired 2026-05-05.)
- `DATA_SOURCES.md` — standing observation that yfinance is the root cause of nearly every cache-corruption incident, with an incident log and candidate replacements (Alpaca/Polygon/hybrid). Becomes load-bearing at Phase 5 (real money).
- `docs/archive/` — superseded design docs and time-capsule research (PLAN, HUNT_APR2026, AUDIT, AUDIT_MONTH2, AUDIT_MONTH2_REVIEW, AUDIT_47, DECISIONS_RESOLVED, OPS_DASHBOARD_PLAN, HANDOFF_ALPACA_BARS). Read for historical context only.
- `References/` — Original 2020 proposal and Ernie Chan books

### Project Decisions
- **Broker**: Alpaca (primary), QuantConnect (research only when needed)
- **Backtesting**: vectorbt
- **Frontend**: React + TypeScript + TradingView Lightweight Charts (v5)
- **Backend**: Python + FastAPI
- **Risk**: Equal-weight top-N position sizing (at strategy layer) + SPY/BTC trend filters + vol-scaling overlay + a two-tier drawdown monitor (**-10% dashboard alert**, **-35% catastrophe halt with manual reset**). The -10% tier is a dashboard banner only, not persisted, no notifications. The -35% tier is the only persisted state (`{"halted": bool}`). Older controls (-15% auto-halt, -10% strategy-level breaker, 2% rule + 20% position cap) are retired — see HISTORY.md C5/C7. Kelly criterion is computed as a diagnostic in `backtesting/metrics.py` but NOT used for sizing — vol-scaling (Moreira & Muir 2017) replaced it because our factor strategies can estimate volatility reliably but cannot estimate forward expected returns per position, which is what Kelly requires. Vol-scaling is the reduced-form Kelly that sidesteps the hardest estimation problem. See CAPABILITIES.md for the full rationale.
- **Evaluation framework (v2, 2026-04-18)**: CAGR-first scorecard, not Sharpe. **Applies to Mode 1 factor-trading strategies (momentum, trend, reversal, mean-reversion).** Primary gates: OOS CAGR ≥ 15%, OOS MaxDD ≥ -40%, OOS Calmar ≥ 1.0, OOS/IS CAGR ratio ≥ 70%. Full scorecard (MAR, Sterling, Burke, Pain, Ulcer, UPI, Sortino, Omega, Gain-to-Pain, time underwater, max recovery days) reported for context. Sharpe shown informational only — not gated. See `VALIDATION.md`. **Not all research uses these gates** — yield/income strategies, bridge-plan research, and life-design explorations have their own success criteria (e.g., sustainable withdrawal coverage, principal preservation, total return with DRIP).
- **Statistical validation**: Six-test scorecard (all required before real money; quarterly re-validation enforced via gate):
  - **Test 1** — OOS holdout (train 2010-2022, test 2023-today).
  - **Test 2** — Rolling OOS with fixed parameters.
  - **Test 3** — Parameter stability across half-A/half-B splits (crypto only; other accounts skip).
  - **Test 4** — Block bootstrap CAGR p5/p50/p95 (gated: p5 ≥ 0%).
  - **Test 5** — Portfolio fit (satellite marginal contribution; not gated).
  - **Test 6** — Walk-forward REFIT vs defaults (non-gating). Per-window grid search on adapter-defined `refit_param_grid`; PASS if defaults within 10% of refit or better, REVIEW only if refit stably beats defaults by >20%. Strategy-discovery pattern: new candidates get dropped in as `refit_strategy_factory` + grid on an adapter or run via `scripts/walk_forward_refit_*.py`.
- **No shorting (current constraint, not permanent)**: Use reverse ETFs instead when needed. Avoids margin/borrow complexity on Alpaca. BOOK_SHAPE identifies IBKR + futures as the real crisis alpha unlock — revisit this constraint if/when broker migration happens.

### Live Architecture (A1 + A2 active; A3, A4 retired)
Factor diversification across Alpaca paper accounts. A3 (2026-04-21) and A4 (2026-07-13) are retired; both slots are preserved for successor strategies (candidates: A5-Events pooled event sleeve, VIX tail leg, basis carry — see `AUDIT_FABLE.md` §5).

- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter + book-level vol-scaling (cap 1.5, added 2026-07-18) — profits when trends persist. Every-21-trading-days rebalance (manual).
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling (cap 1.5, restored 2026-07-18) — crisis alpha + defensive. Every-21-trading-days rebalance (manual).
- **Account 3 (FIRE 0.3 — RETIRED)**: Slot preserved for future strategy. See `DECISIONS_RESOLVED.md`.
- **Account 4 (FIRE 0.4 — RETIRED 2026-07-13)**: Was Crypto Momentum Rotation (top 2 of 9 coins, BTC 125d SMA filter + vol-scaling, daily cron). Retired on three legs: walk-forward edge decay (newest window +9.6% CAGR, Calmar 0.87 < 1.0 gate), +17.9pp live drag traced to bug-era churn and never re-validated live, unreachable 40%-upgrade clock. The 33%→40% pre-commitment is void. Canonical narrative: `HISTORY.md` 2026-07-13. Hourly cron left in place — validation gate blocks it cleanly (`skipped`, once/day).

Combined OOS for the current 2-account book (A1+A2 50/50, 2026-07-18 configs, net of costs): **CAGR +24.1%, MaxDD -8.7%, Calmar 2.77**. Realistic live estimate: Calmar ~2 (correlations spike in crises; both accounts now extend to 1.5× in calm regimes, so losing days scale too). Historical pre-retirement combined numbers are in git history and `HISTORY.md`.

Multi-account credentials in `.env` (`ALPACA_API_KEY` + `_2`/`_3`/`_4`). `AlpacaBroker(account=1|2|3|4)` selects. Rebalance schedule: A1/A2 every 21 trading days anchored to 2026-04-21 (manual, ~3:00 PM ET), filter monitor every 4h (cron). See `AUTOMATION.md` for full operational detail. Upcoming A1/A2 rebalance dates: 2026-07-22 (Wed), 2026-08-20 (Thu).

### Strategies

**See `STRATEGIES.md`** for full OOS scorecards, research/building-block tables, universe definitions, filters & overlays, and strategy source files. Quick status: A1 PASS (CAGR 31.2% with book vol-scaling, revalidated 07-18), A2 PASS (CAGR 16.8% at cap=1.5, revalidated 07-18), A3 RETIRED, A4 RETIRED. Open caveat: C3 (S&P 500 survivorship bias, ~1-2pp on A1).

### Risk Controls (summary — see `AUTOMATION.md` for operational detail)

- **Time convention:** ET (America/New_York) is the system reference timezone. Use `data/trading_dates.py` helpers (`today_et`, `utc_ts_to_et_date`), never `date.today()` or `datetime.now()`.
- **Filter monitor:** SPY 200d + BTC 125d filters checked every 4h via cron. Auto-rebalances on flip. Each SPY run also computes two alert-only signals (macOS notification, never trade): VIX9D/VIX3M tail signal (≥1.10) and the 5-sensor macro composite (alerts on vote changes ≥2; led SPY-200d by 34-56 days in 2018/2020/2022 — see `docs/research/MACRO_COMPOSITE_EVAL.md`). Exposure management is decoupled from signal rotation — speed matters (daily filter = Sharpe 1.27 vs monthly = 0.79).
- **Drawdown monitor:** Two tiers — **-10% dashboard alert** (amber banner, non-blocking) and **-35% catastrophe halt** (per-account kill-switch, manual reset required, 403 on rebalance). Neither threshold fires in 16y of backtest.
- **Concurrency:** All rebalance entry points serialize via `dual_rebalance_lock` (async + file lock). Contention → 409 / `status="locked"`.
- **Sub-broker-minimum rejections** on A4 (sub-$10 BTC dust orders) are expected and harmless — revisit only if recurring >30 days.

### Architecture (summary — see `docs/architecture.d2` for the visual, explore the code for detail)

**Data:** `data/pipeline.py` (ETF/stock cache), `data/crypto.py` (backtest), `data/alpaca_crypto_bars.py` (live), `data/snapshots.py` (equity history), `data/trading_dates.py` (ET helpers), `data/plausibility.py` (value guards).

**Strategies:** `strategies/portfolio_config.py` (LIVE surface — PORTFOLIOS dict, filters), `strategies/portfolio_backtest.py` (RESEARCH surface). Individual strategies in `strategies/*.py`. `strategies/portfolio_config.py` has a hard invariant: zero imports from `backtesting/` or `mode2/`.

**Execution:** `execution/rebalance.py` (weights → orders), `execution/risk_manager.py` (drawdown), `execution/vol_scaling.py` (EWMA), `execution/validation_gate.py` (rebalance gate), `execution/alpaca_broker.py` (multi-account), `execution/rebalance_log.py` (JSONL audit).

**API:** FastAPI on :8001. Live routes (`/portfolio`, `/orders`, `/ops`) ship to cloud. Research routes (`/backtests`, `/strategies`) are laptop-only.

**Dashboard:** React + Vite + TradingView on :5174. 5-tab account switcher, equity charts, correlation monitor, rebalance UI, ops panel, backtests.

**Mode 2:** `mode2/` — PEAD pipeline (Finnhub EPS + Insider Monkey transcripts + scoring prompts + tracker). CLI: `uv run python3 -m mode2.run_analysis {fetch|summary|analyze|status}`.

**Scripts:** `scripts/start.sh` (both servers), `scripts/filter_check.py` + `scripts/cron_filter_check.sh` (cron 4h, incl. VIX tail + macro composite alerts), `scripts/daily_crypto_rebalance.py` + `scripts/cron_crypto_rebalance.sh` (cron daily, gate-blocked since A4 retirement), `scripts/run_validation.py` (6-test runner), `scripts/signal_tracker.py` (A4 execution drag, historical), `scripts/macro_composite_eval.py` (pre-registered eval), `scripts/{buyback_drift,deletion_reversion,spinoff_drift,insider_cluster}_poc.py` (reusable event kill-test harnesses; caches in gitignored `data/research_cache/`).

### Running the Project
- **Both servers**: `./scripts/start.sh` (recommended). Backend on :8001, frontend on :5174. Port :8000 is FIREMaster.
- **Backend only**: `uv run uvicorn api.main:app --reload --port 8001`
- **Frontend only**: `cd dashboard && npm run dev`
- **Validation**: `uv run python3 scripts/run_validation.py --account N` — runs Tests 1-6. See `VALIDATION.md` for the strategy-discovery workflow.
- **Filter monitor**: Runs automatically via cron every 4h. Manual: `uv run python3 scripts/filter_check.py` (or `--dry-run`). Install commands in `AUTOMATION.md`.
- **Signal tracker**: `uv run python3 scripts/signal_tracker.py` — A4 signal-only vs live return decomposition. `--since YYYY-MM-DD` for recent window.

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript
- **Async endpoints**: All FastAPI `async def` endpoints MUST use `asyncio.to_thread()` for blocking calls (Alpaca API, yfinance downloads, parquet I/O, pandas computations). Calling blocking functions directly freezes the event loop and makes the entire server unresponsive to concurrent requests. This applies to route handlers and scheduled jobs alike.
- **Maintainability is a first-class constraint.** George works on this alone with AI partners and re-enters the codebase after gaps. A clever optimization that requires holding three files in your head is worse than a boring implementation a future session can grok cold. Optimize for: fewer surfaces to remember, fewer invariants to re-verify, fewer places a change has to land. Before adding a new file/abstraction/mirror, ask whether it makes the next person's job easier or harder. If a "mirrors X" docstring is needed, the two implementations should probably be one.

### Working with Claude — behavioral defaults

<!-- 4.7-SPECIFIC GUARDRAILS: The rules below were written to correct recurring failure
     modes observed with Claude 4.7 (over-engineering, defensive gatekeeping of new ideas,
     deference to casual preferences, measuring everything against existing infrastructure).
     Opus 4.6 does not exhibit these patterns. SKIP this section if running on 4.6.
     Re-activate if Anthropic forces a 4.7 upgrade. -->

**The following rules apply to Claude 4.7 only.** Opus 4.6 handles these correctly by default. Kept here in case of forced model upgrade.

<details>
<summary>4.7 behavioral corrections (click to expand)</summary>

**The anti-defensive rule:** The rules below are operational guardrails for building code. They are NOT evaluation criteria for new research. When George brings a new idea, strategy, article, or research direction, the FIRST response must engage with what the idea is trying to do — not measure it against existing infrastructure, validation gates, or account slots. The pattern of "let me check if this fits our existing system" before understanding the thesis has been the #1 recurring failure mode with 4.7 (documented 2026-05-13 after 3 separate instances in one session). New ideas get evaluated on their own terms first. Existing infrastructure adapts to good ideas; good ideas don't get demoted to fit existing infrastructure.

- **Preference ≠ requirement.** Offhand "I like X" is input, not a constraint. Give the engineering recommendation first; surface preference deviations as labeled trade-offs.

- **Stop and confirm before changes >50 lines or any new file/architecture decision.** State the smallest viable alternative + what you're proposing + why, and wait for a yes. *This applies to CODE changes, not to research discussions. Don't use this rule to gatekeep exploration.*

- **Diagnose before workaround.** When something looks broken, run the diagnostic that shows what the upstream actually thinks before proposing infrastructure to route around it. Surface "we could just wait" or "the broker handled it" as peer options, not footnotes. Don't duplicate authoritative external validation client-side on first occurrence.

- **Honesty over flattery in commits and docs.** When a decision is driven by preference rather than engineering merit, label it as such. Future-you re-reading a doc should see what was actually decided and why.

- **Simplicity over complexity.** When two designs both work, take the smaller one. Prefer one obvious code path over two clever ones; a single source of truth over parallel implementations whose equivalence has to be re-proven. Complexity has consistently been the failure mode here.

- **Test live↔backtest semantic parity, not just numeric parity.** When a live system reads "the same data" backtest used, ask: are the bars settled? Closed or still-forming partial? Timezone assumptions implicit? The C9 partial-bar contamination silently diverged live from backtest for ~14 days because "yfinance returned a row, therefore it's a closed bar" was an unstated assumption. First question for any live↔backtest gap: "is the strategy reading the same kind of data point in both modes?"

- **Match the evaluation framework to the strategy's objective function.** Not everything is a factor strategy competing for Calmar supremacy. When George brings yield research, bridge-income ideas, or life-design explorations, evaluate them by what they're trying to do (income floor, principal preservation, withdrawal coverage) — not by the Mode 1 CAGR/Calmar gates. The defensive pattern of measuring every new idea against the existing book's metrics is the single most recurring failure mode with 4.7. Engage with the thesis first, identify the right success criteria second, then evaluate.

- **Idea Farm mode for strategic stagnation.** When George signals defensive-cycle fatigue ("do nothing new" verdicts repeating, "breakthrough" in mocking quotes, austerity framing he rejects, "we need bold"), invoke the `/idea-farm` skill BEFORE running another optimization round. Skill at `~/.claude/skills/idea-farm/`. Default cadence: monthly minimum.

</details>

### Current Phase & Next Steps

**Status (2026-07-18 — post build-out week):** The taken-down-to-raise-again week. A4 retired (edge decay + bug-era drag, `HISTORY.md` 07-13). All four public-event streams killed on fresh data — A5-Events dead as a concept (`docs/research/EVENT_KILLTESTS_JUL2026.md`). The breakthrough came from **sizing engineering instead**: A1 book-level vol-scaling (OOS 25.3%→31.2%, Calmar 2.84) + A2 cap=1.5 restoration (11.0% MARGINAL→16.8% PASS) ≈ +4pp validated book CAGR, live from the 07-22 rebalance. Two alert-only signals watch the book (VIX tail, macro composite — operator runbook in `AUTOMATION.md`). George's standing posture is unchanged: bold builds and honest kills over defensive maintenance; kill-test cheaply before building; the next 2-3 clean rebalance cycles are the live test of the new sizing and the clock on the Q3 real-money checkpoint (A1 clean-window alpha ≥ 0 required — the 04-22→07-17 window lagged SPY, explained by the now-fixed un-relevered design).

**Mode 1 (Structural Alpha):** 2-account live book (A1+A2); build-out of successor sleeves in progress (2026-07-13 session: A4 retired, buyback-drift kill test run, VIX sleeve quantified).
- Account 1: 15 stocks (SM + SPY Filter + book vol-scaling since 07-18) — live since 2026-03-10, OOS CAGR 31.2%. Clean-window live matches signal (no drag); prior SPY lag was the un-relevered design, fixed by the overlay.
- Account 2: 34 positions (Trend + Low-Vol) — live since 2026-03-10. cap=1.5 restored 2026-07-18: OOS CAGR 16.8% PASS (was 11.0% MARGINAL). Live ~flat pre-restore; levered from the 07-22 rebalance.
- Account 4: RETIRED 2026-07-13 at -23.1% live (see `HISTORY.md`).
- Live-tracking clock reset to 2026-04-21 (the Mar 10 → Apr 17 window was compromised by stale-data bug). April 21 is the anchor for the 21-trading-day rebalance cycle.

**Validation status:** A1 PASS (07-18, book vol-scaling, CAGR 31.2%), A2 PASS (07-18, cap=1.5, CAGR 16.8%); expire 2026-10-16. Results in `data/validation_reports/`, state in `data/risk_state/validation_state.json`. A3 + A4 status="retired" — retired accounts are an unconditional block, no override can bypass. `execution/validation_gate.py` blocks FAIL/unvalidated; MARGINAL allowed for paper. Overrides for FAIL/unvalidated/expired only: `FIRE_VALIDATION_OVERRIDE=1` (global) or `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` (scoped). Both surface a WARNING log.

**Open bugs:** Tier 1 closed except C3 (S&P 500 survivorship, ~1-2pp on A1 CAGR — only matters pre-real-money). C10 closed 2026-05-06 by migrating live crypto signal computation to Alpaca's bars endpoint (broker-native, no third-party publishing delay) — see `HISTORY.md` C10/C11 for the authoritative narrative. Tiers 2+3 fully closed. Tier 4 R6/R7/R8/R10/R13/R14/R15 are reporting hygiene, non-blocking. See `HISTORY.md` for per-item detail.

**Mode 2 (Informational Alpha):** Phase A in progress.
- PEAD data pipeline + transcript scraper + scoring prompts + recommendation tracker built (`mode2/`).
- Data sources: Finnhub (EPS surprise, free), Insider Monkey (transcripts, free), yfinance (prices).
- Week 1 (2026-04-15): 6 companies analyzed, 1 long recommendation (C, conviction 4/5), 5 skips. C long at $131.69, stop $125, target $138, 40-day hold (paper).
- **Key learning**: Large-cap PEAD drift is 1-3% (not 5-8% as in academic literature which skews small-cap). Best PEAD opportunities will be mid-caps with less analyst coverage in weeks 2-4 of earnings season.

**Dashboard:** React + TradingView on :5174. Tabs: Live Portfolio (5-account switcher + equity charts + correlation), Rebalance (preview → execute), Ops (filter/validation/events), Backtests. Ticker mapping: yfinance hyphens → Alpaca dots via `to_alpaca_equity_symbol()`.

**Next steps:**
- **Watch the new sizing live (top priority):** 07-22 rebalance runs A1 ×~1.08 and A2 →~1.5× gross for the first time. Verify orders/margin behave per `HISTORY.md` 2026-07-18; then 2-3 clean cycles → Q3 real-money checkpoint (gate: A1 clean-window alpha ≥ 0 vs SPY).
- **Standing George decisions:** VIXY tail leg buy/pass (alert armed; ~5% of book; see `AUTOMATION.md` runbook). Basis carry stays parked until Deribit 30d funding > ~8-10% annualized (monthly one-command probe in `EVENT_KILLTESTS_JUL2026.md`; also worth checking when BTC re-crosses its 125d SMA).
- **Fly.io deployment** (`DEPLOYMENT_PLAN.md`): the durable fix for laptop scheduling and the real-money gate. A weekend of work; next infra priority.
- **Hygiene:** tests/ has 12 pre-existing failures (predate 07-18, verified by stash-diff) — clean up on a slow day. C3 survivorship: Norgate declined 2026-07-18 (George: not worth $30/mo while edges are the constraint); handle pre-real-money by haircutting A1 expectations ~1-2pp or a free sensitivity test.
- **Open research vectors (thin but alive):** crypto on-chain microstructure, CEF discount reversion (BREAKTHROUGH_VECTORS), data-walled small-cap quality-momentum (needs point-in-time data). Kill-test-first discipline applies — one cheap falsification before any build (the 07-13 session pattern).
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season.
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`).
- Mode 2: C recommendation CLOSED 2026-07-13 retro-review — stopped -5.1% on 05-04, then thesis played out fully (high $147.96 on 06-18, past target). Lesson logged in tracker: PEAD holds need time-exits, not tight stops.

### Research Tracks (outside Mode 1/Mode 2 framework)

**Yield / Bridge-Income Strategy (scoped, awaiting decision to prosecute):**
George researched a yield-harvesting "Diversified Flywheel" strategy (STRC/NVDY/AMZY) with Gemini in early-mid May. The strategy spec remains at `docs/research/HighYield_Strategy_STRC_NVDY_AMZY.md`; the deeper bridge-plan-context docs in FIREMaster moved to `FIREMaster/docs/archive/` when the FIREMaster productize pivot became primary (2026-05-13). Track is not currently being prosecuted but is a live candidate. Different objective than Mode 1 — evaluate by income floor + principal preservation + total return with DRIP, not by CAGR/Calmar gates. Worth raising as a Mode 1 breakthrough alternative when ideas-for-breakthrough conversations happen.
