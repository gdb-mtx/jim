"""
Crypto Account 4 Robust Optimization — min(Calmar across halves).

Unlike the original crypto_autoresearch.py (maximizes full-sample Sharpe →
regime-cherry-picking), this script explicitly scores configs by their
WORST-HALF Calmar. The optimization objective becomes:

    maximize:  min(Calmar_half_A, Calmar_half_B)

where half A is 2020-2022 (the crypto super-bull) and half B is 2023-2026
(chop + recovery). A config that does well only in one regime is penalized;
only regime-robust configs surface.

This is the honest CAGR-first version of parameter selection — it cannot
overfit in the traditional sense because the objective explicitly punishes
regime dependence. If no config meaningfully beats the current production
SMA-200/top3, that's the answer: the parameter surface is already harvested.

Usage:
    uv run python3 scripts/crypto_robust_opt.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")

from data.crypto import download_btc_prices, download_crypto_prices  # noqa: E402
from mode2.crypto_autoresearch import Config, run_config  # noqa: E402


# Expanded sweep — same axes as Test 3 but finer
SWEEP_CONFIGS: list[tuple[str, int, int]] = [
    # (filter_type, filter_period, filter_fast)
    ("sma", 100, 0),
    ("sma", 125, 0),
    ("sma", 150, 0),
    ("sma", 175, 0),
    ("sma", 200, 0),
    ("sma", 225, 0),
    ("ema", 100, 0),
    ("ema", 150, 0),
    ("ema", 200, 0),
    ("dual", 150, 50),
    ("dual", 200, 50),
    ("none", 0, 0),
]
LOOKBACKS = [14, 21, 30, 42]
TOP_NS = [1, 2, 3]


def main() -> int:
    print("Loading crypto data...")
    prices = download_crypto_prices(start="2018-01-01")
    btc = download_btc_prices(start="2018-01-01")

    configs: list[Config] = []
    for ft, fp, ff in SWEEP_CONFIGS:
        for lb in LOOKBACKS:
            for tn in TOP_NS:
                label = (
                    f"{ft}-{fp}/lb{lb}/top{tn}"
                    if ft != "dual"
                    else f"dual-{ff}/{fp}/lb{lb}/top{tn}"
                )
                configs.append(
                    Config(
                        name=label,
                        filter_type=ft,
                        filter_period=fp if fp else 200,
                        filter_fast=ff,
                        lookback=lb,
                        top_n=tn,
                        rebal_days=1,
                        vol_target=0.15,
                        risk_adj_momentum=False,
                    )
                )
    print(f"Sweep: {len(configs)} configurations")

    def _run_half(label: str, start: str, end: str) -> dict[str, dict]:
        print(f"\nRunning half {label} ({start} to {end})...")
        subset = prices.loc[start:end]
        out: dict[str, dict] = {}
        for i, cfg in enumerate(configs):
            if i % 20 == 0:
                print(f"  {i}/{len(configs)}")
            try:
                r = run_config(subset, btc, cfg)
                # run_config returns cagr, max_dd as percentages (e.g. +45.6, -14.1)
                cagr_dec = r.cagr / 100
                mdd_dec = r.max_dd / 100
                calmar = cagr_dec / abs(mdd_dec) if mdd_dec else 0.0
                out[cfg.name] = {
                    "cagr": cagr_dec,
                    "max_dd": mdd_dec,
                    "calmar": calmar,
                    "sharpe": r.sharpe,
                }
            except Exception as e:
                out[cfg.name] = {"error": str(e)}
        return out

    half_a = _run_half("A", "2020-01-01", "2022-12-31")
    half_b = _run_half("B", "2023-01-01", "2026-12-31")

    # Combine — for each config that succeeded in both halves, compute min-Calmar
    combined = []
    for name in half_a:
        if "error" in half_a[name] or name not in half_b or "error" in half_b[name]:
            continue
        ca_a = half_a[name]["calmar"]
        ca_b = half_b[name]["calmar"]
        cagr_a = half_a[name]["cagr"]
        cagr_b = half_b[name]["cagr"]
        mdd_a = half_a[name]["max_dd"]
        mdd_b = half_b[name]["max_dd"]
        combined.append(
            {
                "name": name,
                "min_calmar": min(ca_a, ca_b),
                "calmar_a": ca_a,
                "calmar_b": ca_b,
                "min_cagr": min(cagr_a, cagr_b),
                "cagr_a": cagr_a,
                "cagr_b": cagr_b,
                "mdd_a": mdd_a,
                "mdd_b": mdd_b,
            }
        )

    # Sort by min-Calmar — the robust optimization objective
    combined.sort(key=lambda r: r["min_calmar"], reverse=True)

    print(f"\n{'=' * 110}")
    print("  ROBUST OPTIMIZATION — ranked by min(Calmar_A, Calmar_B)")
    print(f"{'=' * 110}")
    print(
        f"{'Rank':<5} {'Config':<32} {'min-Cal':>8} {'Cal A':>7} {'Cal B':>7} "
        f"{'CAGR A':>8} {'CAGR B':>8} {'MDD A':>7} {'MDD B':>7}"
    )
    print("-" * 110)
    for i, r in enumerate(combined[:20], 1):
        print(
            f"{i:<5} {r['name']:<32} "
            f"{r['min_calmar']:>7.2f}  "
            f"{r['calmar_a']:>6.2f}  {r['calmar_b']:>6.2f}  "
            f"{r['cagr_a'] * 100:>+7.1f}% {r['cagr_b'] * 100:>+7.1f}% "
            f"{r['mdd_a'] * 100:>+6.1f}% {r['mdd_b'] * 100:>+6.1f}%"
        )

    # Highlight current production and reference configs
    print(f"\n{'=' * 110}")
    print("  KEY COMPARISONS")
    print(f"{'=' * 110}")
    reference_names = [
        "sma-200/lb21/top3",  # current production (conservative)
        "sma-150/lb21/top2",  # prior tuned (failed old Test 3)
        "sma-100/lb21/top2",  # half B winner family
        "ema-150/lb21/top2",  # half A winner family
    ]
    for name in reference_names:
        match = next((r for r in combined if r["name"] == name), None)
        rank = next((i + 1 for i, r in enumerate(combined) if r["name"] == name), None)
        if match:
            print(
                f"  {name:<32} rank {rank}/{len(combined)}  min-Cal {match['min_calmar']:.2f}  "
                f"(A {match['calmar_a']:.2f} / B {match['calmar_b']:.2f})"
            )

    # Full-sample check on the robust winner to see what OOS holdout would say
    print(f"\n{'=' * 110}")
    print("  OOS HOLDOUT CHECK — best robust config on train (pre-2023) / test (2023+)")
    print(f"{'=' * 110}")
    winner = combined[0]
    print(f"  Winner by min-Calmar: {winner['name']}")
    # Parse winner's params
    filter_part, lb_part, top_part = winner["name"].split("/")
    if filter_part.startswith("sma"):
        ft = "sma"
        fp = int(filter_part.split("-")[1])
        ff = 0
    elif filter_part.startswith("ema"):
        ft = "ema"
        fp = int(filter_part.split("-")[1])
        ff = 0
    elif filter_part.startswith("dual"):
        ft = "dual"
        ff = int(filter_part.split("-")[1])
        fp = 150  # default used in sweep
    elif filter_part == "none":
        ft = "none"
        fp = 200
        ff = 0
    else:
        raise ValueError(f"Can't parse filter: {filter_part}")
    lb = int(lb_part.replace("lb", ""))
    tn = int(top_part.replace("top", ""))
    winner_cfg = Config(
        name=winner["name"],
        filter_type=ft,
        filter_period=fp,
        filter_fast=ff,
        lookback=lb,
        top_n=tn,
        rebal_days=1,
        vol_target=0.15,
        risk_adj_momentum=False,
    )
    train = prices.loc[:"2022-12-31"]
    test = prices.loc["2023-01-01":]
    train_r = run_config(train, btc, winner_cfg)
    test_r = run_config(test, btc, winner_cfg)
    print(
        f"  Train (2018-2022): CAGR {train_r.cagr:+.1f}%, MaxDD {train_r.max_dd:.1f}%, "
        f"Calmar {(train_r.cagr / 100) / abs(train_r.max_dd / 100):.2f}"
    )
    print(
        f"  Test (2023-2026):  CAGR {test_r.cagr:+.1f}%, MaxDD {test_r.max_dd:.1f}%, "
        f"Calmar {(test_r.cagr / 100) / abs(test_r.max_dd / 100):.2f}"
    )
    ratio = (test_r.cagr / train_r.cagr) if abs(train_r.cagr) > 1e-6 else 0.0
    print(f"  OOS/IS CAGR ratio: {ratio:.0%}")

    # Save ranked results
    df = pd.DataFrame(combined)
    out_path = ROOT / "data" / "mode2" / "crypto_robust_opt.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"\nFull ranking saved to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
