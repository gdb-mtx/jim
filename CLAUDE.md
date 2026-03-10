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

### Strategies (8 total: 5 individual + 3 portfolio combos)
| Strategy | Sharpe | Return | MaxDD | Notes |
|---|---|---|---|---|
| **Stock Momentum + SPY Filter** | **1.38** | **17.6%** | **-12.2%** | **Best performer** |
| Blended Portfolio + SPY Filter | 1.37 | 14.2% | -9.3% | Lowest drawdown |
| Blended Portfolio | 1.13 | 12.6% | -15.8% | 60% SM + 20% CS + 20% DM |
| Stock Momentum (S&P 500) | 1.16 | 15.9% | -18.6% | Best single strategy |
| Cross-Sectional Momentum | 0.85 | 7.0% | -10.8% | Validated |
| Time-Series Momentum | 0.85 | 6.2% | -15.2% | Validated |
| Dual Momentum (Antonacci) | 0.83 | 7.6% | -19.9% | Validated |
| Multi-Timeframe Momentum | 0.67 | 4.1% | -11.0% | Regime fail |
| *SPY Buy & Hold (benchmark)* | *0.87* | *14.5%* | *-33.7%* | — |

- **Best performer**: Stock Momentum + SPY Filter — 17.6% return, 1.38 Sharpe, -12.2% MaxDD (beats SPY on every metric)
- **ETF Universe**: 18 assets (8 broad ETFs + 9 sector ETFs + SHY cash proxy)
- **Stock Universe**: 451 S&P 500 stocks (cached parquet, survivorship bias noted)
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007). Single most impactful improvement.
- **Portfolio combination**: 60% Stock Momentum + 20% Cross-Sectional + 20% Dual Momentum. ETF strategies too correlated (0.93-0.96) for much diversification benefit; Stock Momentum at 0.71 correlation is the key diversifier.
- **Key insight**: Individual stocks provide far more dispersion than ETFs — momentum alpha requires dispersion
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period. Charts and SPY comparison start from the first active trading day.
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/portfolio.py`

### Architecture
```
data/pipeline.py          — yfinance ETF data download & caching
data/sp500.py             — S&P 500 stock universe + VIX data
strategies/base.py        — Abstract strategy interface
strategies/trend_following.py — Time-Series & Multi-Timeframe Momentum
strategies/momentum.py    — Cross-Sectional & Dual Momentum (ETF-based)
strategies/stock_momentum.py — Individual stock momentum + VIX filter
strategies/portfolio.py   — Portfolio combiner + SPY 200-day MA trend filter
backtesting/metrics.py    — Sharpe, drawdown, Kelly, profit factor
backtesting/validation.py — Walk-forward, Monte Carlo, regime tests
execution/risk_manager.py — Fractional Kelly + 2% rule + circuit breakers
api/main.py              — FastAPI backend
dashboard/               — React + Vite + TradingView Charts
```

### Running the Project
- **Backend**: `uv run uvicorn api.main:app --reload` (from project root)
- **Frontend**: `cd dashboard && npm run dev` → http://localhost:5173
- **Validation**: `uv run python3 -c "from backtesting.validation import full_validation; ..."`

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript

### Current Phase & Next Steps
- Completed: Phase 1 (core engine), Phase 2 (strategies), Phase 2.5 (dashboard), Phase 3 (strategy expansion), Phase 3.5 (performance optimization)
- **SM + SPY Filter: 17.6% return, 1.38 Sharpe, -12.2% MaxDD — beats SPY on every metric with 1/3 the drawdown**
- Dashboard shows 8 strategies with SPY buy-and-hold overlay (red) on all equity curves
- Known risk: momentum crash vulnerability during sharp regime changes (COVID). VIX + SPY trend filter together provide strong but imperfect protection.
- Next: Alpaca paper trading integration