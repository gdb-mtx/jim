"""Live-path portfolio configuration — PORTFOLIOS dict + filter functions.

Split out from strategies/portfolio.py per DEPLOYMENT_PLAN.md §Phase 0 so the
live trading surface (execution/, scripts/filter_check.py, api/routes/) can
import only what it needs without dragging in pandas-heavy backtest code.

Hard invariant: this module has zero imports from `backtesting/` or `mode2/`.
The companion `strategies/portfolio_backtest.py` may import from here, never
the other way around.
"""

import numpy as np
import pandas as pd

from data.pipeline import download_and_cache
from data.alpaca_crypto_bars import get_btc_bars
from strategies.trend_following import TimeSeriesMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum
from strategies.multi_asset_trend import MultiAssetTrend
from strategies.low_volatility import LowVolatility
from strategies.mean_reversion import ShortTermReversal
from strategies.crypto_momentum import CryptoMomentum


PORTFOLIOS = {
    # --- Account 1: Momentum (existing) ---
    "sm_filtered": {
        "name": "Stock Momentum + SPY Filter",
        "weights": {"stock_momentum": 1.0},
        "spy_filter": True,
        # Book-level vol scaling added 2026-07-18 (George-approved). The
        # strategy's per-name 20% vol targeting leaves the diversified book
        # at 22-70% gross and never re-levers the aggregate; this overlay
        # recaptures the diversification benefit (OOS 25.3%→31.1% CAGR,
        # Calmar 2.56→2.82). Same params/infra as trend_lowvol.
        "vol_scaling": True,
        "vol_scaling_params": {
            "vol_target": 0.15,
            "vol_halflife": 21,
            "scalar_floor": 0.5,
            "scalar_cap": 1.5,
        },
    },
    "blend_filtered": {
        "name": "Blended Portfolio + SPY Filter",
        "weights": {
            "stock_momentum": 0.60,
            "cross_sectional": 0.20,
            "dual_momentum": 0.20,
        },
        "spy_filter": True,
    },
    "blend_no_filter": {
        "name": "Blended Portfolio",
        "weights": {
            "stock_momentum": 0.60,
            "cross_sectional": 0.20,
            "dual_momentum": 0.20,
        },
        "spy_filter": False,
    },
    # --- Account 2: Trend + Low-Vol ---
    # Optimized: 30/70 MAT/LV (Sharpe 1.36 vs 1.33 at 50/50)
    # Low-Vol does the heavy lifting; MAT provides crisis alpha hedge
    "trend_lowvol": {
        "name": "Trend + Low-Vol",
        "weights": {
            "multi_asset_trend": 0.30,
            "low_volatility": 0.70,
        },
        "spy_filter": True,
        "vol_scaling": True,
        "vol_scaling_params": {
            "vol_target": 0.15,
            "vol_halflife": 21,
            "scalar_floor": 0.5,
            # 1.5 restores the strategy's original validated design (calm-regime
            # extension into Reg-T margin, equity accounts only — cap=1.0
            # alignment 2026-04 dropped OOS CAGR to 11%; see HISTORY.md
            # 2026-07-18). Live path clamps crypto books to 1.0.
            "scalar_cap": 1.5,
        },
    },
    "multi_asset_trend": {
        "name": "Multi-Asset Trend",
        "weights": {"multi_asset_trend": 1.0},
        "spy_filter": False,  # strategy has its own trend filter built in
    },
    "low_volatility": {
        "name": "Low Volatility",
        "weights": {"low_volatility": 1.0},
        "spy_filter": True,
    },
    # --- Account 3: Reversal + Momentum Hedge ---
    # Optimized: 60/40 STR/SM (Sharpe 1.54 vs 1.41 pure reversal)
    # Blending reversal with its opposite smooths the equity curve
    "reversal_blend": {
        "name": "Reversal + Momentum Blend",
        "weights": {
            "short_term_reversal": 0.60,
            "stock_momentum": 0.40,
        },
        "spy_filter": True,
    },
    "short_term_reversal": {
        "name": "Short-Term Reversal",
        "weights": {"short_term_reversal": 1.0},
        "spy_filter": True,
    },
    # --- Account 4: Crypto Momentum ---
    # BTC filter is built into CryptoMomentum strategy (125d SMA, robust-opt production).
    # Don't apply a second filter at the portfolio level.
    "crypto_momentum_filtered": {
        "name": "Crypto Momentum + BTC Filter",
        "weights": {"crypto_momentum": 1.0},
        "spy_filter": False,
        "btc_filter": False,
        "vol_scaling": True,
        "vol_scaling_params": {
            "vol_target": 0.15,
            "vol_halflife": 30,
            "scalar_floor": 0.1,
            "scalar_cap": 1.0,
        },
    },
}

# Strategy classes keyed by ID
ETF_STRATEGIES = {
    "ts_momentum": TimeSeriesMomentum,
    "cross_sectional": CrossSectionalMomentum,
    "dual_momentum": DualMomentum,
    "multi_asset_trend": MultiAssetTrend,
}

STOCK_STRATEGIES = {
    "stock_momentum": StockMomentum,
    "low_volatility": LowVolatility,
    "short_term_reversal": ShortTermReversal,
}

CRYPTO_STRATEGIES = {
    "crypto_momentum": CryptoMomentum,
}


def compute_spy_trend_filter(
    start: str = "2010-01-01",
    ma_period: int = 200,
    reduction: float = 0.5,
    live_price: float | None = None,
) -> pd.Series:
    """Compute SPY trend filter: 1.0 when above MA, `reduction` when below.

    Args:
        start: Start date for SPY data (needs extra history for MA warmup)
        ma_period: Moving average period (default 200 days)
        reduction: Position scalar when below MA (0.5 = half exposure)
        live_price: Real-time SPY price (e.g. from Alpaca) to override
            the last cached yfinance close. The 200d MA is unaffected
            (1/200th shift is negligible).

    Returns:
        Series of scalars (1.0 or reduction) indexed by date
    """
    # Download extra history for MA warmup
    spy_prices = download_and_cache(["SPY"], start="2008-01-01", cache_name="spy_filter")
    spy_close = spy_prices["SPY"] if "SPY" in spy_prices.columns else spy_prices.squeeze()

    # Override last close with real-time price for live trading decisions
    if live_price is not None:
        spy_close = spy_close.copy()
        spy_close.iloc[-1] = live_price

    spy_ma = spy_close.rolling(ma_period, min_periods=ma_period).mean()

    above_ma = spy_close > spy_ma
    scalar = pd.Series(np.where(above_ma, 1.0, reduction), index=spy_close.index)

    return scalar


def compute_btc_trend_filter(
    start: str = "2021-01-01",
    ma_period: int = 125,
    live_price: float | None = None,
) -> pd.Series:
    """Compute BTC trend filter: 1.0 when above MA, 0.0 when below.

    Uses 125d SMA (robust-opt production, 2026-04-18 — see
    scripts/crypto_robust_opt.py). Parameters scored by
    min(Calmar_half_A, Calmar_half_B) across 144 configs; SMA-125/top2
    was the regime-robust winner. Prior defaults: 150d (autoresearch,
    regime-lucky), then 200d (conservative). Unlike SPY filter which
    reduces to 0.5, crypto bear markets warrant full exit (1.0 or 0.0).

    Live BTC prices come from Alpaca's bars endpoint (broker-native, no
    publishing delay). Backtest BTC history still comes from yfinance via
    strategies/portfolio_backtest.py — Alpaca only goes back to 2021-01-01.

    Args:
        start: Start date for BTC data (needs history for MA warmup;
            Alpaca's earliest BTC bar is 2021-01-01).
        ma_period: Moving average period (default 125 days).
        live_price: Real-time BTC price (e.g. from Alpaca latest trade)
            to override the last bar's close.

    Returns:
        Series of scalars (1.0 or 0.0) indexed by date
    """
    btc_prices = get_btc_bars(start=start)

    if live_price is not None:
        btc_prices = btc_prices.copy()
        btc_prices.iloc[-1] = live_price

    btc_ma = btc_prices.rolling(ma_period, min_periods=ma_period).mean()
    above_ma = btc_prices > btc_ma
    scalar = pd.Series(np.where(above_ma, 1.0, 0.0), index=btc_prices.index)
    return scalar
