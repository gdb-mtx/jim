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

### Strategies (5 implemented, warmup-trimmed metrics)
| Strategy | Sharpe | Return | MaxDD | Walk-Forward | Validation |
|---|---|---|---|---|---|
| **Stock Momentum (S&P 500)** | **1.16** | **15.9%** | **-18.6%** | **1.27 median OOS** | WF+MC pass, regime partial |
| Time-Series Momentum | 0.85 | 6.2% | -15.2% | 0.78 median OOS | PASS |
| Multi-Timeframe Momentum | 0.67 | 4.1% | -11.0% | 0.55 median OOS | FAIL (regime) |
| Cross-Sectional Momentum | 0.85 | 7.0% | -10.8% | 0.82 median OOS | PASS |
| Dual Momentum (Antonacci) | 0.83 | 7.6% | -19.9% | 0.76 median OOS | PASS |
| *SPY Buy & Hold (benchmark)* | *0.84* | *13.7%* | *-33.7%* | — | — |

- **Best performer**: Stock Momentum — beats SPY return (15.9% vs 13.7%) with higher Sharpe and half the drawdown
- **ETF Universe**: 18 assets (8 broad ETFs + 9 sector ETFs + SHY cash proxy)
- **Stock Universe**: 451 S&P 500 stocks (cached parquet, survivorship bias noted)
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45
- **Key insight**: Individual stocks provide far more dispersion than ETFs — momentum alpha requires dispersion
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period (lookback + vol window). Charts and SPY comparison start from the first active trading day for fair comparison.
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`

### Architecture
```
data/pipeline.py          — yfinance ETF data download & caching
data/sp500.py             — S&P 500 stock universe + VIX data
strategies/base.py        — Abstract strategy interface
strategies/trend_following.py — Time-Series & Multi-Timeframe Momentum
strategies/momentum.py    — Cross-Sectional & Dual Momentum (ETF-based)
strategies/stock_momentum.py — Individual stock momentum + VIX filter
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
- Completed: Phase 1 (core engine), Phase 2 (strategies), Phase 2.5 (dashboard), Phase 3 (strategy iteration)
- **Stock Momentum beats SPY (15.9% vs 13.7%) with 1.16 Sharpe and half the drawdown**
- Dashboard shows SPY buy-and-hold overlay (red) on all equity curves for comparison
- Known risk: momentum crash vulnerability during sharp regime changes (COVID)
- Next: Alpaca paper trading integration, portfolio-level combination of strategies