"""Strategy endpoints — list strategies and their performance.

Runs actual backtests to compute live metrics instead of hardcoding.
"""

from fastapi import APIRouter
from data.pipeline import download_prices, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from strategies.trend_following import TimeSeriesMomentum, MultiTimeframeMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum
from strategies.multi_asset_trend import MultiAssetTrend
from strategies.low_volatility import LowVolatility
from strategies.mean_reversion import ShortTermReversal
from strategies.portfolio import PORTFOLIOS, run_portfolio
from backtesting.metrics import full_report

router = APIRouter()

ETF_STRATEGY_CLASSES = [
    ("ts_momentum", TimeSeriesMomentum),
    ("multi_tf_momentum", MultiTimeframeMomentum),
    ("cross_sectional", CrossSectionalMomentum),
    ("dual_momentum", DualMomentum),
    ("multi_asset_trend_solo", MultiAssetTrend),
]

STOCK_STRATEGY_CLASSES = [
    ("stock_momentum", StockMomentum),
    ("low_volatility_solo", LowVolatility),
    ("short_term_reversal_solo", ShortTermReversal),
]

_cached_metrics: list[dict] | None = None


@router.get("/")
async def list_strategies():
    """List all available strategies with latest metrics."""
    global _cached_metrics
    if _cached_metrics is not None:
        return _cached_metrics

    results = []

    # ETF strategies
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    etf_prices = download_prices(symbols, start="2010-01-01")

    for strategy_id, cls in ETF_STRATEGY_CLASSES:
        strategy = cls()
        returns = strategy.generate_returns(etf_prices)
        # Trim warmup period (flat returns before strategy starts trading)
        non_zero = returns[returns != 0]
        if len(non_zero) > 0:
            returns = returns.loc[non_zero.index[0]:]
        report = full_report(returns, name=strategy.name)
        results.append({
            "name": strategy.name,
            "id": strategy_id,
            "status": "backtesting",
            "annualized_return": report["annualized_return"],
            "sharpe_ratio": report["sharpe_ratio"],
            "max_drawdown": report["max_drawdown"],
            "win_rate": report["win_rate"],
            "validation_passed": report["sharpe_ratio"] >= 1.0,
        })

    # Stock strategies
    try:
        stock_prices = download_sp500_prices(start="2010-01-01")
        vix = download_vix()
        for strategy_id, cls in STOCK_STRATEGY_CLASSES:
            strategy = cls()
            strategy.set_vix(vix)
            returns = strategy.generate_returns(stock_prices)
            non_zero = returns[returns != 0]
            if len(non_zero) > 0:
                returns = returns.loc[non_zero.index[0]:]
            report = full_report(returns, name=strategy.name)
            results.append({
                "name": strategy.name,
                "id": strategy_id,
                "status": "backtesting",
                "annualized_return": report["annualized_return"],
                "sharpe_ratio": report["sharpe_ratio"],
                "max_drawdown": report["max_drawdown"],
                "win_rate": report["win_rate"],
                "validation_passed": report["sharpe_ratio"] >= 1.0,
            })
    except Exception as e:
        print(f"Warning: Could not load stock strategies: {e}")

    # Portfolio strategies (combinations + filters)
    try:
        for portfolio_id, config in PORTFOLIOS.items():
            name, returns = run_portfolio(portfolio_id, start="2010-01-01")
            report = full_report(returns, name=name)
            results.append({
                "name": name,
                "id": portfolio_id,
                "status": "backtesting",
                "annualized_return": report["annualized_return"],
                "sharpe_ratio": report["sharpe_ratio"],
                "max_drawdown": report["max_drawdown"],
                "win_rate": report["win_rate"],
                "validation_passed": report["sharpe_ratio"] >= 1.0,
            })
    except Exception as e:
        print(f"Warning: Could not load portfolio strategies: {e}")

    _cached_metrics = results
    return results
