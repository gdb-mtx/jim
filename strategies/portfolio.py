"""
Combined Portfolio Strategy with SPY Trend Filter + Vol-Scaling Overlay.

Blends multiple strategy return streams and applies market regime overlays:
1. SPY 200-day MA trend filter (Faber 2007)
2. Volatility-scaling overlay (Moreira & Muir 2017)

Three-account architecture for uncorrelated factor diversification:
- Account 1: Momentum (existing SM + SPY Filter)
- Account 2: Trend + Low-Vol (crisis alpha + defensive)
- Account 3: Reversal (anti-momentum hedge)

Academic basis:
- Faber (2007): "A Quantitative Approach to Tactical Asset Allocation"
- Moreira & Muir (2017): "Volatility-Managed Portfolios" — scaling equity
  exposure by inverse realized vol adds +0.1-0.3 Sharpe
- Barroso & Santa-Clara (2015): Vol-scaling on momentum eliminates crash risk
"""

import numpy as np
import pandas as pd
from data.pipeline import download_and_cache, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from strategies.trend_following import TimeSeriesMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum
from strategies.multi_asset_trend import MultiAssetTrend
from strategies.low_volatility import LowVolatility
from strategies.mean_reversion import ShortTermReversal
from strategies.crypto_momentum import CryptoMomentum
from data.crypto import download_crypto_prices, download_btc_prices


# ── Preset portfolio configurations ──────────────────────────────────
#
# Account 1 (Momentum): profits when trends persist
# Account 2 (Trend + Low-Vol): crisis alpha + defensive stocks
# Account 3 (Reversal): anti-momentum, buys short-term losers
#
PORTFOLIOS = {
    # --- Account 1: Momentum (existing) ---
    "sm_filtered": {
        "name": "Stock Momentum + SPY Filter",
        "weights": {"stock_momentum": 1.0},
        "spy_filter": True,
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
            "scalar_cap": 1.0,
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


def _generate_strategy_returns(
    strategy_id: str,
    etf_prices: pd.DataFrame,
    stock_prices: pd.DataFrame | None = None,
    vix: pd.Series | None = None,
    crypto_prices: pd.DataFrame | None = None,
    btc_prices: pd.Series | None = None,
) -> pd.Series:
    """Generate returns for a single strategy."""
    if strategy_id in CRYPTO_STRATEGIES:
        strategy = CRYPTO_STRATEGIES[strategy_id]()
        if btc_prices is not None:
            strategy.set_btc(btc_prices)
        returns = strategy.generate_returns(crypto_prices)
    elif strategy_id in STOCK_STRATEGIES:
        strategy = STOCK_STRATEGIES[strategy_id]()
        if vix is not None:
            strategy.set_vix(vix)
        returns = strategy.generate_returns(stock_prices)
    else:
        strategy = ETF_STRATEGIES[strategy_id]()
        returns = strategy.generate_returns(etf_prices)

    # Trim warmup
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    return returns


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

    spy_ma = spy_close.rolling(ma_period).mean()

    above_ma = spy_close > spy_ma
    scalar = pd.Series(np.where(above_ma, 1.0, reduction), index=spy_close.index)

    return scalar


def compute_btc_trend_filter(
    start: str = "2018-01-01",
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

    Args:
        start: Start date for BTC data (needs history for MA warmup)
        ma_period: Moving average period (default 200 days)
        live_price: Real-time BTC price (e.g. from Alpaca) to override
            the last cached yfinance close.

    Returns:
        Series of scalars (1.0 or 0.0) indexed by date
    """
    btc_prices = download_btc_prices(start=start)

    if live_price is not None:
        btc_prices = btc_prices.copy()
        btc_prices.iloc[-1] = live_price

    btc_ma = btc_prices.rolling(ma_period).mean()
    above_ma = btc_prices > btc_ma
    scalar = pd.Series(np.where(above_ma, 1.0, 0.0), index=btc_prices.index)
    return scalar


def apply_vol_scaling(
    returns: pd.Series,
    vol_target: float = 0.15,
    vol_halflife: int = 21,
    scalar_floor: float = 0.5,
    scalar_cap: float = 1.0,
) -> pd.Series:
    """Apply volatility-scaling overlay to portfolio returns.

    Scales exposure inversely to recent realized volatility. When the market
    is calm, take more risk. When turbulent, take less.

    Academic basis:
    - Moreira & Muir (2017): "Volatility-Managed Portfolios"
      Scaling by inverse vol adds +0.1-0.3 Sharpe because high-vol periods
      do not compensate with proportionally higher returns.
    - Barroso & Santa-Clara (2015): Vol-scaling on momentum eliminates crashes.

    Args:
        returns: Daily strategy returns
        vol_target: Target annualized vol (0.15 = 15%)
        vol_halflife: EWMA half-life in days for vol estimation
        scalar_floor: Minimum exposure (0.5 = never below 50%)
        scalar_cap: Maximum exposure (1.0 = no leverage; matches Alpaca paper /
                    spot-only constraints. AUDIT_MONTH2 C4: live had no
                    vol-scaling overlay and couldn't realize a 1.5x scalar even
                    if it had one. Cap=1.0 keeps sim and live apples-to-apples.)

    Returns:
        Vol-scaled daily returns
    """
    # EWMA realized vol (responds faster to regime changes than rolling window)
    ewma_var = returns.ewm(halflife=vol_halflife).var()
    realized_vol = np.sqrt(ewma_var) * np.sqrt(252)

    # Scalar: target / realized, capped
    scalar = vol_target / realized_vol.replace(0, np.nan)
    scalar = scalar.clip(lower=scalar_floor, upper=scalar_cap)

    # Lag by 1 day (use yesterday's vol estimate for today's sizing)
    scalar = scalar.shift(1).fillna(1.0)

    return returns * scalar


def run_portfolio(
    portfolio_id: str,
    start: str = "2010-01-01",
    end: str | None = None,
) -> tuple[str, pd.Series]:
    """Run a combined portfolio and return (name, returns Series).

    Args:
        portfolio_id: Key into PORTFOLIOS dict
        start: Backtest start date
        end: Backtest end date (optional)

    Returns:
        Tuple of (portfolio_name, combined_returns_series)
    """
    config = PORTFOLIOS[portfolio_id]
    weights = config["weights"]
    use_spy_filter = config["spy_filter"]
    use_btc_filter = config.get("btc_filter", False)
    use_vol_scaling = config.get("vol_scaling", False)
    vol_scaling_params = config.get("vol_scaling_params", {})

    # Load data
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    etf_prices = download_and_cache(symbols, start=start, end=end, cache_name="etf_prices")

    stock_prices = None
    vix = None
    if any(sid in STOCK_STRATEGIES for sid in weights):
        stock_prices = download_sp500_prices(start=start)
        vix = download_vix()

    crypto_prices = None
    btc_prices = None
    if any(sid in CRYPTO_STRATEGIES for sid in weights):
        crypto_prices = download_crypto_prices(start=start)
        btc_prices = download_btc_prices()

    # Generate returns for each component strategy
    strategy_returns = {}
    for strategy_id in weights:
        strategy_returns[strategy_id] = _generate_strategy_returns(
            strategy_id, etf_prices, stock_prices, vix, crypto_prices, btc_prices
        )

    # Align to common dates and compute weighted blend
    aligned = pd.DataFrame(strategy_returns).dropna()
    combined = sum(aligned[sid] * w for sid, w in weights.items())

    # Apply SPY trend filter
    if use_spy_filter:
        spy_filter = compute_spy_trend_filter(start=start)
        spy_aligned = spy_filter.reindex(combined.index).ffill().fillna(1.0)
        combined = combined * spy_aligned

    # Apply BTC trend filter (binary: 1.0 or 0.0)
    if use_btc_filter:
        btc_filter = compute_btc_trend_filter(start=start)
        btc_aligned = btc_filter.reindex(combined.index).ffill().fillna(1.0)
        combined = combined * btc_aligned

    # Apply vol-scaling overlay (Moreira & Muir 2017)
    if use_vol_scaling:
        combined = apply_vol_scaling(combined, **vol_scaling_params)

    return config["name"], combined


# Live book after A3 retirement (2026-04-21): A1 + A2 + A4 at 1/3 each.
LIVE_ACCOUNT_STRATEGIES = ["sm_filtered", "trend_lowvol", "crypto_momentum_filtered"]

# Equity-only core (A1 + A2) — base for A4's marginal portfolio contribution.
EQUITY_CORE_STRATEGIES = ["sm_filtered", "trend_lowvol"]


def run_equity_core(
    start: str = "2010-01-01",
    end: str | None = None,
) -> tuple[str, pd.Series]:
    """Run the equity-only core (A1 + A2) at 50/50 on the equity calendar.

    Used as the "existing book" base when measuring A4's marginal
    portfolio contribution. Returns a 252-day-convention series.
    """
    account_returns = {}
    for pid in EQUITY_CORE_STRATEGIES:
        _, returns = run_portfolio(pid, start=start, end=end)
        account_returns[pid] = returns

    aligned = pd.DataFrame(account_returns).dropna()
    combined = aligned.mean(axis=1)
    return "Equity Core (A1 + A2)", combined


def run_combined_portfolio(
    start: str = "2010-01-01",
    end: str | None = None,
) -> tuple[str, pd.Series]:
    """Run the full live book: A1 + A2 + A4 at 1/3 each on the equity calendar.

    A4's crypto returns are compounded across weekends so Monday's A4 return
    reflects the Fri→Mon cumulative BTC move. The series starts from the
    latest strategy's first day (A4 inception = 2020-09-11). Callers
    annualize with periods_per_year=252.
    """
    account_returns = {}
    for pid in LIVE_ACCOUNT_STRATEGIES:
        _, returns = run_portfolio(pid, start=start, end=end)
        non_zero = returns[(returns != 0) & returns.notna()]
        if len(non_zero):
            returns = returns.loc[non_zero.index[0]:]
        account_returns[pid] = returns

    eq_cal = account_returns["sm_filtered"].index.union(
        account_returns["trend_lowvol"].index
    )
    latest_start = max(s.index[0] for s in account_returns.values())
    eq_cal = eq_cal[eq_cal >= latest_start]

    def _to_equity_calendar(r: pd.Series) -> pd.Series:
        equity_curve = (1.0 + r).cumprod()
        on_eq = equity_curve.reindex(eq_cal, method="ffill")
        return on_eq.pct_change()

    on_calendar = {k: _to_equity_calendar(v) for k, v in account_returns.items()}
    df = pd.DataFrame(on_calendar).dropna()
    combined = df.mean(axis=1)
    return "Combined Live Portfolio (A1 + A2 + A4)", combined
