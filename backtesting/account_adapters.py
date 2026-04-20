"""
Account Adapters — Per-account glue for the validation runner.

Each account is a live-paper strategy in production. To validate it, we
need two things: the full-sample strategy return series (for OOS holdout,
rolling-Sharpe, and bootstrap) and, where practical, a `strategy_fn`
closure that re-runs the strategy on arbitrary price slices (for the
walk_forward_analysis function in backtesting/validation.py).

Account 4 (crypto) and Account 1 (single-universe stock momentum) get
the full walk-forward treatment. Accounts 2 and 3 blend strategies on
different universes, so they expose the full-sample returns only and we
do rolling-window Sharpe on those returns. Documented honestly in the
report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from data.crypto import download_btc_prices, download_crypto_prices
from data.sp500 import download_sp500_prices, download_vix
from strategies.crypto_momentum import CryptoMomentum
from strategies.mean_reversion import ShortTermReversal
from strategies.low_volatility import LowVolatility
from strategies.portfolio import (
    apply_vol_scaling,
    compute_spy_trend_filter,
    run_portfolio,
)
from strategies.stock_momentum import StockMomentum


@dataclass
class AccountAdapter:
    """Bundle of everything the runner needs to validate one account."""

    account: int
    name: str
    portfolio_id: str
    periods_per_year: int
    start: str
    full_returns: pd.Series
    prices: pd.DataFrame | None  # None when rolling-OOS eval is not feasible
    strategy_fn: callable | None  # None when rolling-OOS eval is not feasible
    warmup_days: int
    walk_forward_supported: bool
    # Optional: inputs for Test 6 walk-forward REFIT. If all three are set,
    # Test 6 runs a per-window grid search on `refit_prices` using
    # `refit_strategy_factory(**params)` as the runner. For composite
    # accounts (e.g., A2 = 30% MAT + 70% LV), set these to refer to the
    # dominant or most-searchable leg; leave None to skip.
    refit_prices: "pd.DataFrame | None" = None
    refit_strategy_factory: "callable | None" = None
    refit_param_grid: "dict | None" = None
    refit_description: str = ""


def _spy_filter_scalar_series() -> pd.Series:
    """Precompute SPY 200d filter scalar over full history."""
    return compute_spy_trend_filter(start="2008-01-01", ma_period=200, reduction=0.5)


def _build_account_1() -> AccountAdapter:
    """Account 1: Stock Momentum + SPY Filter.

    Strategy_fn runs StockMomentum (with hardcoded defaults) on the sliced
    stock prices, with VIX injected from a precomputed closure, and applies
    the SPY 200d filter to the final returns.

    Note on "walk-forward": `walk_forward_supported=True` means this adapter
    is compatible with the rolling-OOS harness in `walk_forward_analysis`.
    That harness evaluates fixed-default params on rolling test windows — it
    does NOT refit parameters per window. For true walk-forward refit, see
    `walk_forward_refit_analysis` and the standalone scripts under
    `scripts/walk_forward_refit_*.py`.
    """
    full_returns = run_portfolio("sm_filtered", start="2010-01-01")[1].dropna()
    prices = download_sp500_prices(start="2010-01-01")
    vix = download_vix()
    spy_scalar = _spy_filter_scalar_series()

    def strategy_fn(slice_prices: pd.DataFrame) -> pd.Series:
        s = StockMomentum()
        s.set_vix(vix)
        raw = s.generate_returns(slice_prices)
        spy_aligned = spy_scalar.reindex(raw.index).ffill().fillna(1.0)
        return raw * spy_aligned

    # Test 6 (walk-forward REFIT) grid for A1 — small sweep over the two
    # parameters most likely to move the needle. Kept modest so Test 6
    # stays within ~15s per validation run. Expand in a standalone script
    # for deeper exploration (see scripts/walk_forward_refit_a1.py).
    def refit_factory(**params):
        def runner(slice_prices):
            s = StockMomentum(**params)
            s.set_vix(vix)
            raw = s.generate_returns(slice_prices)
            spy_aligned = spy_scalar.reindex(raw.index).ffill().fillna(1.0)
            return raw * spy_aligned
        return runner

    refit_grid = {
        "lookback_days": [126, 189, 252],
        "top_n": [10, 15, 20],
    }

    return AccountAdapter(
        account=1,
        name="Stock Momentum + SPY Filter",
        portfolio_id="sm_filtered",
        periods_per_year=252,
        start="2010-01-01",
        full_returns=full_returns,
        prices=prices,
        strategy_fn=strategy_fn,
        warmup_days=252,
        walk_forward_supported=True,
        refit_prices=prices,
        refit_strategy_factory=refit_factory,
        refit_param_grid=refit_grid,
        refit_description="StockMomentum over S&P 500 universe",
    )


def _build_account_2() -> AccountAdapter:
    """Account 2: 30% Multi-Asset Trend + 70% Low-Vol + SPY filter + vol-scaling.

    Two strategies on different universes (5 ETFs vs S&P 500 stocks).
    Rolling-OOS eval with a single combined strategy_fn is impractical here —
    the account uses rolling Sharpe on the precomputed full-sample returns.

    For Test 6 (walk-forward refit) we search the LowVolatility leg only
    (70% weight, S&P 500 universe). The Multi-Asset Trend leg is 5 ETFs
    with a tiny parameter surface and is not worth searching in the main
    validation flow.
    """
    full_returns = run_portfolio("trend_lowvol", start="2010-01-01")[1].dropna()

    # Test 6 refit inputs — search Low-Vol leg only
    lv_prices = download_sp500_prices(start="2010-01-01")
    lv_vix = download_vix()
    lv_spy = compute_spy_trend_filter(start="2008-01-01", ma_period=200, reduction=0.5)

    def refit_factory(**params):
        def runner(slice_prices):
            s = LowVolatility(**params)
            s.set_vix(lv_vix)
            raw = s.generate_returns(slice_prices)
            spy_aligned = lv_spy.reindex(raw.index).ffill().fillna(1.0)
            return raw * spy_aligned
        return runner

    refit_grid = {
        "vol_lookback_days": [42, 63, 84],
        "momentum_lookback_days": [126, 189, 252],
        "top_n": [20, 30, 40],
    }

    return AccountAdapter(
        account=2,
        name="Trend + Low-Vol",
        portfolio_id="trend_lowvol",
        periods_per_year=252,
        start="2010-01-01",
        full_returns=full_returns,
        prices=None,
        strategy_fn=None,
        warmup_days=0,
        walk_forward_supported=False,
        refit_prices=lv_prices,
        refit_strategy_factory=refit_factory,
        refit_param_grid=refit_grid,
        refit_description="LowVolatility leg only (70% of A2; Multi-Asset Trend leg not searched)",
    )


def _build_account_3() -> AccountAdapter:
    """Account 3: 60% Short-Term Reversal + 40% Stock Momentum + SPY filter.

    Both strategies run on S&P 500 stocks, so rolling-OOS evaluation is
    feasible. Like A1, this uses fixed-default params — no per-window
    parameter refit; see `walk_forward_refit_analysis` for that mode.
    """
    full_returns = run_portfolio("reversal_blend", start="2010-01-01")[1].dropna()
    prices = download_sp500_prices(start="2010-01-01")
    vix = download_vix()
    spy_scalar = _spy_filter_scalar_series()

    def strategy_fn(slice_prices: pd.DataFrame) -> pd.Series:
        str_strat = ShortTermReversal()
        str_strat.set_vix(vix)
        str_returns = str_strat.generate_returns(slice_prices)

        sm_strat = StockMomentum()
        sm_strat.set_vix(vix)
        sm_returns = sm_strat.generate_returns(slice_prices)

        aligned = pd.DataFrame(
            {"str": str_returns, "sm": sm_returns}
        ).dropna()
        blended = 0.6 * aligned["str"] + 0.4 * aligned["sm"]
        spy_aligned = spy_scalar.reindex(blended.index).ffill().fillna(1.0)
        return blended * spy_aligned

    return AccountAdapter(
        account=3,
        name="Reversal + Momentum Blend",
        portfolio_id="reversal_blend",
        periods_per_year=252,
        start="2010-01-01",
        full_returns=full_returns,
        prices=prices,
        strategy_fn=strategy_fn,
        warmup_days=252,
        walk_forward_supported=True,
    )


def _build_account_4() -> AccountAdapter:
    """Account 4: Crypto Momentum Rotation + 125d BTC filter + vol-scaling.

    Single universe (9 coins), BTC prices injected via closure. Vol-scaling
    applied to the returns after signal generation, matching the portfolio
    config. Uses fixed-default params (picked one-time via
    `scripts/crypto_robust_opt.py` on a 2-half train/test split with
    min-Calmar objective); the validation-runner's rolling-OOS harness runs
    these fixed params across windows — no per-window parameter refit.
    """
    full_returns = run_portfolio("crypto_momentum_filtered", start="2018-01-01")[1].dropna()
    prices = download_crypto_prices(start="2018-01-01")
    btc = download_btc_prices(start="2018-01-01")

    def strategy_fn(slice_prices: pd.DataFrame) -> pd.Series:
        s = CryptoMomentum()
        s.set_btc(btc)
        raw = s.generate_returns(slice_prices)
        return apply_vol_scaling(
            raw,
            vol_target=0.15,
            vol_halflife=30,
            scalar_floor=0.1,
            scalar_cap=1.5,
        )

    return AccountAdapter(
        account=4,
        name="Crypto Momentum + BTC Filter",
        portfolio_id="crypto_momentum_filtered",
        periods_per_year=365,
        start="2018-01-01",
        full_returns=full_returns,
        prices=prices,
        strategy_fn=strategy_fn,
        warmup_days=200,
        walk_forward_supported=True,
    )


_BUILDERS = {
    1: _build_account_1,
    2: _build_account_2,
    3: _build_account_3,
    4: _build_account_4,
}


def build_adapter(account: int) -> AccountAdapter:
    """Construct the adapter bundle for the given account number."""
    if account not in _BUILDERS:
        raise ValueError(f"Unknown account {account!r}; expected one of {list(_BUILDERS)}")
    return _BUILDERS[account]()
