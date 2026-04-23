"""
RenTech follow-up tests — digging deeper after the equal-weight ensemble
failed the gate. Three orthogonal tests on the same signal library:

  Test 1: low_ivol SOLO as a standalone candidate
          - Is A5=low_ivol a viable candidate?
          - Correlation vs A2's low-vol leg (if > 0.6, factor-duplicative)
          - OOS stats 2023-2026

  Test 2: A1-OVERLAY — the scout's meta-point
          - Add the 5 RenTech ranks to A1's 9mo-skip-1mo momentum rank
          - Pick top-15 by COMBINED rank, compare to A1 pure-momentum top-15
          - If combined beats pure, the ensemble is useful as overlay not standalone

  Test 3: SIGNAL-AGREEMENT ensemble
          - Instead of averaging ranks (which dilutes best signals), require at
            least K of N signals to put a stock in their top-30%
          - Harder-to-pass selection, higher conviction, fewer picks
          - Tests whether consensus (not average) is the right combining rule

All tests use the same cost / overlay / rebalance conventions for fair compare.

Usage:
    uv run python3 scripts/rentech_followup_tests.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")

from data.sp500 import download_sp500_prices  # noqa: E402
from strategies.rentech_signals import (  # noqa: E402
    combine_ranks,
    low_ivol,
    near_52wh,
    price_acceleration,
    short_reversal,
    spy_trend_filter,
    trend_quality,
    turn_of_month_boost,
    _to_rank,
)


IS_END = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END = "2026-04-20"
POST_2020 = "2021-01-01"  # Exclude the +158% COVID snapback year
REBALANCE_DAYS = 21
COST_BPS_ROUNDTRIP = 5.0
PERIODS_PER_YEAR = 252


def _load_spy() -> pd.Series:
    from data.pipeline import download_with_retry, write_parquet_atomic
    import time
    cache_path = ROOT / "data" / "raw" / "spy.parquet"
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 16:
            df = pd.read_parquet(cache_path)
            if list(df.columns) == ["SPY"]:
                return df.squeeze()
    df = download_with_retry(["SPY"], start="2009-01-01", min_coverage_ratio=1.0)
    s = df.iloc[:, 0]
    s.name = "SPY"
    write_parquet_atomic(s.to_frame(), cache_path)
    return s


def stats(net: pd.Series, label: str) -> dict:
    r = net.dropna()
    if len(r) == 0:
        return {"label": label, "bars": 0, "cagr": np.nan, "sharpe": np.nan,
                "maxdd": np.nan, "calmar": np.nan}
    cagr = (1 + r).prod() ** (PERIODS_PER_YEAR / len(r)) - 1
    sharpe = (r.mean() / r.std()) * np.sqrt(PERIODS_PER_YEAR) if r.std() > 0 else 0.0
    cum = (1 + r).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(maxdd) if maxdd else 0.0
    return {"label": label, "bars": len(r), "cagr": cagr, "sharpe": sharpe,
            "maxdd": maxdd, "calmar": calmar}


def print_row(s: dict) -> None:
    print(f"  {s['label']:<32} CAGR {s['cagr']:+7.1%}  "
          f"Sharpe {s['sharpe']:>5.2f}  MaxDD {s['maxdd']:+7.1%}  "
          f"Calmar {s['calmar']:>5.2f}  ({s['bars']} bars)")


def weights_from_rank(
    rank_df: pd.DataFrame,
    top_frac: float | None = None,
    top_n: int | None = None,
    rebalance_days: int = REBALANCE_DAYS,
    overlay_mult: pd.Series | None = None,
) -> pd.DataFrame:
    """Top-fraction OR top-N selection from cross-sectional rank [0,1]."""
    if top_n is not None:
        # Select top_n per row (highest ranks). Equivalent to rank-descending.
        ranks_desc = rank_df.rank(axis=1, ascending=False, method="average")
        selected = (ranks_desc <= top_n).astype(float)
    else:
        assert top_frac is not None
        threshold = 1 - top_frac
        selected = (rank_df >= threshold).astype(float)

    n_sel = selected.sum(axis=1).replace(0, 1)
    weights = selected.div(n_sel, axis=0)

    rebalance_mask = pd.Series(False, index=rank_df.index)
    valid_idx = weights.dropna(how="all").index
    if len(valid_idx) > 0:
        rebalance_dates = valid_idx[::rebalance_days]
        rebalance_mask.loc[rebalance_dates] = True
    weights[~rebalance_mask] = np.nan
    weights = weights.ffill().fillna(0)

    if overlay_mult is not None:
        aligned = overlay_mult.reindex(weights.index).ffill().fillna(1.0)
        weights = weights.mul(aligned, axis=0)

    return weights


def run(weights: pd.DataFrame, prices: pd.DataFrame) -> pd.Series:
    price_ret = prices.pct_change().fillna(0)
    gross = (price_ret * weights.shift(1)).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(0)
    cost = turnover * (COST_BPS_ROUNDTRIP / 10_000.0 / 2)
    return gross - cost


def a1_momentum_rank(prices: pd.DataFrame) -> pd.DataFrame:
    """Replicate StockMomentum's ranking: 9mo return skip recent 1mo,
    rank descending, return as [0,1] rank where 1 = strongest."""
    lagged = prices.shift(21)
    older = prices.shift(189)
    momentum = (lagged - older) / older
    # Rank descending internally then invert to [0,1] with 1=best
    return _to_rank(momentum, ascending=False)


def section_header(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}")


def main() -> int:
    print("Loading prices + SPY...")
    prices = download_sp500_prices(start="2010-01-01")
    spy = _load_spy().reindex(prices.index).ffill()

    print("Computing signal ranks...")
    signals = {
        "short_reversal":     short_reversal(prices, lookback=5),
        "near_52wh":          near_52wh(prices, lookback=252),
        "low_ivol":           low_ivol(prices, spy, lookback=63),
        "trend_quality":      trend_quality(prices, lookback=63),
        "price_acceleration": price_acceleration(prices, short=5, long=21),
    }
    momentum_rank = a1_momentum_rank(prices)

    spy_f = spy_trend_filter(spy, ma_period=200)
    tom = turn_of_month_boost(prices.index)
    overlay = spy_f.reindex(prices.index).ffill() * tom.reindex(prices.index).ffill()

    # =====================================================================
    # TEST 1: low_ivol SOLO + correlation with A2-style low-vol proxy
    # =====================================================================
    section_header("TEST 1: low_ivol SOLO vs A2-style low-vol proxy")

    # low_ivol solo strategy
    w_ivol = weights_from_rank(signals["low_ivol"], top_frac=0.10,
                                rebalance_days=REBALANCE_DAYS, overlay_mult=overlay)
    ret_ivol = run(w_ivol, prices)

    # A2-style low-vol PROXY: rank stocks by trailing 63d realized vol, long
    # bottom decile. This is the LowVolatility strategy's core signal.
    stock_ret = prices.pct_change()
    realized_vol = stock_ret.rolling(63, min_periods=32).std() * np.sqrt(252)
    a2_vol_rank = _to_rank(realized_vol, ascending=True)  # low vol = rank 1.0
    w_a2proxy = weights_from_rank(a2_vol_rank, top_frac=0.10,
                                    rebalance_days=REBALANCE_DAYS, overlay_mult=overlay)
    ret_a2proxy = run(w_a2proxy, prices)

    print("\n  Standalone performance:")
    for label, window in [("Full 2010-2026", ("2010-01-01", OOS_END)),
                           ("IS 2010-2022", ("2010-01-01", IS_END)),
                           ("OOS 2023-2026", (OOS_START, OOS_END)),
                           ("Post-2020 (exclude COVID)", (POST_2020, OOS_END))]:
        lo, hi = window
        print_row(stats(ret_ivol.loc[lo:hi], f"low_ivol | {label}"))
        print_row(stats(ret_a2proxy.loc[lo:hi], f"A2 low-vol proxy | {label}"))
        print()

    aligned = pd.concat({"low_ivol": ret_ivol, "a2_proxy": ret_a2proxy},
                        axis=1).dropna()
    corr_full = aligned["low_ivol"].corr(aligned["a2_proxy"])
    corr_oos = (aligned.loc[OOS_START:OOS_END]["low_ivol"]
                .corr(aligned.loc[OOS_START:OOS_END]["a2_proxy"]))
    print(f"  Correlation (full):  {corr_full:+.3f}")
    print(f"  Correlation (OOS):   {corr_oos:+.3f}")
    print(f"  Gate: < 0.60 → viable standalone | ≥ 0.60 → factor-duplicative with A2")
    print(f"  Verdict on duplication: "
          f"{'DUPLICATIVE' if abs(corr_full) >= 0.60 else 'distinct enough'}")

    # =====================================================================
    # TEST 2: A1-OVERLAY — combine A1 momentum rank with RenTech ranks
    # =====================================================================
    section_header("TEST 2: A1-OVERLAY — momentum rank + 5 RenTech ranks")

    # Baseline: A1 pure momentum top-15
    w_a1_pure = weights_from_rank(momentum_rank, top_n=15,
                                   rebalance_days=REBALANCE_DAYS, overlay_mult=overlay)
    ret_a1_pure = run(w_a1_pure, prices)

    # Overlay: combine momentum with the 5 RenTech signals
    combined_signals = dict(signals)
    combined_signals["momentum"] = momentum_rank
    overlay_rank = combine_ranks(combined_signals)
    w_a1_overlay = weights_from_rank(overlay_rank, top_n=15,
                                      rebalance_days=REBALANCE_DAYS, overlay_mult=overlay)
    ret_a1_overlay = run(w_a1_overlay, prices)

    # Alternative: momentum gets 50% weight, 5 RenTech share the other 50%
    # (Prevents the 5 weak signals from drowning A1's established edge.)
    w_mom = 0.50
    w_others = 0.50 / 5
    signal_means = {name: df for name, df in combined_signals.items()}
    rank_sum = momentum_rank.fillna(0) * w_mom + momentum_rank.notna().astype(float) * 0
    count_sum = momentum_rank.notna().astype(float) * w_mom
    for name, df in signals.items():  # non-momentum ones
        rank_sum = rank_sum.add(df.fillna(0) * w_others, fill_value=0)
        count_sum = count_sum.add(df.notna().astype(float) * w_others, fill_value=0)
    weighted_overlay_rank = rank_sum / count_sum.replace(0, np.nan)
    w_a1_weighted = weights_from_rank(weighted_overlay_rank, top_n=15,
                                       rebalance_days=REBALANCE_DAYS, overlay_mult=overlay)
    ret_a1_weighted = run(w_a1_weighted, prices)

    print("\n  Comparison (all use top-15, monthly, SPY filter + TOM, 5 bps):")
    print()
    for label, window in [("Full 2010-2026", ("2010-01-01", OOS_END)),
                           ("IS 2010-2022", ("2010-01-01", IS_END)),
                           ("OOS 2023-2026", (OOS_START, OOS_END)),
                           ("Post-2020", (POST_2020, OOS_END))]:
        lo, hi = window
        print(f"  [{label}]")
        print_row(stats(ret_a1_pure.loc[lo:hi], "A1 pure momentum"))
        print_row(stats(ret_a1_overlay.loc[lo:hi], "A1 + RenTech (equal-weight)"))
        print_row(stats(ret_a1_weighted.loc[lo:hi], "A1 + RenTech (50/50 split)"))
        print()

    # =====================================================================
    # TEST 3: SIGNAL-AGREEMENT ENSEMBLE
    # =====================================================================
    section_header("TEST 3: SIGNAL-AGREEMENT ensemble (≥K of N in top-30%)")

    # For each signal, mark stocks in top-30% as 1.0 (agreement vote)
    top30 = {}
    for name, df in signals.items():
        top30[name] = (df >= 0.70).astype(float)
    # Sum agreement votes per (date, ticker)
    vote_sum = sum(top30.values())
    # Rank: more agreement = higher rank
    # For weights, take top decile by vote count, equal-weight
    # First: require at least K=3 of 5 agreement to be eligible
    for K in [2, 3, 4]:
        eligible = (vote_sum >= K).astype(float)
        # Among eligible, equal-weight (no further ranking needed)
        n_eligible = eligible.sum(axis=1).replace(0, 1)
        w_agreement = eligible.div(n_eligible, axis=0)
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = w_agreement.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[::REBALANCE_DAYS]
            rebalance_mask.loc[rebalance_dates] = True
        w_agreement[~rebalance_mask] = np.nan
        w_agreement = w_agreement.ffill().fillna(0)
        # Apply overlay
        w_agreement = w_agreement.mul(overlay.reindex(w_agreement.index).ffill().fillna(1.0),
                                      axis=0)
        ret_agree = run(w_agreement, prices)

        avg_n_picks = (eligible.sum(axis=1).loc[valid_idx]).mean()
        print(f"\n  K={K} (at least {K} of 5 signals agree top-30%) — "
              f"avg {avg_n_picks:.0f} picks/day")
        for label, window in [("Full", ("2010-01-01", OOS_END)),
                               ("IS", ("2010-01-01", IS_END)),
                               ("OOS", (OOS_START, OOS_END)),
                               ("Post-2020", (POST_2020, OOS_END))]:
            lo, hi = window
            print_row(stats(ret_agree.loc[lo:hi], f"K={K} | {label}"))

    # =====================================================================
    # SYNTHESIS
    # =====================================================================
    section_header("SYNTHESIS")

    print("""
  Gate: OOS CAGR ≥ 15%, Calmar ≥ 1.2, OOS/IS ≥ 70%

  Test 1 (low_ivol solo):
    - If duplicative with A2 AND fails gate → dead
    - If distinct-enough OR passes gate → keep as A5 candidate
  Test 2 (A1 overlay):
    - If overlay OOS CAGR > A1 pure OOS CAGR by ≥2pp → genuine improvement
    - Otherwise → overlay dilutes, kill
  Test 3 (signal-agreement):
    - If any K value clears OOS 15% CAGR AND Calmar ≥ 1.2 → keep
    - Otherwise → ensemble philosophy dead on our signals
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
