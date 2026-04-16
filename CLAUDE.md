# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

### Key Documents
- `PLAN.md` — Full project plan with architecture, roadmap, risk framework, and essential reading
- `PLAN_MODE2.md` — Two-mode architecture: Mode 1 (structural alpha, existing) + Mode 2 (informational alpha, PEAD + event-driven + macro regime). The strategic plan for compounding $50K over the bridge to 59½.
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `References/` — Original 2020 proposal and Ernie Chan books

### Project Decisions
- **Broker**: Alpaca (primary), QuantConnect (research only when needed)
- **Backtesting**: vectorbt
- **Frontend**: React + TypeScript + TradingView Lightweight Charts (v5)
- **Backend**: Python + FastAPI
- **Risk**: Fractional Kelly + 2% max loss + drawdown circuit breakers (-15% portfolio, -10% strategy)
- **Statistical validation**: Walk-forward analysis, Monte Carlo, regime testing required before any live money
- **No shorting**: Use reverse ETFs instead when needed (avoids margin/borrow complexity)

### Four-Account Architecture
Uncorrelated factor diversification across 4 Alpaca paper accounts ($100k each):
- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter — profits when trends persist. Monthly rebalance.
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling — crisis alpha + defensive. Monthly rebalance.
- **Account 3 (FIRE 0.3 — Reversal + Momentum)**: 60% Short-Term Reversal + 40% SM — anti-momentum hedge. **Weekly rebalance** (reversal signal decays after ~5 days).
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 2 of 9 coins by 21-day momentum, BTC 150d SMA trend filter + vol-scaling. **Daily rebalance** at 00:05 UTC via APScheduler. (Optimized from top-3/200d on 2026-04-15 via `mode2/crypto_autoresearch.py`: Sharpe 1.56→2.01, MaxDD -23.5%→-14.1%)

Cross-account correlations: 0.56-0.66 equity pairs, 0.12-0.18 crypto-equity pairs
Combined 3-account (equity): **1.59 Sharpe, 16.8% return, -10.2% MaxDD**
Crypto standalone: **1.62 Sharpe, 33.2% CAGR, -23.5% MaxDD** (0.18 SPY correlation)

Multi-account credentials in `.env` (ALPACA_API_KEY, ALPACA_API_KEY_2, ALPACA_API_KEY_3, ALPACA_API_KEY_4). `AlpacaBroker(account=1|2|3|4)` selects credentials.

Rebalance schedule (two layers — exposure management + signal rotation):
- **Daily at 4:30 PM ET**: Filter monitor checks all accounts — auto-rebalances if SPY/BTC filter flips (launchd, no server needed)
- **Daily at 00:05 UTC**: Account 4 crypto signal rotation — automated via APScheduler (requires server)
- **Every Monday**: Account 3 reversal signal rotation (manual)
- **First Monday of month**: Accounts 1 & 2 momentum/trend signal rotation (manual)

### Strategies (8 momentum + 3 factor + 1 crypto + portfolio combos)
| Strategy | Sharpe | Return | MaxDD | Notes |
|---|---|---|---|---|
| **Combined 3-Account Portfolio** | **1.59** | **16.8%** | **-10.2%** | **All 3 equity accounts blended** |
| **Crypto Momentum (filtered)** | **1.62** | **33.2%** | **-23.5%** | **Acct 4 — daily, 0.18 SPY corr** |
| **Reversal + Momentum Blend** | **1.54** | **15.2%** | **-9.4%** | **Acct 3 blend** |
| **Stock Momentum + SPY Filter** | **1.38** | **17.6%** | **-12.2%** | **Acct 1** |
| **Trend + Low-Vol (vol-scaled)** | **1.36** | **17.7%** | **-14.0%** | **Acct 2 blend** |
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
- **Stock Universe**: 451 S&P 500 stocks (cached parquet, survivorship bias noted)
- **Crypto Universe**: 9 coins (BTC, ETH, SOL, BNB, ADA, AVAX, LINK, DOT, XRP)
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007)
- **BTC 150-day SMA trend filter**: Binary 100% cash when BTC < 150d SMA (sat out all of 2022). Optimized from 200d — crypto cycles faster than equities.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4, +0.1-0.3 Sharpe improvement
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`

### Risk Controls — Operational Behavior

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
backtesting/validation.py — Walk-forward, Monte Carlo, regime tests
execution/risk_manager.py — Fractional Kelly + 2% rule + circuit breakers
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

**Mode 1 (Structural Alpha):** Completed Phases 1-6. All 4 accounts live on Alpaca paper ($400k total), all rebalanced to full exposure 2026-04-14.
  - Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10
  - Account 2: 34 stocks (Trend + Low-Vol) — first trade 2026-03-10
  - Account 3: 52 stocks (Reversal Blend) — first trade 2026-03-10, weekly rebalance
  - Account 4: Crypto Momentum Rotation — daily automated rebalance at 00:05 UTC
  - Combined 3-account (equity): 1.59 Sharpe, 16.8% return, -10.2% MaxDD
  - Account 4 (crypto): 1.62 Sharpe, 33.2% CAGR, -23.5% MaxDD, 0.18 SPY correlation

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
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`)
- Mode 2: Track C recommendation for 40 days (check price by 2026-05-25)
- Mode 1: Investigate Account 1 & 3 correlation (0.87 live vs 0.56 backtest)
- Mode 1: Rebalance markers on equity charts, reconciliation, walk-forward validation
