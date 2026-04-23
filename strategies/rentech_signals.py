"""
RenTech-flavored weak-signal library for the Account 5 POC.

Each cross-sectional signal function takes a prices DataFrame (date x ticker)
and returns a ranks DataFrame (date x ticker, values in [0,1]). 1.0 = strongest
bullish signal; NaN = insufficient history (excluded from selection naturally).

Design principles per HUNT_APR2026 RenTech scout:
- Price-only (no cached volume data across S&P 500)
- Orthogonal to A1's 9mo-skip-1mo momentum — no long-term momentum signals
- Published academic basis for each signal
- Weak signals are EXPECTED; the ensemble is the idea
- Rank-based combining is outlier-robust

Academic citations inline per signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_rank(df: pd.DataFrame, ascending: bool) -> pd.DataFrame:
    """Cross-sectional rank each row (date), scale to [0,1]. NaN stays NaN.

    ascending=True → lowest value gets rank 1.0 (useful for "low is bullish"
    signals like reversal / low-IVOL). ascending=False → highest is 1.0.
    """
    ranks = df.rank(axis=1, ascending=ascending, method="average", pct=True)
    return ranks


# -------------------------------------------------------------------------
# Cross-sectional signals (for stock selection)
# -------------------------------------------------------------------------


def short_reversal(prices: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """5-day cross-sectional short reversal.

    Jegadeesh (1990), "Evidence of Predictable Behavior of Security Returns."
    Stocks with the worst recent returns tend to bounce back. Long-only
    adaptation: rank ascending on trailing-N return; highest rank = biggest
    recent loser = best expected reversal.

    Weak signal; realistic forward edge ~3-5 bps/day gross on the top decile
    in post-2015 data. Costs eat most of it at monthly rebalance cadence —
    ensemble is the only way this adds value.
    """
    ret = prices.pct_change(lookback)
    return _to_rank(ret, ascending=True)


def near_52wh(prices: pd.DataFrame, lookback: int = 252) -> pd.DataFrame:
    """52-week high proximity.

    George & Hwang (2004), "The 52-Week High and Momentum Investing," JF.
    Stocks near their 52-week highs tend to continue; far from highs tend to
    underperform. Rank descending on Close / 252d-max — closest to 1.0 = rank 1.

    Distinct from A1's 9mo momentum: uses LEVEL (peak reference) not RETURN,
    captures "nearness to breakout" vs "cumulative gain." Correlation to A1 is
    expected to be moderate (0.3-0.5) but not duplicative.
    """
    rolling_max = prices.rolling(lookback, min_periods=lookback // 2).max()
    proximity = prices / rolling_max
    return _to_rank(proximity, ascending=False)


def low_ivol(
    prices: pd.DataFrame,
    market_prices: pd.Series,
    lookback: int = 63,
) -> pd.DataFrame:
    """Low idiosyncratic volatility anomaly.

    Ang, Hodrick, Xing, Zhang (2006), "The Cross-Section of Volatility and
    Expected Returns," JF. Stocks with low residual volatility (vs market)
    outperform high-IVOL stocks — counterintuitive result that has held up.

    Implementation: residual = stock_return - beta * market_return, where beta
    is estimated over the same 63d window. Rank ascending on rolling std of
    residuals — lowest IVOL = rank 1.

    Note: A2 already holds a low-vol leg, so this signal will correlate with
    A2. The ensemble diversifies within the signal set, not within the book.
    """
    stock_ret = prices.pct_change()
    mkt_ret = market_prices.pct_change().reindex(stock_ret.index)

    # Rolling beta via covariance / variance. Vectorized per ticker.
    mkt_var = mkt_ret.rolling(lookback, min_periods=lookback // 2).var()

    residuals = pd.DataFrame(index=stock_ret.index, columns=stock_ret.columns, dtype=float)
    for ticker in stock_ret.columns:
        s = stock_ret[ticker]
        cov = s.rolling(lookback, min_periods=lookback // 2).cov(mkt_ret)
        beta = cov / mkt_var
        residuals[ticker] = s - beta * mkt_ret

    ivol = residuals.rolling(lookback, min_periods=lookback // 2).std()
    return _to_rank(ivol, ascending=True)


def trend_quality(prices: pd.DataFrame, lookback: int = 63) -> pd.DataFrame:
    """Trend quality (smoothness of recent uptrend).

    Rank by R² of log(price) regressed on time over the lookback window —
    a smooth/straight uptrend has R² near 1.0, a choppy/volatile trend has
    lower R². Captures "quality of trend" distinct from "strength of return."

    No direct canonical citation but conceptually in the Wilder / Connors
    technical-analysis tradition and parallels the "trend strength" factor
    some practitioners use (cf. Hurst-exponent approaches). Orthogonal to
    both momentum (slope sign/magnitude) and mean-reversion (short-term).
    """
    log_p = np.log(prices)

    def _r2(window_vals: np.ndarray) -> float:
        if np.isnan(window_vals).any() or len(window_vals) < 5:
            return np.nan
        x = np.arange(len(window_vals), dtype=float)
        y = window_vals
        x_mean, y_mean = x.mean(), y.mean()
        cov = ((x - x_mean) * (y - y_mean)).sum()
        var_x = ((x - x_mean) ** 2).sum()
        if var_x == 0:
            return np.nan
        slope = cov / var_x
        y_pred = y_mean + slope * (x - x_mean)
        ss_res = ((y - y_pred) ** 2).sum()
        ss_tot = ((y - y_mean) ** 2).sum()
        if ss_tot == 0:
            return np.nan
        r2 = 1 - ss_res / ss_tot
        # Sign by slope so downtrends don't get "high quality" credit
        return r2 * np.sign(slope)

    # Apply row-wise rolling — pandas rolling.apply is slow but this is a POC
    r2_df = log_p.rolling(lookback, min_periods=lookback).apply(_r2, raw=True)
    return _to_rank(r2_df, ascending=False)


def price_acceleration(
    prices: pd.DataFrame,
    short: int = 5,
    long: int = 21,
) -> pd.DataFrame:
    """Price acceleration — short-term return minus medium-term.

    Captures inflection points: a stock whose 5d return is strong relative
    to its 21d return is accelerating; rank descending on (ret_5 - ret_21).
    Orthogonal to A1's 9-month momentum (too long) and to short_reversal
    (5d alone); it's the DIFFERENCE that matters.

    No canonical single paper — variant of the "intermediate momentum" or
    "momentum acceleration" factors discussed in Novy-Marx's research.
    """
    ret_short = prices.pct_change(short)
    ret_long = prices.pct_change(long)
    accel = ret_short - ret_long
    return _to_rank(accel, ascending=False)


# -------------------------------------------------------------------------
# Market-timing overlays (affect exposure, not selection)
# -------------------------------------------------------------------------


def turn_of_month_boost(dates: pd.DatetimeIndex) -> pd.Series:
    """Turn-of-month exposure multiplier.

    Ariel (1987), Ogden (1990). Excess equity returns concentrate in the
    last 2 trading days of one month + first 3 of the next. Effect has
    decayed from ~0.15%/event (1987-2005) to ~0.05%/event (2010+) — weak
    but alive. Used as exposure multiplier, not stock selector.

    Returns Series indexed by `dates` with values 1.0 (TOM window) or 0.85
    (non-TOM days).
    """
    out = pd.Series(0.85, index=dates)
    # Mark last 2 + first 3 business days of each calendar month
    month_index = dates.to_series().groupby([dates.year, dates.month])
    for _, group in month_index:
        sorted_days = group.sort_index().index
        if len(sorted_days) >= 3:
            out.loc[sorted_days[:3]] = 1.0  # first 3 of month
        if len(sorted_days) >= 2:
            out.loc[sorted_days[-2:]] = 1.0  # last 2 of month
    return out


def spy_trend_filter(spy: pd.Series, ma_period: int = 200) -> pd.Series:
    """Binary SPY 200d MA filter. Below MA = 0.5, above = 1.0. Matches A1's
    regime filter."""
    spy_ma = spy.rolling(ma_period, min_periods=ma_period).mean()
    return (spy > spy_ma).astype(float).clip(lower=0.5, upper=1.0) * 0.5 + 0.5


# -------------------------------------------------------------------------
# Ensemble combiner (equal-weight ranks → composite rank)
# -------------------------------------------------------------------------


def combine_ranks(signal_ranks: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Equal-weight mean of signal ranks into a composite rank.

    Each input DataFrame is in [0,1] (NaN where signal missing). NaN-safe
    row-wise average: where a signal is missing for a given (date, ticker),
    that cell is excluded from the denominator — stocks with partial signal
    coverage still get a score from whichever signals have data. Output in [0,1].
    """
    combined_sum: pd.DataFrame | None = None
    combined_count: pd.DataFrame | None = None
    for df in signal_ranks.values():
        mask = df.notna().astype(float)
        filled = df.fillna(0)
        if combined_sum is None:
            combined_sum = filled.copy()
            combined_count = mask.copy()
        else:
            combined_sum = combined_sum.add(filled, fill_value=0)
            combined_count = combined_count.add(mask, fill_value=0)
    assert combined_count is not None and combined_sum is not None
    composite = combined_sum / combined_count.replace(0, np.nan)
    return composite


def signal_orthogonality_matrix(
    signal_ranks: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """Pairwise Pearson correlation between signal rank panels.

    For each pair of signals, stack rank values across (date, ticker) and
    correlate. High correlation (>0.7) = redundant; <0.3 = genuinely
    orthogonal.
    """
    names = list(signal_ranks.keys())
    corr = pd.DataFrame(index=names, columns=names, dtype=float)
    series = {name: df.stack() for name, df in signal_ranks.items()}
    for i, n1 in enumerate(names):
        for n2 in names[i:]:
            # Align on common index (date, ticker)
            s1, s2 = series[n1].align(series[n2], join="inner")
            c = s1.corr(s2) if len(s1) > 100 else np.nan
            corr.loc[n1, n2] = c
            corr.loc[n2, n1] = c
    return corr
