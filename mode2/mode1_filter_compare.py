"""
Breakthrough #1 final step — compare Portfolio M (momentum) vs Portfolio C (Claude).

Both portfolios select top-15 from the top-30 momentum pool for each rebalance date,
restricted to symbols with transcript scores. Equal weight, hold 30 calendar days.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    universes = pd.read_parquet("data/mode2/mode1_filter/candidate_universes.parquet")
    scores = json.load(open("data/mode2/mode1_filter/scores_all.json"))
    prices = pd.read_parquet("data/raw/sp500_prices.parquet")

    # SPY benchmark
    spy_prices = prices["SPY"] if "SPY" in prices.columns else None
    if spy_prices is None:
        import yfinance as yf
        spy_prices = yf.download("SPY", start="2025-01-01", auto_adjust=True, progress=False)["Close"]
        if isinstance(spy_prices, pd.DataFrame):
            spy_prices = spy_prices.iloc[:, 0]

    def spy_fwd(start, days=30):
        idx = spy_prices.index
        if start not in idx:
            start = idx[idx.get_indexer([start], method="pad")[0]]
        end_t = start + pd.Timedelta(days=days)
        if end_t > idx.max():
            return None
        end = idx[idx.get_indexer([end_t], method="pad")[0]]
        return float(spy_prices.loc[end] / spy_prices.loc[start] - 1)

    rebalance_dates = sorted(universes["rebalance_date"].unique())

    results = []
    per_date_detail = []

    for date_str in rebalance_dates:
        grp = universes[universes["rebalance_date"] == date_str].copy()
        if not grp["has_forward_data"].all():
            print(f"{date_str}: skipping — no 30d forward data yet")
            continue

        # Attach score, drop symbols without transcript
        grp["score"] = grp["symbol"].map(scores)
        grp_scored = grp.dropna(subset=["score"]).copy()
        n_dropped = len(grp) - len(grp_scored)

        # Sort by momentum rank ascending (rank 1 = best momentum)
        grp_scored = grp_scored.sort_values("rank")

        # Portfolio M: top-15 by momentum rank (from scored subset)
        port_m = grp_scored.head(15).copy()

        # Portfolio C: top-15 by score desc, ties broken by rank asc
        grp_by_score = grp_scored.sort_values(["score", "rank"], ascending=[False, True])
        port_c = grp_by_score.head(15).copy()

        m_ret = port_m["fwd_30d_return"].mean()
        c_ret = port_c["fwd_30d_return"].mean()
        spy_ret = spy_fwd(pd.Timestamp(date_str))

        # Identify what C added / dropped vs M
        m_set = set(port_m["symbol"])
        c_set = set(port_c["symbol"])
        added = sorted(c_set - m_set)
        dropped = sorted(m_set - c_set)

        results.append({
            "date": date_str,
            "n_scored": len(grp_scored),
            "n_dropped_no_transcript": n_dropped,
            "port_m_30d": m_ret,
            "port_c_30d": c_ret,
            "excess_c_vs_m": c_ret - m_ret,
            "spy_30d": spy_ret,
            "port_m_vs_spy": m_ret - spy_ret,
            "port_c_vs_spy": c_ret - spy_ret,
            "added_by_claude": added,
            "dropped_by_claude": dropped,
        })

        # Per-date detail for deep dive
        for _, row in grp_scored.iterrows():
            per_date_detail.append({
                "date": date_str,
                "symbol": row["symbol"],
                "momentum_rank": row["rank"],
                "momentum": row["momentum"],
                "claude_score": row["score"],
                "in_port_m": row["symbol"] in m_set,
                "in_port_c": row["symbol"] in c_set,
                "fwd_30d_return": row["fwd_30d_return"],
            })

    # Summary
    df = pd.DataFrame(results)
    print("\n=== BREAKTHROUGH #1 TEST RESULTS ===\n")
    print("Per-date:")
    for _, r in df.iterrows():
        print(f"  {r['date']}  |  M: {r['port_m_30d']:+.2%}  C: {r['port_c_30d']:+.2%}  "
              f"excess: {r['excess_c_vs_m']:+.2%}  (SPY: {r['spy_30d']:+.2%})")
        print(f"              Claude added: {r['added_by_claude']}")
        print(f"              Claude dropped: {r['dropped_by_claude']}")

    avg_m = df["port_m_30d"].mean()
    avg_c = df["port_c_30d"].mean()
    avg_excess = df["excess_c_vs_m"].mean()

    print(f"\nAVERAGES across {len(df)} months:")
    print(f"  Portfolio M (top-15 momentum):     {avg_m:+.2%}/month")
    print(f"  Portfolio C (top-15 Claude):       {avg_c:+.2%}/month")
    print(f"  SPY:                                {df['spy_30d'].mean():+.2%}/month")
    print(f"  Excess (C - M):                    {avg_excess:+.2%}/month")

    # Decision
    print(f"\nDECISION (from BREAKTHROUGH.md):")
    if avg_excess >= 0.015:
        print(f"  BUILD filter layer. C-M = {avg_excess:+.2%} meets >=1.5% threshold.")
    elif avg_excess >= 0.005:
        print(f"  3-month paper trial. C-M = {avg_excess:+.2%} in 0.5-1.5% band.")
    else:
        print(f"  KILL Mode 2 filter thesis. C-M = {avg_excess:+.2%} below 0.5% threshold.")

    # Score-return relationship
    det = pd.DataFrame(per_date_detail)
    det_complete = det.dropna(subset=["fwd_30d_return"])
    print(f"\nSCORE -> 30d RETURN (all scored (symbol, date) pairs):")
    by_score = det_complete.groupby("claude_score").agg(
        n=("fwd_30d_return", "size"),
        mean_ret=("fwd_30d_return", "mean"),
        median_ret=("fwd_30d_return", "median"),
    )
    print(by_score.to_string())

    corr = det_complete[["claude_score", "fwd_30d_return"]].corr().iloc[0, 1]
    print(f"\n  Correlation(score, 30d_return) = {corr:+.3f}")

    # Hit rate for 5/5 conviction names
    score5 = det_complete[det_complete["claude_score"] == 5]
    if len(score5) > 0:
        hit_rate = (score5["fwd_30d_return"] > 0).mean()
        print(f"  5/5 names positive 30d: {hit_rate:.0%} ({len(score5)} names)")

    # Save
    out = Path("data/mode2/mode1_filter/results.json")
    out.write_text(json.dumps({
        "per_date": results,
        "summary": {
            "avg_port_m_30d": avg_m,
            "avg_port_c_30d": avg_c,
            "avg_excess": avg_excess,
            "avg_spy_30d": float(df["spy_30d"].mean()),
            "score_return_correlation": float(corr),
            "n_months": len(df),
        },
    }, indent=2, default=str))
    det.to_parquet("data/mode2/mode1_filter/per_symbol_detail.parquet")
    print(f"\nSaved: {out}")
    print(f"Saved: data/mode2/mode1_filter/per_symbol_detail.parquet")


if __name__ == "__main__":
    main()
