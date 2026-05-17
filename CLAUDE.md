# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

**Bigger picture:** FIRE is one piece of George's bridge-to-59.5 financial plan. The full life picture — net worth, property sales, SEPP 72(t), income targets, risk tolerance — lives in **FIREMaster** (`/Users/george/Desktop/Projects/FIREMaster`). Not all research that touches FIRE is a factor-trading strategy. Some serves income generation, yield harvesting, or life-design objectives with different evaluation criteria. When George brings research from outside (Gemini sessions, personal analysis), engage with the thesis on its own terms before reaching for the CAGR/Calmar gates.

### Key Documents
- **`CAPABILITIES.md`** — standing system-capabilities brief (LP / operator / future-self framing). Inventory + honest limits + peer comparison in one place. Update as the system evolves.
- **`HISTORY.md`** — resolved fixes and decision deltas (April 2026 fix pack, A4 first-entry cascade, framework changes). Canonical per-item description for every C/S/D/R label referenced in code or commits. Look here first when a code path mentions "post-CN fix" and you want to know what changed. The verbose original audit cycle (status-threaded discovery + follow-up sessions) is at `docs/archive/AUDIT_MONTH2.md`; the 4.7-era re-review checklist is at `docs/archive/AUDIT_47.md`. Both are time-capsules — read for forensic context only.
- `VALIDATION.md` — CAGR-first evaluation framework (v2, 2026-04-18)
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `BOOK_SHAPE.md` — what the book IS, what it ISN'T, and what functional components are missing (crisis alpha, non-price edge, regime adaptivity). The pivot from "hunt for A5" to "complete the book's architecture." Read before proposing new strategies.
- `docs/research/` — open research scoping. Active tracks:
  - `HighYield_Strategy_STRC_NVDY_AMZY.md` — yield-harvesting flywheel (bridge-income strategy, different objective function than Mode 1 — see "Research Tracks" below)
  - `ML_REGIME_OVERLAY.md` — LSTM/XGBoost as standalone strategy (A5 candidate or A4 replacement) OR book-level regime overlay (Gap 3). Dual-role — kill gates determine which.
  - `RATE_VOL_SCOPE.md` — A5 candidate, MOVE-conditional TLT reversal (shelved: MOVE at multi-year lows)
  - `PLAN_MODE2.md` — Mode 1+2 strategic plan, Phase A live
- **FIREMaster** (`/Users/george/Desktop/Projects/FIREMaster`) — the full financial picture, bridge-plan projections. Yield strategy deep research docs (`STRATEGY_CAPSULE.md`, `BRIDGE_STRATEGY_REVIEW.md`, `SCOUT_REVIEW_MAY2026.md`) moved to `docs/archive/` here in FIRE as of 2026-05-13.
- `DEPLOYMENT_PLAN.md` — 24/7 cloud deployment research for the live trading module (Fly.io primary, 5-phase migration plan). Paper-first; pre-real-money hardening in Phase 5.
- `AUTOMATION.md` — reference for the A4 daily rebalance automation: APScheduler job, launchd filter monitors (equity + crypto), sleep behavior, install/uninstall commands.
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

### Three-Account Live Architecture
Uncorrelated factor diversification across 3 Alpaca paper accounts, 1/3 each of total book. A3 is retired but its Alpaca account slot is preserved for future strategy assignment.

- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter — profits when trends persist. Monthly rebalance.
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling — crisis alpha + defensive. Monthly rebalance.
- **Account 3 (FIRE 0.3 — RETIRED)**: Slot preserved for future strategy. See `DECISIONS_RESOLVED.md`.
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 2 of 9 coins by 21-day momentum, BTC 125d SMA trend filter + vol-scaling. **Daily rebalance** via launchd at 8:05 PM laptop-local (= 00:05 UTC in EDT). A4 weight **33%**, pre-committed **40% upgrade** once ≥6 months of signal-trading days confirm live Calmar ≥ 2.0. See `AUTOMATION.md` for launchd details.

Combined OOS (2023-01-03 → 2026-04-20, net of costs + vol-scaling): **CAGR +26.5%, MaxDD -6.2%, Calmar 4.28**. Realistic live estimate: **Calmar 2.5-3.5** (correlations spike in crises, A4 live is -7% in 3 weeks vs +5% signal). A4 standalone: **CAGR +38.6%, Calmar 3.05** in backtest (8-coin live universe, post C11 BNB removal).

Multi-account credentials in `.env` (`ALPACA_API_KEY` + `_2`/`_3`/`_4`). `AlpacaBroker(account=1|2|3|4)` selects. Rebalance schedule: A4 daily (launchd), A1/A2 first Monday of month (manual), filter monitor every 4h (launchd). See `AUTOMATION.md` for full operational detail.

### Strategies — OOS scorecard (live accounts)

**Fresh-data OOS per the CAGR-first framework (test window ends 2026-04-20). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION.md`.**

Numbers below are post the C1+C2+C4+C6 fix pack (calendar/ppy convention, BTC MA warmup, live vol-scaling parity, transaction costs), C9 (crypto partial-bar signal contamination, 2026-05-06), C10 (Alpaca-bars migration for live crypto, 2026-05-06), and the 8-coin universe switch (2026-05-17, backtest now uses `LIVE_CRYPTO_UNIVERSE` matching Alpaca's tradeable set — see HISTORY.md C11). See `HISTORY.md` for what each fix changed. **C3 (S&P 500 survivorship bias)** is the one remaining open caveat — A1 standalone CAGR is ~1-2pp overstated; not fixed pre-real-money.

| Strategy | Status | CAGR | MaxDD | Calmar | MAR | Sortino | *Sharpe (info)* |
|---|---|---|---|---|---|---|---|
| **Crypto Momentum (Acct 4)** | PASS | **+38.6%** | **-12.6%** | **3.05** | 3.05 | — | *1.76* |
| **Stock Momentum + SPY (Acct 1)** ⚠ C3 | PASS | **+27.2%** | **-9.9%** | **2.76** | 2.76 | 2.10 | *2.04* |
| **Trend + Low-Vol (Acct 2)** | MARGINAL | **+11.0%** | **-7.3%** | **1.51** | 1.51 | — | *1.37* |
| *Reversal + Momentum (Acct 3)* — retired | RETIRED | *14.5%* | *-7.2%* | *2.03* | — | — | — |

A1 + A4 PASS the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates. **A2 is MARGINAL** — backtest used to leverage the low-vol leg up to 1.5× in calm regimes that live could never realize; cap=1.0 alignment brings it to 11%. MARGINAL is allowed for paper per `execution/validation_gate.py`.

A3's historical numbers retained as MARGINAL per last validation; strategy available in Backtests → Building Blocks as `reversal_blend`.

Research/building-block strategies (in-sample only — never went to a live account, OOS not measured):

| Strategy | Sharpe (IS) | Return (IS) | MaxDD (IS) | Notes |
|---|---|---|---|---|
| Short-Term Reversal + SPY | 1.41 | 12.7% | -10.0% | Anti-momentum |
| Low Volatility + SPY | 1.32 | 14.7% | -11.9% | Defensive |
| Blended Portfolio + SPY Filter | 1.37 | 14.2% | -9.3% | 60/20/20 momentum |
| Stock Momentum (S&P 500) | 1.16 | 15.9% | -18.6% | No filter |
| Cross-Sectional Momentum | 0.85 | 7.0% | -10.8% | ETF-based |
| Time-Series Momentum | 0.85 | 6.2% | -15.2% | ETF-based |
| Multi-Asset Trend | 0.76 | 5.8% | -13.0% | Crisis alpha |
| Dual Momentum (Antonacci) | 0.83 | 7.6% | -19.9% | ETF-based |
| Multi-Timeframe Momentum | 0.67 | 4.1% | -11.0% | Regime fail |
| *SPY Buy & Hold (benchmark)* | *0.87* | *14.5%* | *-33.7%* | — |

- **ETF Universe**: 18 assets (8 broad ETFs + 9 sector ETFs + SHY cash proxy)
- **Multi-Asset Universe**: SPY, EFA, TLT, GLD, DBC (5 uncorrelated asset classes)
- **Stock Universe**: 501 S&P 500 stocks (cached parquet, survivorship bias noted). Coverage gate: trailing 500 trading days ≥80% non-NaN — lets recent S&P additions enter the rotation once they have ~2y of history without corrupting backtests (pre-IPO NaN rows propagate to NaN ranks → excluded from selection for periods before the ticker existed).
- **Crypto Universe**: 9 coins for backtest, 8 coins for live (BTC, ETH, SOL, BNB*, ADA, AVAX, LINK, DOT, XRP). *BNB is in the backtest universe but excluded from live — Alpaca doesn't list it (regulatory non-listing post 2023 SEC v. Binance, see HISTORY.md C11). `data/crypto.CRYPTO_UNIVERSE` is the 9-coin backtest set; `data/crypto.LIVE_CRYPTO_UNIVERSE` is the 8-coin tradeable subset that live signal computation operates on. Quality/volume-gated by design — top-cap L1s and major smart-contract platforms only. Deliberate exclusion of memecoins (DOGE, SHIB, PEPE, etc.) and low-float altcoins. No memecoins (DOGE, SHIB, PEPE) or low-float narrative coins. An ML or alternative crypto strategy may use different data sources (on-chain metrics, funding rates, exchange flows) or a modified universe if justified by the thesis.
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007).
- **BTC 125-day SMA trend filter**: Binary 100% cash when BTC < 125d SMA (sat out all of 2022). Robust-opt picked 125d from 200d/150d/125d/100d grid.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4.
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone.
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period.
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`.

### Risk Controls (summary — see `AUTOMATION.md` for operational detail)

- **Time convention:** ET (America/New_York) is the system reference timezone. Use `data/trading_dates.py` helpers (`today_et`, `utc_ts_to_et_date`), never `date.today()` or `datetime.now()`.
- **Filter monitor:** SPY 200d + BTC 125d filters checked every 4h via launchd. Auto-rebalances on flip. Exposure management is decoupled from signal rotation — speed matters (daily filter = Sharpe 1.27 vs monthly = 0.79).
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
**Scripts:** `scripts/start.sh` (both servers), `scripts/filter_check.py` (launchd 4h), `scripts/daily_crypto_rebalance.py` (launchd daily), `scripts/run_validation.py` (6-test runner), `scripts/signal_tracker.py` (A4 execution drag).

### Running the Project
- **Both servers**: `./scripts/start.sh` (recommended). Backend on :8001, frontend on :5174. Port :8000 is FIREMaster.
- **Backend only**: `uv run uvicorn api.main:app --reload --port 8001`
- **Frontend only**: `cd dashboard && npm run dev`
- **Validation**: `uv run python3 scripts/run_validation.py --account N` — runs Tests 1-6. See `VALIDATION.md` for the strategy-discovery workflow.
- **Filter monitor**: Runs automatically via launchd every 4h. Manual: `uv run python3 scripts/filter_check.py` (or `--dry-run`). Install/uninstall commands in `AUTOMATION.md`.
- **Signal tracker**: `uv run python3 scripts/signal_tracker.py` — A4 signal-only vs live return decomposition. `--since YYYY-MM-DD` for recent window.

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript
- **Async endpoints**: All FastAPI `async def` endpoints MUST use `asyncio.to_thread()` for blocking calls (Alpaca API, yfinance downloads, parquet I/O, pandas computations). Calling blocking functions directly freezes the event loop and makes the entire server unresponsive to concurrent requests. This applies to route handlers and scheduled jobs alike.
- **Maintainability is a first-class constraint.** George works on this alone with AI partners and re-enters the codebase after gaps. A clever optimization that requires holding three files in your head is worse than a boring implementation a future session can grok cold. Optimize for: fewer surfaces to remember, fewer invariants to re-verify, fewer places a change has to land. Before adding a new file/abstraction/mirror, ask whether it makes the next person's job easier or harder. If a "mirrors X" docstring is needed, the two implementations should probably be one.

### Working with Claude — behavioral defaults

**READ THIS FIRST — the anti-defensive rule:** The rules below are operational guardrails for building code. They are NOT evaluation criteria for new research. When George brings a new idea, strategy, article, or research direction, the FIRST response must engage with what the idea is trying to do — not measure it against existing infrastructure, validation gates, or account slots. The pattern of "let me check if this fits our existing system" before understanding the thesis has been the #1 recurring failure mode in this project (documented 2026-05-13 after 3 separate instances in one session). New ideas get evaluated on their own terms first. Existing infrastructure adapts to good ideas; good ideas don't get demoted to fit existing infrastructure.

- **Preference ≠ requirement.** Offhand "I like X" is input, not a constraint. Give the engineering recommendation first; surface preference deviations as labeled trade-offs.

- **Stop and confirm before changes >50 lines or any new file/architecture decision.** State the smallest viable alternative + what you're proposing + why, and wait for a yes. *This applies to CODE changes, not to research discussions. Don't use this rule to gatekeep exploration.*

- **Diagnose before workaround.** When something looks broken, run the diagnostic that shows what the upstream actually thinks before proposing infrastructure to route around it. Surface "we could just wait" or "the broker handled it" as peer options, not footnotes. Don't duplicate authoritative external validation client-side on first occurrence.

- **Honesty over flattery in commits and docs.** When a decision is driven by preference rather than engineering merit, label it as such. Future-you re-reading a doc should see what was actually decided and why.

- **Simplicity over complexity.** When two designs both work, take the smaller one. Prefer one obvious code path over two clever ones; a single source of truth over parallel implementations whose equivalence has to be re-proven. Complexity has consistently been the failure mode here.

- **Test live↔backtest semantic parity, not just numeric parity.** When a live system reads "the same data" backtest used, ask: are the bars settled? Closed or still-forming partial? Timezone assumptions implicit? The C9 partial-bar contamination silently diverged live from backtest for ~14 days because "yfinance returned a row, therefore it's a closed bar" was an unstated assumption. First question for any live↔backtest gap: "is the strategy reading the same kind of data point in both modes?"

- **Match the evaluation framework to the strategy's objective function.** Not everything is a factor strategy competing for Calmar supremacy. When George brings yield research, bridge-income ideas, or life-design explorations, evaluate them by what they're trying to do (income floor, principal preservation, withdrawal coverage) — not by the Mode 1 CAGR/Calmar gates. The defensive pattern of measuring every new idea against the existing book's metrics is the single most recurring failure mode in this project. Engage with the thesis first, identify the right success criteria second, then evaluate.

- **Idea Farm mode for strategic stagnation.** When George signals defensive-cycle fatigue ("do nothing new" verdicts repeating, "breakthrough" in mocking quotes, austerity framing he rejects, "we need bold"), invoke the `/idea-farm` skill BEFORE running another optimization round. Skill at `~/.claude/skills/idea-farm/`. Default cadence: monthly minimum.

### Current Phase & Next Steps

**Mode 1 (Structural Alpha):** 3-account live book (A1+A2+A4) at 1/3 each; pre-Fly hardening mode.
- Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10, OOS CAGR 27.2%
- Account 2: 34 positions (Trend + Low-Vol) — live since 2026-03-10, OOS CAGR 11.0% MARGINAL
- Account 4: Crypto Momentum Rotation — daily at 00:05 UTC, SMA-125/top2 production, OOS CAGR 38.6%, Calmar 3.05 (8-coin live universe). First live entry 2026-04-22; A4 33%→40% upgrade clock counts from that date (cash-on-filter days don't count).
- Live-tracking clock reset to 2026-04-20 (the Mar 10 → Apr 17 window was compromised by stale-data bug).

**Validation status:** All three active accounts PASS the CAGR-first gates. Results in `data/validation_reports/`, state in `data/risk_state/validation_state.json`. A3 status="retired" — retired accounts are an unconditional block, no override can bypass. `execution/validation_gate.py` blocks FAIL/unvalidated; MARGINAL allowed for paper. Overrides for FAIL/unvalidated/expired only: `FIRE_VALIDATION_OVERRIDE=1` (global) or `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` (scoped). Both surface a WARNING log.

**Open bugs:** Tier 1 closed except C3 (S&P 500 survivorship, ~1-2pp on A1 CAGR — only matters pre-real-money). C10 closed 2026-05-06 by migrating live crypto signal computation to Alpaca's bars endpoint (broker-native, no third-party publishing delay) — see `HISTORY.md` C10/C11 for the authoritative narrative. Tiers 2+3 fully closed. Tier 4 R6/R7/R8/R10/R13/R14/R15 are reporting hygiene, non-blocking. See `HISTORY.md` for per-item detail.

**Mode 2 (Informational Alpha):** Phase A in progress.
- PEAD data pipeline + transcript scraper + scoring prompts + recommendation tracker built (`mode2/`).
- Data sources: Finnhub (EPS surprise, free), Insider Monkey (transcripts, free), yfinance (prices).
- Week 1 (2026-04-15): 6 companies analyzed, 1 long recommendation (C, conviction 4/5), 5 skips. C long at $131.69, stop $125, target $138, 40-day hold (paper).
- **Key learning**: Large-cap PEAD drift is 1-3% (not 5-8% as in academic literature which skews small-cap). Best PEAD opportunities will be mid-caps with less analyst coverage in weeks 2-4 of earnings season.

**Dashboard:** React + TradingView on :5174. Tabs: Live Portfolio (5-account switcher + equity charts + correlation), Rebalance (preview → execute), Ops (filter/validation/events), Backtests. Ticker mapping: yfinance hyphens → Alpaca dots via `to_alpaca_equity_symbol()`.

**Next steps:**
- **4.7-era audit pass** (done 2026-05-08). Cold-read of AUDIT_MONTH2.md against the current code came back clean: every closed claim that affects behavior matches code. Audit docs archived to `docs/archive/`; HISTORY.md is now the canonical digest. `DEPLOYMENT_PLAN.md`, `AUTOMATION.md`, `execution/rebalance.py`, `execution/alpaca_broker.py` are still on the watch list for residual narrative drift; spot-check as you touch them.
- **Mode 1**: stay alive in pre-Fly hardening mode; fix bugs as they surface; don't optimize. Open R-items (R6-R8, R10, R13-R15) are non-blocking cleanup; see `HISTORY.md`.
- **Open strategy research** (no active sprint): The April 2026 A5 hunt exhausted 12 vectors of *uncorrelated factor strategies* specifically — that search space has diminishing returns. But fundamentally different approaches (yield/carry, ML signals, non-price edges) are open vectors with active research docs. See `docs/research/` for current tracks. Shelved factor-strategy vectors: rate vol (`RATE_VOL_SCOPE.md`, MOVE at lows), commodity vol, narrative-aware crypto.
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season.
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`).
- Mode 2: Track C recommendation for 40 days (check price by 2026-05-25).

### Research Tracks (outside Mode 1/Mode 2 framework)

**Yield / Bridge-Income Strategy (active research, 2026-05):**
George is researching a yield-harvesting "Diversified Flywheel" strategy (STRC/NVDY/AMZY) as a potential Account 5 candidate, iterated with Gemini over multiple sessions. This serves a DIFFERENT objective than Mode 1 — it targets reliable monthly income that exceeds a sustainable withdrawal rate during the bridge years, with principal preservation. The strategy spec is at `docs/research/HighYield_Strategy_STRC_NVDY_AMZY.md`; deeper context (funding sources, SEPP 72(t) deployment, Gemini audit) is in FIREMaster (`STRATEGY_CAPSULE.md`, `BRIDGE_STRATEGY_REVIEW.md`).

**Key framing:** This is NOT competing with A1/A2/A4 on CAGR/Calmar. It's a carry/yield factor play targeting income floor + principal preservation. Evaluate by: total return with DRIP, yield sustainability, drawdown behavior in stress, withdrawal coverage ratio. The Mode 1 validation gates (OOS CAGR ≥ 15%, etc.) do not apply here.
