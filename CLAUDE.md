# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

### Key Documents
- `PLAN.md` — Full project plan with architecture, roadmap, risk framework, and essential reading
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
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 3 of 9 coins by 21-day momentum, BTC 200d MA trend filter + vol-scaling. **Daily rebalance** at 00:05 UTC via APScheduler.

Cross-account correlations: 0.56-0.66 equity pairs, 0.12-0.18 crypto-equity pairs
Combined 3-account (equity): **1.59 Sharpe, 16.8% return, -10.2% MaxDD**
Crypto standalone: **1.62 Sharpe, 33.2% CAGR, -23.5% MaxDD** (0.18 SPY correlation)

Multi-account credentials in `.env` (ALPACA_API_KEY, ALPACA_API_KEY_2, ALPACA_API_KEY_3, ALPACA_API_KEY_4). `AlpacaBroker(account=1|2|3|4)` selects credentials.

Rebalance schedule:
- **Daily at 00:05 UTC**: Account 4 (crypto) — automated via APScheduler
- Every Monday: Account 3 (reversal)
- First Monday of month: All 3 equity accounts

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
- **BTC 200-day MA trend filter**: Binary 100% cash when BTC < 200d MA (sat out all of 2022)
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4, +0.1-0.3 Sharpe improvement
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`

### Architecture
```
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
api/locks.py             — Per-account async rebalance locks (prevents concurrent execution)
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
dashboard/src/components/RebalancePanel.tsx — Preview/execute rebalance with order diff table
dashboard/src/components/RebalanceHistory.tsx — Rebalance event journal with expandable order details
dashboard/               — React + Vite + TradingView Charts
```

### Running the Project
- **Both servers**: `./scripts/start.sh` (recommended — starts backend + frontend, cleans up stale processes)
- **Backend only**: `uv run uvicorn api.main:app --reload` (from project root)
- **Frontend only**: `cd dashboard && npm run dev` → http://localhost:5173
- **Validation**: `uv run python3 -c "from backtesting.validation import full_validation; ..."`

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript

### Current Phase & Next Steps
- Completed: Phase 1-4 (core engine, strategies, dashboard, Alpaca execution), Phase 5 (multi-factor research + 3-account infra), Phase 6 (crypto momentum)
- **All 4 accounts live on paper**: $400k total deployed across 4 uncorrelated strategies
  - Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10
  - Account 2: 34 stocks (Trend + Low-Vol) — first trade 2026-03-10
  - Account 3: 52 stocks (Reversal Blend) — first trade 2026-03-10
  - Account 4: Crypto Momentum Rotation — daily automated rebalance at 00:05 UTC
- **Combined 3-account (equity): 1.59 Sharpe, 16.8% return, -10.2% MaxDD** (vs SPY 0.87 Sharpe, -33.7% MaxDD)
- **Account 4 (crypto): 1.62 Sharpe, 33.2% CAGR, -23.5% MaxDD** — 0.18 SPY correlation, excellent diversifier
- Dashboard: 5-tab account switcher (Combined / FIRE 0.1 / 0.2 / 0.3 / 0.4), live equity charts, correlation monitor (Combined view), Backtests with grouped strategy panel
- **Performance tracking**: Daily equity snapshots in parquet, Alpaca backfill on startup, live equity curves in dashboard
- **Correlation monitoring**: Rolling 21-day pairwise correlation (6 pairs), matrix + rolling chart, alert at 0.80 threshold, confidence badges
- **Automated trading**: APScheduler runs daily crypto rebalance at 00:05 UTC inside FastAPI lifespan
- **Circuit breaker monitoring**: RiskStatusPanel polls `/api/portfolio/risk` every 30s, shows green bar when healthy, red alert with reset buttons when halted
- **Regime filter status**: FilterStatusBanner shows SPY price vs 200d MA (accounts 1-3) and BTC price vs 200d MA (account 4), color-coded green/amber/red
- **Rebalance UI**: RebalancePanel with preview → confirm → execute flow, order diff table, SPY/BTC filter warnings, handles 409 (concurrent) and 403 (circuit breaker) errors
- **Rebalance history**: RebalanceHistory shows past rebalance events with expandable per-order details, source badges, filter badges
- **Execution safety**: Per-account async locks (409 on concurrent rebalance), circuit breaker persistence to disk, structured JSONL rebalance audit trail, retry logic on scheduled jobs
- Rebalance flow: `POST /api/orders/rebalance/preview?account=N&strategy_id=X` → review → `POST /api/orders/rebalance/execute?account=N&strategy_id=X`
- Next: Automated equity rebalance scheduler, reconciliation, walk-forward validation, track paper trading 3+ months before live money
