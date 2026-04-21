# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

### Key Documents
- **`AUDIT_MONTH2.md`** — open bugs and fix plan from the 2026-04-20 adversarial review. Has caveats on every headline number; read this before trusting CAGR/Calmar figures below.
- `DECISIONS_RESOLVED.md` — record of the April 2026 portfolio-architecture decisions (A3 retired, A4 at 33% with 40% upgrade ladder). Formerly DECISIONS_PENDING.md; renamed after both decisions executed.
- `PLAN.md` — Full project plan with architecture, roadmap, risk framework, and essential reading
- `PLAN_MODE2.md` — Two-mode architecture: Mode 1 (structural alpha, existing) + Mode 2 (informational alpha, PEAD + event-driven + macro regime). The strategic plan for compounding $50K over the bridge to 59½.
- `VALIDATION_PLAN.md` — CAGR-first evaluation framework (v2, 2026-04-18)
- `RATE_VOL_SCOPE.md` — Account 5 candidate scoping (MOVE-conditional TLT reversal)
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `DEPLOYMENT_PLAN.md` — 24/7 cloud deployment research for the live trading module (Fly.io primary, 5-phase migration plan). Paper-first; pre-real-money hardening in Phase 5.
- `References/` — Original 2020 proposal and Ernie Chan books

### Project Decisions
- **Broker**: Alpaca (primary), QuantConnect (research only when needed)
- **Backtesting**: vectorbt
- **Frontend**: React + TypeScript + TradingView Lightweight Charts (v5)
- **Backend**: Python + FastAPI
- **Risk**: Equal-weight top-N position sizing (at strategy layer) + SPY/BTC trend filters + drawdown circuit breakers (-15% portfolio, -10% strategy — design under review, see AUDIT_MONTH2 C5). Historical "Fractional Kelly + 2% rule + 20% position cap" were wired in naming only: Kelly/2% rule were dead code, and the 20% cap silently conflicted with A4's top-2 crypto design — all three removed 2026-04-21 (AUDIT_MONTH2 C7 + R12 cleanup).
- **Evaluation framework (v2, 2026-04-18)**: CAGR-first scorecard, not Sharpe. Primary gates: OOS CAGR ≥ 15%, OOS MaxDD ≥ -40%, OOS Calmar ≥ 1.0, OOS/IS CAGR ratio ≥ 70%. Full scorecard (MAR, Sterling, Burke, Pain, Ulcer, UPI, Sortino, Omega, Gain-to-Pain, time underwater, max recovery days) reported for context. Sharpe shown informational only — not gated. See `VALIDATION_PLAN.md`.
- **Statistical validation**: Six-test scorecard (all required before real money; quarterly re-validation enforced via gate):
  - **Test 1** — OOS holdout (train 2010-2022, test 2023-today).
  - **Test 2** — Rolling OOS with fixed parameters. (Previously mislabeled `walk_forward_refit`; corrected 2026-04-20 — no refit happens here.)
  - **Test 3** — Parameter stability across half-A/half-B splits (crypto only; other accounts skip).
  - **Test 4** — Block bootstrap CAGR p5/p50/p95 (gated: p5 ≥ 0%).
  - **Test 5** — Portfolio fit (satellite marginal contribution; not gated).
  - **Test 6** — Walk-forward REFIT vs defaults (added 2026-04-20, non-gating). Per-window grid search on adapter-defined `refit_param_grid`; PASS if defaults within 10% of refit or better, REVIEW only if refit stably beats defaults by >20%. A1 + A2 currently PASS — literature defaults are not demonstrably suboptimal and a true parameter search cannot beat them. See `VALIDATION_PLAN.md`. Strategy-discovery pattern: new candidates get dropped in as `refit_strategy_factory` + grid on an adapter or run via `scripts/walk_forward_refit_*.py`.
- **No shorting**: Use reverse ETFs instead when needed (avoids margin/borrow complexity)

### Three-Account Live Architecture (post-2026-04-20 A3 retirement)
Uncorrelated factor diversification across 3 Alpaca paper accounts, 1/3 each of total book. A3 is retired but its Alpaca account slot is preserved for future strategy assignment.

- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter — profits when trends persist. Monthly rebalance.
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling — crisis alpha + defensive. Monthly rebalance.
- **Account 3 (FIRE 0.3 — RETIRED 2026-04-20)**: 60% STR + 40% SM. Retired because 40% of its book was literally A1 (structural overlap → A1↔A3 OOS correlation 0.876). Liquidated $99,826.89 all-cash. Slot preserved for future strategy. See `DECISIONS_RESOLVED.md`.
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 2 of 9 coins by 21-day momentum, BTC 125d SMA trend filter + vol-scaling. **Daily rebalance** at 00:05 UTC via APScheduler. Parameters picked via `scripts/crypto_robust_opt.py` by maximizing `min(Calmar_half_A, Calmar_half_B)` across 144 configs — regime-robust objective. SMA-125/top2 remains the robust winner post-C2 fix (half A 2.89 / half B 2.94 with strict 125d MA warmup; half B was 3.10 under the old min_periods=1 convention). A4 weight in combined book is **33%** (1/3), with a pre-committed **40% upgrade** once ≥6 months of signal-trading days (not cash-on-filter) confirm live Calmar ≥ 2.0 and A4↔equity correlation ≤ 0.25.

Cross-account correlations (OOS backtest 2023-01-03 → 2026-03-10):
- A1↔A2: **0.38** (backtest) — genuinely diversified
- A1↔A4: 0.10-0.19 — genuinely diversified
- A2↔A4: 0.10-0.19 — genuinely diversified
- (A3 retired — historical correlations preserved in DECISIONS_RESOLVED.md)

**Live correlation panel** (dashboard) shows A1/A2/A4 pairs only. Live A4 pairs currently show "—" because A4 has been all-cash since launch (BTC below 125d MA filter → zero-variance returns make Pearson correlation undefined).

Combined OOS (2023-01-03 → 2026-04-17; equity trading calendar, A4 compounded Fri→Mon, ppy=252):

- Equity core (A1+A2 at 50/50): **CAGR +22.3%, MaxDD -7.7%, Calmar 2.88**
- 3-account live book (A1+A2+A4 at 1/3 each): **CAGR +30.3%, MaxDD -7.0%, Calmar 4.31**

*C1 fix applied 2026-04-20: the old union-calendar+fillna(0)+ppy=365 convention gave essentially the same numbers (28.09%/-7.56%/3.71) — the audit's "biased HIGH" magnitude claim did not materialize. Code migrated anyway for cleaner semantics.*

Account 4 standalone (fresh data through 2026-04-20, post C1+C2 fixes):
**CAGR +45.2%, MaxDD -11.4%, Calmar 3.98** (Sharpe 1.90 informational). Block-bootstrap CAGR p5/p50/p95: **+24.8% / +45.8% / +76.1%**. Prior report of 47.1%/4.15 was on a slightly shorter window.

Multi-account credentials in `.env` (ALPACA_API_KEY, ALPACA_API_KEY_2, ALPACA_API_KEY_3, ALPACA_API_KEY_4). `AlpacaBroker(account=1|2|3|4)` selects credentials. Account 3 is retired; orders endpoint `_require_active()` guard + validation_gate both block rebalance attempts against it.

Rebalance schedule (two layers — exposure management + signal rotation):
- **Daily at 4:30 PM ET**: Filter monitor checks all active accounts — auto-rebalances if SPY/BTC filter flips (launchd, no server needed). A3 excluded from `ACCOUNT_FILTERS`.
- **Daily at 00:05 UTC**: Account 4 crypto signal rotation — automated via APScheduler (requires server)
- **First Monday of month**: Accounts 1 & 2 momentum/trend signal rotation (manual)
- A3 weekly cadence retired with A3 itself.

**Concurrency (AUDIT_MONTH2.md S1, fixed 2026-04-20):** all three rebalance entry points (API `/rebalance/execute`, APScheduler A4 job, `filter_check.py`) now serialize via `dual_rebalance_lock` (async + file lock) or, for the sync cron path, the same `file_rebalance_lock` they observe. Contention raises `RebalanceLockedError` → 409 from the API, `status="locked"` from the cron. Verified end-to-end — real-money-graduation blocker lifted.

### Strategies — OOS scorecard (live accounts)

**Fresh-data OOS per the CAGR-first framework (test window ends 2026-04-20, post-cache-refresh). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION_PLAN.md`.**

**Load-bearing caveats before trusting these numbers (see AUDIT_MONTH2.md):**
- **C1 (fixed 2026-04-20):** `run_combined_portfolio` migrated from union calendar + fillna(0) + ppy=365 to equity trading calendar with A4 compounded Fri→Mon + ppy=252. Empirical delta on headline numbers was ≤ 0.3pp CAGR / 0.05 Calmar — audit's "biased HIGH" claim did not materialize.
- **C2 (fixed 2026-04-20):** `min_periods=1` on BTC MA warmup changed to strict `min_periods=period` in `strategies/crypto_momentum.py`, `mode2/crypto_autoresearch.py`, and `api/routes/portfolio.py`. Robust-opt + validation harnesses now compute MA on full BTC history before reindexing to half-slices, so pre-slice warmup is used. SMA-125/top2 remains the min-Calmar winner (half A 2.89 unchanged, half B 3.10 → 2.94).
- **C3:** A1 standalone CAGR is ~1-2pp overstated by S&P 500 survivorship bias (known, documented below).
- **C4 (fixed 2026-04-21, option B with `scalar_cap=1.0`):** Live vol-scaling now applied in `compute_rebalance` via `execution/vol_scaling.compute_live_vol_scalar` for any config with `vol_scaling: True` (A2 + A4). Backtest `scalar_cap` also reduced 1.5 → 1.0 in both `apply_vol_scaling` default and per-config params — sim and live are now apples-to-apples at the 1.0 upside cap (Alpaca paper is spot-only / no margin, so cap=1.5 was unreachable in live anyway). Live/backtest scalar parity verified within 1e-6 on A2's 10-day snapshot history. Empirical impact on headline numbers below.

| Strategy | Status | CAGR | MaxDD | Calmar | MAR | UPI | Sortino | *Sharpe (info)* |
|---|---|---|---|---|---|---|---|---|
| **Crypto Momentum (Acct 4)** | PASS | **+43.8%** | **-11.4%** | **3.86** | 3.86 | — | — | — |
| **Stock Momentum + SPY (Acct 1)** ⚠ C3 | PASS | **+27.3%** | **-9.8%** | **2.77** | 2.77 | — | 2.11 | *2.05* |
| **Trend + Low-Vol (Acct 2)** | MARGINAL | **+11.2%** | **-7.3%** | **1.54** | 1.54 | — | — | — |
| *Reversal + Momentum (Acct 3)* — retired | RETIRED | *14.5%* | *-7.2%* | *2.03* | — | — | — | — |

A1 + A4 PASS the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates. **A2 dropped to MARGINAL** after the C4 fix (cap 1.5 → 1.0): backtest had been leveraging the low-vol leg up to 1.5× in calm regimes that live could never realize. Post-fix CAGR 11.2% is below the 15% gate, but MARGINAL is allowed for paper per `execution/validation_gate.py` — the actual live book was never producing 16.9% anyway because `apply_vol_scaling` was not wired into the live rebalance path. A4's drop (45.2% → 43.8% CAGR, 3.98 → 3.86 Calmar) is smaller because crypto realized vol is usually at or above the 15% target — the cap-1.5 capability rarely bound.

**Combined headline numbers (A1+A2+A4 @ 1/3, Equity core @ 50/50) are stale pending a re-run of `run_combined_portfolio` against post-C4 configs.** The ladder-to-40% decision was made on relative-Calmar across weight configurations and the direction is not affected by the C4 fix (same bias across all three A4 weight scenarios), but the absolute Calmar/CAGR numbers need to be re-issued before citing them for real-money sizing.

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
- **Stock Universe**: 501 S&P 500 stocks (cached parquet, survivorship bias noted). Coverage gate is **trailing 500 trading days ≥80% non-NaN** — was previously "≥80% of all days since 2010," which locked out every post-2013 IPO / recent S&P addition. The new gate lets recent adds like VRT and LITE enter the live rotation once they have ~2y of history, without corrupting backtests (pre-IPO NaN rows propagate to NaN ranks → excluded from selection for periods before the ticker existed). Fixed 2026-04-20.
- **Crypto Universe**: 9 coins (BTC, ETH, SOL, BNB, ADA, AVAX, LINK, DOT, XRP)
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007)
- **BTC 125-day SMA trend filter**: Binary 100% cash when BTC < 125d SMA (sat out all of 2022). Robust-opt picked 125d from 200d/150d/125d/100d grid on 2026-04-18.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4, +0.1-0.3 Sharpe improvement
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`

### Risk Controls — Operational Behavior

**Time convention — ET is the system reference timezone.** All scheduled times in FIRE are anchored to America/New_York (ET, DST-aware). The equity market runs on ET, and the user is a digital nomad whose laptop local time shifts constantly — laptop-local timezones must never be load-bearing. Same discipline applies to both local (launchd) and cloud (Fly cron) schedulers: `TZ=America/New_York` or `CRON_TZ=America/New_York`, not local time. Enforced at the code layer by `data/trading_dates.py` helpers (`today_et`, `utc_ts_to_et_date`) — use these, don't call `date.today()` or `datetime.now()` directly. The A4 crypto APScheduler job is the only exception and runs at 00:05 UTC (crypto markets are 24/7, so UTC-anchoring is the honest convention there).

**When are filters and circuit breakers checked?**
Risk controls are checked at two levels:

1. **Filter monitor (daily, automated)**: `scripts/filter_check.py` runs via macOS launchd at **4:30 PM ET daily** — even when the server is off. Computes SPY and BTC filter scalars, compares to last-known state in `data/risk_state/filter_state.json`. If a filter flips, **auto-executes rebalances** for affected accounts with full safety rails (circuit breakers, price staleness, file locks). Sends macOS notification. Logs to `data/filter_check.log` with `source="filter_monitor"` in the rebalance journal.

2. **Scheduled rebalance (signal rotation)**: Rotates *which* stocks/assets to hold at the strategy's native cadence:
   - **Account 4** (daily): APScheduler at 00:05 UTC (crypto signal + BTC filter)
   - **Account 3** (weekly): Manual trigger every Monday
   - **Accounts 1 & 2** (monthly): Manual trigger first Monday of month

**Key design: exposure management is decoupled from signal rotation.** The filter monitor handles *how much* to hold (reacts same-day to filter changes). The scheduled rebalance handles *what* to hold (monthly/weekly signal rotation). Backtesting showed this split is critical: daily filter reaction = Sharpe 1.27, monthly lag = Sharpe 0.79 (worse than no filter).

The dashboard's RiskStatusPanel and FilterStatusBanner show current status. FilterStatusBanner also shows the filter monitor's last check time and any recent auto-rebalances.

**What happens when a circuit breaker trips?**
- The system **freezes positions** — it does not liquidate. Hold what you've got, don't dig deeper.
- `POST /api/orders/rebalance/execute` returns **403** and refuses to trade on that account/strategy.
- The dashboard shows a red alert banner with the breaker details.
- Breaker state **persists to disk** (`data/risk_state/circuit_breaker_acct{N}.json`), so a server restart doesn't silently clear it.

**How to resume after a halt:**
- Manual reset only — dashboard reset button or `POST /api/portfolio/risk/reset?account=N`.
- Reset sets the equity peak to the current value and unhalts.
- This is intentional: forces you to review before resuming, not blindly restart.

**Why hold instead of sell?**
A -15% drawdown means something unusual is happening. Rebalancing into more risk is dangerous, but panic-selling at the bottom is also bad. Freezing forces a human decision.

### Architecture
```
# Mode 1: Factor Trading System
data/pipeline.py          — yfinance ETF data download & caching
data/sp500.py             — S&P 500 stock universe + VIX data
data/crypto.py            — Crypto data pipeline (yfinance + symbol mapping)
data/snapshots.py         — Daily equity snapshots (parquet) + Alpaca backfill
data/trading_dates.py     — ET trading-date helpers (today_et, utc_ts_to_et_date) — TZ-stable
data/correlation.py       — Inter-account correlation monitoring (rolling 21-day)
strategies/base.py        — Abstract strategy interface
strategies/trend_following.py — Time-Series & Multi-Timeframe Momentum
strategies/momentum.py    — Cross-Sectional & Dual Momentum (ETF-based)
strategies/stock_momentum.py — Individual stock momentum + VIX filter
strategies/multi_asset_trend.py — Multi-asset trend following (SPY/TLT/GLD/DBC/EFA)
strategies/low_volatility.py — Low-vol anomaly + momentum quality filter
strategies/mean_reversion.py — Short-term reversal (buy weekly losers)
strategies/crypto_momentum.py — Crypto momentum rotation (21-day, top 3, BTC filter)
strategies/portfolio.py   — Portfolio combiner + SPY/BTC filter + vol-scaling + combined portfolios
backtesting/metrics.py    — Sharpe, drawdown, Kelly, profit factor
backtesting/validation.py — Rolling-OOS + Monte Carlo + regime tests; + walk_forward_refit_analysis (true per-window param refit, added 2026-04-20)
backtesting/bootstrap.py  — Block bootstrap for confidence intervals (VALIDATION_PLAN Test 4)
backtesting/account_adapters.py — Per-account (returns, prices, strategy_fn) bundles for the validation runner
execution/risk_manager.py — Circuit breakers (portfolio + strategy level). Kelly/2% rule deleted 2026-04-21 per C7+R12 cleanup.
execution/vol_scaling.py  — Live vol-scaling scalar (AUDIT_MONTH2 C4 fix, 2026-04-21). Mirrors backtest `apply_vol_scaling` math on snapshot equity.
execution/validation_gate.py — Rebalance gate; blocks accounts without a passing validation record
execution/alpaca_broker.py — Multi-account Alpaca client (4 paper accounts)
execution/rebalance.py   — Signal-to-order pipeline (target weights → trade list)
execution/rebalance_log.py — Structured JSONL rebalance audit trail
api/main.py              — FastAPI backend (lifespan + APScheduler for daily crypto rebalance)
api/locks.py             — Per-account locks: async (in-process) + file-based (cross-process via fcntl)
api/routes/portfolio.py  — Account summary, positions, equity history, correlation, risk status, filter status
api/routes/orders.py     — Rebalance preview/execute, order history, rebalance journal (?account=1|2|3|4)
api/routes/backtests.py  — Backtest runner (individual + combined + crypto)
api/routes/strategies.py — Strategy list with live metrics
dashboard/src/strategyMetadata.ts — Strategy categories, descriptions, sort order
dashboard/src/components/Tooltip.tsx — Reusable hover tooltip (dark theme)
dashboard/src/components/Toast.tsx — Global toast notification system (error/warning/info)
dashboard/src/components/EquityHistoryChart.tsx — Live equity curves (TradingView, per-account + combined)
dashboard/src/components/CorrelationPanel.tsx — Correlation matrix + rolling chart + alerts (Combined view)
dashboard/src/components/StrategyPanel.tsx — Grouped strategy list (Live/Portfolio/Building Blocks)
dashboard/src/components/RiskStatusPanel.tsx — Circuit breaker status + reset (polls every 30s)
dashboard/src/components/FilterStatusBanner.tsx — SPY/BTC trend filter status with price vs 200d MA
dashboard/src/components/RebalancePanel.tsx — Preview/execute rebalance with action-classified order table (new/increase/decrease/exit)
dashboard/src/components/RebalanceHistory.tsx — Rebalance event journal with expandable order details
dashboard/               — React + Vite + TradingView Charts
scripts/start.sh         — Start backend + frontend (recommended)
scripts/filter_check.py  — Daily filter monitor — auto-rebalances on SPY/BTC filter change
scripts/run_validation.py — VALIDATION_PLAN Tests 1-5 runner; updates data/risk_state/validation_state.json
scripts/crypto_robust_opt.py — Crypto parameter search via min(Calmar_A, Calmar_B); produced SMA-125/top2 production config 2026-04-18
scripts/walk_forward_refit_a1.py — True walk-forward REFIT for A1 Stock Momentum (per-window grid search + OOS eval)
scripts/walk_forward_refit_a2.py — Same for A2 Low-Volatility leg
scripts/com.fire.filter-check.plist — macOS launchd plist (4:30 PM ET daily)

# Mode 2: PEAD / Informational Alpha
mode2/earnings.py         — Finnhub EPS data + Insider Monkey transcript scraper + SEC EDGAR
mode2/pead.py             — PEAD scoring prompt templates (structured JSON + quick analysis)
mode2/tracker.py          — Recommendation JSONL tracker with outcome logging
mode2/run_analysis.py     — CLI runner: fetch, summary, analyze, status commands
data/mode2/transcripts/   — Cached transcript JSON files ({SYMBOL}_Q{N}_{YEAR}.json)
data/mode2/recommendations.jsonl — Recommendation log with entry/exit/P&L tracking
data/mode2/reports/       — Weekly markdown research reports
References/mode2-data-sources-research.md — Full data source evaluation (9 sources tested)
```

### Mode 2 Usage
- **Fetch earnings + transcripts**: `uv run python3 -m mode2.run_analysis fetch --symbols JPM,GS,C --quarter 1 --year 2026`
- **Show summary**: `uv run python3 -m mode2.run_analysis summary --quarter 1 --year 2026`
- **Generate analysis prompt**: `uv run python3 -m mode2.run_analysis analyze --symbol JPM`
- **Tracker status**: `uv run python3 -m mode2.run_analysis status`
- **Data sources**: Finnhub (free, EPS surprise + news), Insider Monkey (free, transcript scraping), yfinance (prices). See `References/mode2-data-sources-research.md`.
- **API keys**: `FINNHUB_API_KEY` and `ALPHA_VANTAGE_API_KEY` in `.env`
- **Transcript URL discovery**: Search `site:insidermonkey.com "{COMPANY}" "Q1 2026 earnings call transcript"`, add URL to `TRANSCRIPT_URLS` dict in `run_analysis.py`
- **PEAD drift expectations by market cap**: Large-cap 1-3%, mid-cap 3-5%, small-cap 5-8%. Don't set small-cap targets on mega-cap banks.

### Running the Project
- **Both servers**: `./scripts/start.sh` (recommended — starts backend + frontend, cleans up stale processes)
- **Backend only**: `uv run uvicorn api.main:app --reload` (from project root)
- **Frontend only**: `cd dashboard && npm run dev` → http://localhost:5173
- **Validation**: `uv run python3 scripts/run_validation.py --account N` — runs Tests 1-6 (OOS holdout, rolling OOS, parameter stability for crypto, block bootstrap, portfolio fit, walk-forward REFIT). Writes a markdown report + updates `data/risk_state/validation_state.json`. Rebalances on accounts without a `status="pass"` record (and unexpired) return 403. Quarterly re-validation enforced via `expires`. See `VALIDATION_PLAN.md`.
  - Test 6 runs if the adapter defines a `refit_param_grid`; adds ~15-60s per account depending on grid size.
  - Standalone refit explorers: `scripts/walk_forward_refit_a1.py` (StockMomentum) and `walk_forward_refit_a2.py` (LowVolatility leg). Support `--grid small|medium|large`.
  - **Strategy-discovery workflow** — how to evaluate a new candidate strategy instead of copying paper defaults: see `VALIDATION_PLAN.md` → "Test 6 → Recipe for a new candidate strategy" (5-step process: write class → pick grid → run standalone refit → decide → wire into adapter). This replaces the old practice of lifting 15-year-old academic parameters wholesale.
- **Filter monitor**: Runs automatically via launchd at 4:30 PM ET daily (no server needed)
  - Manual run: `uv run python3 scripts/filter_check.py` (or `--dry-run` to check without trading)
  - Check status: `launchctl list | grep fire`
  - View logs: `cat data/filter_check.log` or `cat data/risk_state/filter_state.json`
  - Install: `cp scripts/com.fire.filter-check.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.fire.filter-check.plist`
  - Uninstall: `launchctl unload ~/Library/LaunchAgents/com.fire.filter-check.plist`
- **Validation**: `uv run python3 -c "from backtesting.validation import full_validation; ..."`

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript
- **Async endpoints**: All FastAPI `async def` endpoints MUST use `asyncio.to_thread()` for blocking calls (Alpaca API, yfinance downloads, parquet I/O, pandas computations). Calling blocking functions directly freezes the event loop and makes the entire server unresponsive to concurrent requests. This applies to route handlers and scheduled jobs alike.

### Current Phase & Next Steps

**Mode 1 (Structural Alpha):** Post-month-2 audit, 3-account live book (A1+A2+A4) at 1/3 each, A3 retired.
  - Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10, OOS CAGR 27.3% (was 20.9% before 2026-04-20 universe-filter fix)
  - Account 2: 34 positions (Trend + Low-Vol) — live since 2026-03-10, OOS CAGR 16.9%
  - Account 3: RETIRED 2026-04-20. Slot preserved. See `DECISIONS_RESOLVED.md`.
  - Account 4: Crypto Momentum Rotation — daily at 00:05 UTC, SMA-125/top2 robust-opt production, OOS CAGR 45.2%, Calmar 3.98. Currently 100% cash (BTC below 125d MA since launch).
  - Live-tracking clock reset to **2026-04-20** — Mar 10 → Apr 17 window was compromised by stale-data bug. A4 33%→40% upgrade clock counts from here (and only counts signal-trading days, not cash-on-filter days).

**Validation status (2026-04-20, fresh-data refresh, CAGR-first framework):** All three active accounts PASS. Results in `data/validation_reports/`, state in `data/risk_state/validation_state.json`. A3 status="retired" (gate blocks retired automatically). `execution/validation_gate.py` blocks FAIL/unvalidated/retired; MARGINAL allowed for paper. Override: `FIRE_VALIDATION_OVERRIDE=1` (global — known issue, see AUDIT_MONTH2.md R2).

**Known open bugs / fix plan** — see `AUDIT_MONTH2.md` for the ranked list. **Tier 1: C1 + C2 + C4 + C7 fixed**, C3 remains as acknowledged survivorship caveat, **C5 (circuit-breaker design) and C6 (fees/slippage in backtest) still open**. C4 fix (2026-04-21, option B): live vol-scaling via `execution/vol_scaling.compute_live_vol_scalar`, `scalar_cap=1.0` in both live and backtest for sim/live parity; A2 dropped PASS → MARGINAL (still allowed for paper), A4 remains PASS. **Tier 2 S1-S4 all fixed 2026-04-20** — `dual_rebalance_lock`, `write_parquet_atomic`, `file_snapshot_lock`, `download_with_retry` live in `api/locks.py` and `data/pipeline.py`; all live-path rebalance and yfinance calls go through them. **Tier 3 D1-D4 all fixed 2026-04-20** — `data/trading_dates.py` (TZ-stable ET helpers) used by snapshot backfill + `_patch_today`; SP500 ticker list on 7-day TTL with stale-cache fallback (refresh pulled 451→503 tickers, confirming 52 silently-dropped delistings); SPY fetch failures now log + surface as nullable `spy_return_pct`/`alpha_pct` rendered as "—" on the dashboard. **Tier 4 R11 fixed 2026-04-21** — `check_price_staleness` now flags unfetchable symbols as drifted with `reason="unfetchable"` instead of silently skipping; unit-tested. Tier 4 R2-R9 remain open — none block paper or real-money operation.

**Sharpe is explicitly deemphasized.** The prior framework used OOS Sharpe ≥ 1.0 as the gate, which is the wrong objective function for a 3-5 year wealth compounder (Sharpe penalizes upside vol and normalizes absolute return magnitude). Sharpe is still shown on reports as informational context but is not gated on. Primary gates are CAGR + MaxDD + Calmar. See `VALIDATION_PLAN.md` for rationale.

**Mode 2 (Informational Alpha):** Phase A in progress — research infrastructure built, first weekly analysis running.
  - **Built 2026-04-15**: PEAD data pipeline (`mode2/`), transcript scraper, scoring prompts, recommendation tracker
  - **Data sources**: Finnhub (EPS surprise, free), Insider Monkey (transcripts, free scraping), yfinance (prices)
  - **Week 1 analysis (2026-04-15)**: 6 companies analyzed (JPM, GS, C, WFC, BLK, JNJ), 1 long recommendation (C, conviction 4/5), 5 skips. BAC (+8.6%), MS (+10.9%), PNC (+5.5%) reported same day — transcripts pending.
  - **Paper tracking**: C long at $131.69, stop $125, target $138, 40-day hold. All paper — no real money until Month 2 (June) per PLAN_MODE2.md.
  - **Key learning**: Large-cap PEAD drift is 1-3% (not 5-8% as in academic literature which skews small-cap). Best PEAD opportunities will be mid-caps with less analyst coverage in weeks 2-4 of earnings season.

**Dashboard infrastructure** (unchanged from Mode 1 build):
- 5-tab account switcher, live equity charts, correlation monitor, Backtests with grouped strategy panel
- All components `React.memo` optimized, no loading gates on background polls
- Data caching: ETF/SPY/S&P500/VIX/crypto parquets with staleness checks
- Daily equity snapshots, Alpaca backfill, circuit breaker monitoring, filter status
- Rebalance UI: preview → confirm → execute, action-classified orders, per-account locks
- Filter monitor: `scripts/filter_check.py` via launchd at 4:30 PM ET daily
- Ticker mapping: yfinance hyphens → Alpaca dots via `to_alpaca_equity_symbol()`
- Snapshot data quality: Alpaca backfill writes NaN for cash/positions — don't treat as zero

**Next steps:**
- **Mode 1 priority:** Tier 1 (C1, C2, C4, C7) + Tier 2 (S1-S4) + Tier 3 (D1-D4) + Tier 4 (R11, R12) all fixed. **C4 fix 2026-04-21 cleared the path for A1 + A2 May 4 rebalance** — live vol-scaling now wired in `compute_rebalance` with `scalar_cap=1.0`; backtest aligned. A2 dropped PASS → MARGINAL (CAGR 16.9% → 11.2%) but allowed for paper. A4 stayed PASS (45.2% → 43.8%). Live/backtest scalar parity verified within 1e-6. **C5 (drawdown-halt design decision + backtest sim)** and **C6 (fee/slippage in backtest)** remain open — neither blocks paper rebalancing. Tier 4 R2-R9 reporting hygiene remain as lower-priority cleanup.
- **Find/build a new Account 4-class strategy** — user's directive 2026-04-18: current crypto account is acceptable baseline but not extraordinary. Target: OOS CAGR and Calmar that meaningfully exceed the existing single-account results. Funding-rate carry on perps was explored and shelved (infra + exchange risk). Open research vectors: rate vol (see `RATE_VOL_SCOPE.md`), commodity vol, narrative-aware crypto.
- Mode 1: Add dashboard banner showing validation status per account (reads `data/risk_state/validation_state.json`).
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season.
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`).
- Mode 2: Track C recommendation for 40 days (check price by 2026-05-25).
