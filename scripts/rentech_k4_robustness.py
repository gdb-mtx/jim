"""
K=4 signal-agreement ensemble — robustness tests.

Previous followup (scripts/rentech_followup_tests.py) surfaced that the
equal-weight ensemble fails but the signal-AGREEMENT ensemble (require K of 5
signals to agree top-30%) clears OOS gates at K=4 with 26.0% CAGR / Calmar 1.35 /
OOS-over-IS ratio 131%. Before we call this a legitimate A5 candidate, stress
it on four axes:

  A. Yearly / half-year breakdown — is one window carrying the result?
  B. Parameter sensitivity — does K=4 survive variation in top-X% threshold,
     hold period, and K itself (K=5 full consensus)?
  C. Correlation vs A1 (momentum) and A2 low-vol proxy — is this actually
     orthogonal or are we re-picking the same names as existing accounts?
  D. Comparison to K=5 full consensus — is 4/5 the sweet spot?

If K=4 holds up across all four tests, proceed to full 6-test VALIDATION.
If it fails any, narrow to what specifically is real.

Usage:
    uv run python3 scripts/rentech_k4_robustness.py
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
    _to_rank,
    low_ivol,
    near_52wh,
    price_acceleration,
    short_reversal,
    spy_trend_filter,
    trend_quality,
    turn_of_month_boost,
)


IS_END = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END = "2026-04-20"
POST_2020 = "2021-01-01"
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


def stats(net: pd.Series) -> dict:
    r = net.dropna()
    if len(r) == 0:
        return {"bars": 0, "cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "calmar": np.nan}
    cagr = (1 + r).prod() ** (PERIODS_PER_YEAR / len(r)) - 1
    sharpe = (r.mean() / r.std()) * np.sqrt(PERIODS_PER_YEAR) if r.std() > 0 else 0.0
    cum = (1 + r).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(maxdd) if maxdd else 0.0
    return {"bars": len(r), "cagr": cagr, "sharpe": sharpe, "maxdd": maxdd, "calmar": calmar}


def signal_agreement_weights(
    signals: dict[str, pd.DataFrame],
    K: int,
    top_pct: float,
    rebalance_days: int,
    overlay_mult: pd.Series,
) -> pd.DataFrame:
    """Require K of N signals to agree a stock is in top_pct. Equal-weight among eligibles."""
    threshold = 1 - top_pct
    top_votes = [(df >= threshold).astype(float) for df in signals.values()]
    vote_sum = sum(top_votes)
    eligible = (vote_sum >= K).astype(float)
    n_eligible = eligible.sum(axis=1).replace(0, 1)
    w = eligible.div(n_eligible, axis=0)

    rebalance_mask = pd.Series(False, index=w.index)
    valid_idx = w.dropna(how="all").index
    if len(valid_idx) > 0:
        rebalance_mask.loc[valid_idx[::rebalance_days]] = True
    w[~rebalance_mask] = np.nan
    w = w.ffill().fillna(0)
    w = w.mul(overlay_mult.reindex(w.index).ffill().fillna(1.0), axis=0)
    return w


def run_weights(weights: pd.DataFrame, prices: pd.DataFrame) -> pd.Series:
    price_ret = prices.pct_change().fillna(0)
    gross = (price_ret * weights.shift(1)).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(0)
    cost = turnover * (COST_BPS_ROUNDTRIP / 10_000.0 / 2)
    return gross - cost


def a1_momentum_rank(prices: pd.DataFrame) -> pd.DataFrame:
    lagged = prices.shift(21)
    older = prices.shift(189)
    mom = (lagged - older) / older
    return _to_rank(mom, ascending=False)


def a2_lowvol_rank(prices: pd.DataFrame) -> pd.DataFrame:
    ret = prices.pct_change()
    realized = ret.rolling(63, min_periods=32).std() * np.sqrt(252)
    return _to_rank(realized, ascending=True)


def weights_from_rank_topn(
    rank_df: pd.DataFrame, top_n: int, rebalance_days: int,
    overlay_mult: pd.Series
) -> pd.DataFrame:
    ranks_desc = rank_df.rank(axis=1, ascending=False, method="average")
    selected = (ranks_desc <= top_n).astype(float)
    n_sel = selected.sum(axis=1).replace(0, 1)
    w = selected.div(n_sel, axis=0)
    rebalance_mask = pd.Series(False, index=rank_df.index)
    valid_idx = w.dropna(how="all").index
    if len(valid_idx) > 0:
        rebalance_mask.loc[valid_idx[::rebalance_days]] = True
    w[~rebalance_mask] = np.nan
    w = w.ffill().fillna(0)
    w = w.mul(overlay_mult.reindex(w.index).ffill().fillna(1.0), axis=0)
    return w


def weights_from_rank_topfrac(
    rank_df: pd.DataFrame, top_frac: float, rebalance_days: int,
    overlay_mult: pd.Series
) -> pd.DataFrame:
    threshold = 1 - top_frac
    selected = (rank_df >= threshold).astype(float)
    n_sel = selected.sum(axis=1).replace(0, 1)
    w = selected.div(n_sel, axis=0)
    rebalance_mask = pd.Series(False, index=rank_df.index)
    valid_idx = w.dropna(how="all").index
    if len(valid_idx) > 0:
        rebalance_mask.loc[valid_idx[::rebalance_days]] = True
    w[~rebalance_mask] = np.nan
    w = w.ffill().fillna(0)
    w = w.mul(overlay_mult.reindex(w.index).ffill().fillna(1.0), axis=0)
    return w


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}")


def main() -> int:
    print("Loading data + computing signals...")
    prices = download_sp500_prices(start="2010-01-01")
    spy = _load_spy().reindex(prices.index).ffill()
    signals = {
        "short_reversal":     short_reversal(prices, lookback=5),
        "near_52wh":          near_52wh(prices, lookback=252),
        "low_ivol":           low_ivol(prices, spy, lookback=63),
        "trend_quality":      trend_quality(prices, lookback=63),
        "price_acceleration": price_acceleration(prices, short=5, long=21),
    }
    spy_f = spy_trend_filter(spy, ma_period=200)
    tom = turn_of_month_boost(prices.index)
    overlay = spy_f.reindex(prices.index).ffill() * tom.reindex(prices.index).ffill()

    # Baseline K=4, top-30%, 21d hold
    w_k4 = signal_agreement_weights(signals, K=4, top_pct=0.30, rebalance_days=21, overlay_mult=overlay)
    ret_k4 = run_weights(w_k4, prices)

    # ============================================================
    # SECTION A: YEARLY + HALF-YEAR BREAKDOWN
    # ============================================================
    section("A. YEARLY + HALF-YEAR RETURN BREAKDOWN (K=4, top-30%, 21d hold)")
    yearly = ret_k4.groupby(ret_k4.index.year).apply(lambda s: (1 + s).prod() - 1)
    years_maxdd = ret_k4.groupby(ret_k4.index.year).apply(
        lambda s: ((1 + s).cumprod() / (1 + s).cumprod().cummax() - 1).min()
    )
    print(f"  {'Year':<6} {'Return':>10} {'MaxDD':>10}")
    for y in yearly.index:
        print(f"  {y:<6} {yearly[y]:>+10.1%} {years_maxdd[y]:>+10.1%}")

    # Half-year split for 2023-2026 OOS
    oos_r = ret_k4.loc[OOS_START:OOS_END]
    print("\n  OOS half-year breakdown:")
    for lo, hi, label in [
        ("2023-01-01", "2023-06-30", "2023 H1"),
        ("2023-07-01", "2023-12-31", "2023 H2"),
        ("2024-01-01", "2024-06-30", "2024 H1"),
        ("2024-07-01", "2024-12-31", "2024 H2"),
        ("2025-01-01", "2025-06-30", "2025 H1"),
        ("2025-07-01", "2025-12-31", "2025 H2"),
        ("2026-01-01", OOS_END,      "2026 YTD"),
    ]:
        s = ret_k4.loc[lo:hi]
        if len(s) > 5:
            ret_total = (1 + s).prod() - 1
            print(f"    {label}  {ret_total:+7.1%}  ({len(s)} bars)")

    # ============================================================
    # SECTION B: PARAMETER SENSITIVITY GRID
    # ============================================================
    section("B. PARAMETER SENSITIVITY — K × top_pct × hold_days")

    print(f"  {'Config':<32} {'Full CAGR':>10} {'OOS CAGR':>10} {'OOS Calmar':>11} {'OOS/IS':>8} {'OOS MaxDD':>10}")
    print("  " + "-" * 82)

    def run_config_grid() -> list:
        results = []
        for K in [3, 4, 5]:
            for top_pct in [0.20, 0.25, 0.30, 0.35]:
                for hold in [10, 21, 42]:
                    w = signal_agreement_weights(signals, K, top_pct, hold, overlay)
                    r = run_weights(w, prices)
                    full = stats(r)
                    is_s = stats(r.loc[:IS_END])
                    oos = stats(r.loc[OOS_START:OOS_END])
                    ratio = oos["cagr"] / is_s["cagr"] if is_s["cagr"] > 1e-6 else 0.0
                    avg_picks = ((((pd.concat([(df >= 1 - top_pct).astype(float) for df in signals.values()]).groupby(level=0).sum()) >= K).astype(float)).sum(axis=1)).mean()  # informational, not used
                    results.append({
                        "K": K, "top_pct": top_pct, "hold": hold,
                        "full_cagr": full["cagr"], "oos_cagr": oos["cagr"],
                        "oos_calmar": oos["calmar"], "oos_ratio": ratio,
                        "oos_maxdd": oos["maxdd"],
                    })
                    tag = f"K={K}, top{int(top_pct*100)}%, hold{hold}d"
                    print(f"  {tag:<32} {full['cagr']:>+9.1%}  {oos['cagr']:>+9.1%}  "
                          f"{oos['calmar']:>10.2f}  {ratio:>7.0%}  {oos['maxdd']:>+9.1%}")
        return results

    grid_results = run_config_grid()

    # Count passes
    gate_passes = [
        r for r in grid_results
        if r["oos_cagr"] >= 0.15 and r["oos_calmar"] >= 1.20 and r["oos_ratio"] >= 0.70
    ]
    print(f"\n  Configs passing ALL OOS gates (≥15% CAGR, ≥1.2 Calmar, ≥70% ratio): "
          f"{len(gate_passes)}/{len(grid_results)}")
    if gate_passes:
        best = max(gate_passes, key=lambda r: r["oos_calmar"])
        print(f"  Best by OOS Calmar: K={best['K']}, top={int(best['top_pct']*100)}%, "
              f"hold={best['hold']}d → Calmar {best['oos_calmar']:.2f}, "
              f"CAGR {best['oos_cagr']:+.1%}")

    # ============================================================
    # SECTION C: CORRELATION vs A1 momentum + A2 low-vol proxy
    # ============================================================
    section("C. CORRELATION: K=4 vs A1 momentum + A2 low-vol proxy")

    # A1 proxy: 9mo momentum, top-15, monthly, same overlay
    a1_rank = a1_momentum_rank(prices)
    w_a1 = weights_from_rank_topn(a1_rank, top_n=15, rebalance_days=21, overlay_mult=overlay)
    ret_a1 = run_weights(w_a1, prices)

    # A2 low-vol proxy: top decile, monthly, same overlay
    a2_rank = a2_lowvol_rank(prices)
    w_a2 = weights_from_rank_topfrac(a2_rank, top_frac=0.10, rebalance_days=21, overlay_mult=overlay)
    ret_a2 = run_weights(w_a2, prices)

    aligned = pd.concat({"K4": ret_k4, "A1": ret_a1, "A2": ret_a2}, axis=1).dropna()
    print(f"\n  Correlation on {len(aligned)} common daily-return bars:")
    print(f"    K=4 ↔ A1 (momentum):    {aligned['K4'].corr(aligned['A1']):+.3f}")
    print(f"    K=4 ↔ A2 (low-vol):     {aligned['K4'].corr(aligned['A2']):+.3f}")
    print(f"    A1  ↔ A2  (control):    {aligned['A1'].corr(aligned['A2']):+.3f}")

    oos_aligned = aligned.loc[OOS_START:OOS_END]
    print(f"\n  OOS-only correlation ({len(oos_aligned)} bars):")
    print(f"    K=4 ↔ A1 (momentum):    {oos_aligned['K4'].corr(oos_aligned['A1']):+.3f}")
    print(f"    K=4 ↔ A2 (low-vol):     {oos_aligned['K4'].corr(oos_aligned['A2']):+.3f}")

    # How much of K=4's picks overlap A1's top-15 and A2's top-decile?
    # Measure on each rebalance day: what fraction of K=4 picks are also in A1 top-15?
    def overlap_fraction(w1: pd.DataFrame, w2: pd.DataFrame) -> float:
        # On days both strategies are invested, what fraction of w1's holdings are also held by w2?
        both_invested = (w1.sum(axis=1) > 0) & (w2.sum(axis=1) > 0)
        if both_invested.sum() == 0:
            return np.nan
        w1_held = (w1 > 0).astype(float)
        w2_held = (w2 > 0).astype(float)
        overlap = (w1_held * w2_held).sum(axis=1) / w1_held.sum(axis=1).replace(0, np.nan)
        return overlap[both_invested].mean()

    print(f"\n  Holdings overlap (fraction of K=4 picks also held by other):")
    print(f"    K=4 picks also in A1 top-15:   {overlap_fraction(w_k4, w_a1):.1%}")
    print(f"    K=4 picks also in A2 top-10%:  {overlap_fraction(w_k4, w_a2):.1%}")

    # ============================================================
    # SECTION D: VERDICT
    # ============================================================
    section("D. VERDICT")
    baseline = next(r for r in grid_results if r["K"] == 4 and r["top_pct"] == 0.30 and r["hold"] == 21)
    print(f"\n  Baseline K=4, top-30%, hold-21d:")
    print(f"    OOS CAGR   {baseline['oos_cagr']:+.1%}")
    print(f"    OOS Calmar {baseline['oos_calmar']:.2f}")
    print(f"    OOS MaxDD  {baseline['oos_maxdd']:+.1%}")
    print(f"    OOS/IS     {baseline['oos_ratio']:.0%}")
    print()
    pass_count = sum([
        baseline['oos_cagr'] >= 0.15,
        baseline['oos_calmar'] >= 1.20,
        baseline['oos_ratio'] >= 0.70,
    ])
    print(f"  Gates cleared on baseline: {pass_count}/3")
    print(f"  Configs passing all gates in sensitivity grid: {len(gate_passes)}/{len(grid_results)}")
    print(f"  K=4 ↔ A1 correlation (OOS): {oos_aligned['K4'].corr(oos_aligned['A1']):+.3f}")
    print(f"  K=4 ↔ A2 correlation (OOS): {oos_aligned['K4'].corr(oos_aligned['A2']):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
