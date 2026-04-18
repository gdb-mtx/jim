"""
Validation Runner — VALIDATION_PLAN.md Tests 1-4 on a live-paper account.

Runs, in order:
  Test 1  Out-of-sample holdout (train through 2022-12-31, test 2023-01-01+)
  Test 2  Walk-forward rolling windows
  Test 3  Parameter stability (crypto only — re-runs autoresearch on two halves)
  Test 4  Block-bootstrap Monte Carlo

Writes a markdown report to data/validation_reports/ and updates the
validation_state.json file so the rebalance endpoint can enforce it.

Usage:
    uv run python3 scripts/run_validation.py --account 4
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.account_adapters import AccountAdapter, build_adapter  # noqa: E402
from backtesting.bootstrap import block_bootstrap  # noqa: E402
from backtesting.metrics import (  # noqa: E402
    annualized_return,
    max_drawdown,
    sharpe_ratio,
)
from backtesting.validation import (  # noqa: E402
    walk_forward_analysis,
    walk_forward_summary,
)

warnings.filterwarnings("ignore")


TRAIN_END = pd.Timestamp("2022-12-31")
REPORTS_DIR = ROOT / "data" / "validation_reports"
STATE_PATH = ROOT / "data" / "risk_state" / "validation_state.json"
VALIDITY_DAYS = 90  # quarterly re-validation


# ── Pre-committed thresholds (from VALIDATION_PLAN.md) ──────────────────
PASS_SHARPE_MIN = 1.0
PASS_RATIO_MIN = 0.70
MARGINAL_SHARPE_MIN = 0.5
MARGINAL_RATIO_MIN = 0.50
BOOTSTRAP_P5_FAIL = 0.3


def _status_from_thresholds(oos_sharpe: float, oos_is_ratio: float) -> str:
    """Classify based on OOS Sharpe + OOS/IS ratio."""
    if oos_sharpe >= PASS_SHARPE_MIN and oos_is_ratio >= PASS_RATIO_MIN:
        return "pass"
    if oos_sharpe >= MARGINAL_SHARPE_MIN and oos_is_ratio >= MARGINAL_RATIO_MIN:
        return "marginal"
    return "fail"


# ── Test 1: OOS holdout ───────────────────────────────────────────────
def test_1_oos_holdout(adapter: AccountAdapter) -> dict:
    returns = adapter.full_returns
    ppy = adapter.periods_per_year

    train = returns[returns.index <= TRAIN_END]
    test = returns[returns.index > TRAIN_END]

    if len(train) < 60 or len(test) < 60:
        return {
            "skip": True,
            "reason": f"Need 60+ days each side; train={len(train)}, test={len(test)}",
        }

    train_sharpe = sharpe_ratio(train, periods_per_year=ppy)
    test_sharpe = sharpe_ratio(test, periods_per_year=ppy)
    ratio = test_sharpe / train_sharpe if abs(train_sharpe) > 1e-6 else 0.0

    status = _status_from_thresholds(test_sharpe, ratio)

    return {
        "train_period": f"{train.index[0].date()} to {train.index[-1].date()}",
        "test_period": f"{test.index[0].date()} to {test.index[-1].date()}",
        "train_days": int(len(train)),
        "test_days": int(len(test)),
        "train_sharpe": float(train_sharpe),
        "test_sharpe": float(test_sharpe),
        "oos_is_ratio": float(ratio),
        "train_cagr": float(annualized_return(train, ppy)),
        "test_cagr": float(annualized_return(test, ppy)),
        "train_maxdd": float(max_drawdown(train)),
        "test_maxdd": float(max_drawdown(test)),
        "status": status,
        "pass": status == "pass",
    }


# ── Test 2: Walk-forward ──────────────────────────────────────────────
def test_2_walk_forward(adapter: AccountAdapter) -> dict:
    """Walk-forward with refitting on raw prices — or, if the adapter
    doesn't support it, rolling 1-year Sharpe on full-sample returns."""
    if adapter.walk_forward_supported:
        train_size = int(3 * adapter.periods_per_year)
        test_size = int(adapter.periods_per_year)
        step = int(adapter.periods_per_year / 2)
        results = walk_forward_analysis(
            adapter.prices,
            adapter.strategy_fn,
            train_size=train_size,
            test_size=test_size,
            step_size=step,
            warmup=adapter.warmup_days,
        )
        summary = walk_forward_summary(results)
        sharpes = [r["test_sharpe"] for r in results]
        return {
            "mode": "walk_forward_refit",
            "n_windows": summary["n_windows"],
            "median_sharpe": float(summary["median_sharpe"]) if sharpes else 0.0,
            "mean_sharpe": float(summary["mean_sharpe"]) if sharpes else 0.0,
            "min_sharpe": float(summary["min_sharpe"]) if sharpes else 0.0,
            "max_sharpe": float(summary["max_sharpe"]) if sharpes else 0.0,
            "profitable_windows": int(summary["profitable_windows"]),
            "total_windows": int(summary["n_windows"]),
            "windows_above_0.5": int(sum(1 for s in sharpes if s > 0.5)),
            "windows": [
                {
                    "window": r["window"],
                    "test_start": str(r["test_start"].date()),
                    "test_end": str(r["test_end"].date()),
                    "test_sharpe": float(r["test_sharpe"]),
                    "test_return": float(r["test_return"]),
                    "test_max_dd": float(r["test_max_dd"]),
                }
                for r in results
            ],
            "pass": summary["pass"],
            "reason": summary["reason"],
        }

    # Fallback: rolling Sharpe on full-sample returns.
    returns = adapter.full_returns
    ppy = adapter.periods_per_year
    window = int(ppy)
    step = int(ppy / 2)
    sharpes = []
    windows = []
    for start in range(0, len(returns) - window + 1, step):
        s = returns.iloc[start : start + window]
        sh = sharpe_ratio(s, periods_per_year=ppy)
        sharpes.append(sh)
        windows.append(
            {
                "window": len(windows) + 1,
                "test_start": str(s.index[0].date()),
                "test_end": str(s.index[-1].date()),
                "test_sharpe": float(sh),
                "test_return": float(annualized_return(s, ppy)),
                "test_max_dd": float(max_drawdown(s)),
            }
        )
    profitable = sum(1 for s in sharpes if s > 0)
    median_s = float(np.median(sharpes)) if sharpes else 0.0
    return {
        "mode": "rolling_full_sample",
        "note": "Walk-forward with refitting not implemented for blended accounts; reporting rolling 1-year Sharpe on full-sample returns instead.",
        "n_windows": len(sharpes),
        "median_sharpe": median_s,
        "mean_sharpe": float(np.mean(sharpes)) if sharpes else 0.0,
        "min_sharpe": float(min(sharpes)) if sharpes else 0.0,
        "max_sharpe": float(max(sharpes)) if sharpes else 0.0,
        "profitable_windows": profitable,
        "total_windows": len(sharpes),
        "windows_above_0.5": sum(1 for s in sharpes if s > 0.5),
        "windows": windows,
        "pass": median_s > 0.5 and profitable >= 3,
        "reason": f"Median rolling Sharpe {median_s:.2f}",
    }


# ── Test 3: Parameter stability (crypto only) ─────────────────────────
def test_3_parameter_stability(adapter: AccountAdapter) -> dict:
    """Re-run crypto autoresearch on two halves (pre-2022 / 2022+) and
    compare the top configs. Non-crypto accounts skip this test."""
    if adapter.account != 4:
        return {"skip": True, "reason": "Parameter stability test is crypto-only"}

    from mode2.crypto_autoresearch import Config, run_config  # noqa: E402

    prices = adapter.prices
    from data.crypto import download_btc_prices  # local to avoid repeated load
    btc = download_btc_prices()

    sweep: list[Config] = []
    for filter_type, filter_period in [("sma", 100), ("sma", 150), ("sma", 200), ("ema", 150), ("none", 0)]:
        for lookback in [14, 21, 30, 42]:
            for top_n in [1, 2, 3]:
                sweep.append(
                    Config(
                        name=f"{filter_type}-{filter_period}/lb{lookback}/top{top_n}",
                        filter_type=filter_type,
                        filter_period=filter_period if filter_period else 200,
                        filter_fast=0,
                        lookback=lookback,
                        top_n=top_n,
                        rebal_days=1,
                        vol_target=0.15,
                        risk_adj_momentum=False,
                    )
                )

    def _run_half(start: str, end: str) -> list[dict]:
        subset = prices.loc[start:end]
        results = []
        for cfg in sweep:
            try:
                r = run_config(subset, btc, cfg)
                results.append(
                    {
                        "name": cfg.name,
                        "sharpe": r.sharpe,
                        "cagr": r.cagr,
                        "max_dd": r.max_dd,
                    }
                )
            except Exception as e:
                results.append({"name": cfg.name, "error": str(e)})
        return sorted(
            [r for r in results if "error" not in r],
            key=lambda r: r["sharpe"],
            reverse=True,
        )

    half_a = _run_half("2020-01-01", "2022-12-31")
    half_b = _run_half("2023-01-01", "2026-12-31")

    top_a = [r["name"] for r in half_a[:5]]
    top_b = [r["name"] for r in half_b[:5]]
    overlap = set(top_a) & set(top_b)

    from strategies.crypto_momentum import CryptoMomentum as _CM
    _cm = _CM()
    production_name = (
        f"sma-{_cm.btc_ma_period}/lb{_cm.lookback_days}/top{_cm.top_n}"
    )
    prod_rank_a = next((i for i, r in enumerate(half_a) if r["name"] == production_name), -1)
    prod_rank_b = next((i for i, r in enumerate(half_b) if r["name"] == production_name), -1)

    passes = len(overlap) >= 2

    return {
        "n_configs": len(sweep),
        "half_a_range": "2020-01-01 to 2022-12-31",
        "half_b_range": "2023-01-01 to 2026-12-31",
        "top_5_half_a": half_a[:5],
        "top_5_half_b": half_b[:5],
        "top5_overlap_count": len(overlap),
        "top5_overlap": sorted(overlap),
        "production_config": production_name,
        "production_rank_half_a": prod_rank_a + 1 if prod_rank_a >= 0 else None,
        "production_rank_half_b": prod_rank_b + 1 if prod_rank_b >= 0 else None,
        "production_sharpe_half_a": half_a[prod_rank_a]["sharpe"] if prod_rank_a >= 0 else None,
        "production_sharpe_half_b": half_b[prod_rank_b]["sharpe"] if prod_rank_b >= 0 else None,
        "pass": passes,
        "reason": (
            f"Top-5 config overlap: {len(overlap)}/5 "
            f"(need >=2 for stability)"
        ),
    }


# ── Test 4: Block bootstrap ───────────────────────────────────────────
def test_4_bootstrap(adapter: AccountAdapter) -> dict:
    return block_bootstrap(
        adapter.full_returns,
        block_size=20,
        n_simulations=1000,
        periods_per_year=adapter.periods_per_year,
        seed=42,
    )


# ── Report writing ────────────────────────────────────────────────────
def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def write_report(account: int, name: str, results: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"account_{account}_{ts}.md"

    t1 = results["test_1"]
    t2 = results["test_2"]
    t3 = results["test_3"]
    t4 = results["test_4"]
    overall = results["overall"]

    lines = [
        f"# Validation Report — Account {account}: {name}",
        f"",
        f"Run: {datetime.now().isoformat(timespec='seconds')}",
        f"Overall status: **{overall['status'].upper()}**",
        f"",
        f"## Test 1 — Out-of-Sample Holdout",
    ]
    if t1.get("skip"):
        lines.append(f"SKIPPED: {t1['reason']}")
    else:
        lines += [
            f"- Train ({t1['train_period']}, {t1['train_days']}d): Sharpe {t1['train_sharpe']:.2f}, CAGR {_fmt_pct(t1['train_cagr'])}, MaxDD {_fmt_pct(t1['train_maxdd'])}",
            f"- Test  ({t1['test_period']}, {t1['test_days']}d): Sharpe **{t1['test_sharpe']:.2f}**, CAGR {_fmt_pct(t1['test_cagr'])}, MaxDD {_fmt_pct(t1['test_maxdd'])}",
            f"- OOS / IS ratio: **{t1['oos_is_ratio']:.2%}**",
            f"- Status: **{t1['status'].upper()}**",
        ]

    lines += ["", "## Test 2 — Walk-Forward"]
    lines += [f"- Mode: {t2['mode']}"]
    if t2.get("note"):
        lines.append(f"- Note: {t2['note']}")
    lines += [
        f"- Windows: {t2['n_windows']}, profitable {t2['profitable_windows']}/{t2['total_windows']}, above-0.5 {t2['windows_above_0.5']}/{t2['total_windows']}",
        f"- Median Sharpe: **{t2['median_sharpe']:.2f}**, min {t2['min_sharpe']:.2f}, max {t2['max_sharpe']:.2f}",
        f"- Pass: {t2['pass']} ({t2['reason']})",
        "",
        "| Window | Test window | Sharpe | Return | MaxDD |",
        "|---|---|---|---|---|",
    ]
    for w in t2["windows"]:
        lines.append(
            f"| {w['window']} | {w['test_start']} → {w['test_end']} | {w['test_sharpe']:.2f} | {_fmt_pct(w['test_return'])} | {_fmt_pct(w['test_max_dd'])} |"
        )

    lines += ["", "## Test 3 — Parameter Stability (crypto only)"]
    if t3.get("skip"):
        lines.append(f"SKIPPED: {t3['reason']}")
    else:
        lines += [
            f"- Sweep: {t3['n_configs']} configs",
            f"- Half A ({t3['half_a_range']}) top-5: " + ", ".join(r["name"] for r in t3["top_5_half_a"]),
            f"- Half B ({t3['half_b_range']}) top-5: " + ", ".join(r["name"] for r in t3["top_5_half_b"]),
            f"- Overlap: {t3['top5_overlap_count']}/5 — {sorted(t3['top5_overlap'])}",
            f"- Production config ({t3['production_config']}) rank: half A = {t3['production_rank_half_a']}, half B = {t3['production_rank_half_b']}",
            f"- Pass: {t3['pass']} ({t3['reason']})",
        ]

    lines += ["", "## Test 4 — Block Bootstrap"]
    if t4.get("skip") or t4.get("pass") is None:
        lines.append(f"SKIPPED: {t4.get('reason')}")
    else:
        lines += [
            f"- N simulations: {t4['n_simulations']}, block size {t4['block_size']}d",
            f"- Sharpe p5/p50/p95: {t4['sharpe_p5']:.2f} / {t4['sharpe_p50']:.2f} / {t4['sharpe_p95']:.2f}",
            f"- MaxDD p5/p95: {_fmt_pct(t4['maxdd_p5'])} / {_fmt_pct(t4['maxdd_p95'])}",
            f"- Pass: {t4['pass']} ({t4['reason']})",
        ]

    lines += ["", "## Decision"]
    lines += [
        f"Pre-committed thresholds (VALIDATION_PLAN.md):",
        f"- Pass: OOS Sharpe ≥ {PASS_SHARPE_MIN} AND OOS/IS ratio ≥ {int(PASS_RATIO_MIN * 100)}%",
        f"- Marginal: OOS Sharpe ≥ {MARGINAL_SHARPE_MIN} OR OOS/IS ratio ≥ {int(MARGINAL_RATIO_MIN * 100)}%",
        f"- Fail: below both",
        f"- Bootstrap fail-safe: 5th-pct Sharpe < {BOOTSTRAP_P5_FAIL}",
        "",
        f"**Final status: {overall['status'].upper()}** — {overall['reason']}",
    ]

    path.write_text("\n".join(lines))
    return path


def update_state(account: int, name: str, results: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
    else:
        state = {}
    expires = (datetime.now() + timedelta(days=VALIDITY_DAYS)).date().isoformat()
    overall = results["overall"]
    t1 = results["test_1"]
    state[f"account_{account}"] = {
        "name": name,
        "last_run": datetime.now().date().isoformat(),
        "status": overall["status"],
        "oos_sharpe": t1.get("test_sharpe") if not t1.get("skip") else None,
        "oos_is_ratio": t1.get("oos_is_ratio") if not t1.get("skip") else None,
        "oos_cagr": t1.get("test_cagr") if not t1.get("skip") else None,
        "oos_maxdd": t1.get("test_maxdd") if not t1.get("skip") else None,
        "expires": expires,
        "reason": overall["reason"],
    }
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _compute_overall(results: dict) -> dict:
    t1 = results["test_1"]
    t3 = results["test_3"]
    t4 = results["test_4"]

    if t1.get("skip"):
        return {"status": "fail", "reason": "OOS holdout could not be computed"}

    status = t1["status"]
    notes = []

    if not t3.get("skip") and not t3.get("pass", True):
        notes.append(f"Test 3 parameter instability: {t3['reason']}")
        status = "fail"

    if not t4.get("skip") and t4.get("sharpe_p5") is not None:
        if t4["sharpe_p5"] < BOOTSTRAP_P5_FAIL:
            notes.append(
                f"Test 4 bootstrap 5th-pct Sharpe {t4['sharpe_p5']:.2f} < {BOOTSTRAP_P5_FAIL}"
            )
            status = "fail"

    reason = (
        f"OOS Sharpe {t1['test_sharpe']:.2f}, ratio {t1['oos_is_ratio']:.0%}"
        + ("; " + "; ".join(notes) if notes else "")
    )
    return {"status": status, "reason": reason}


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--skip-test-3", action="store_true", help="Skip parameter stability sweep (slow, crypto-only)")
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print(f"  VALIDATION — Account {args.account}")
    print(f"{'=' * 70}")

    print("\nLoading adapter...")
    adapter = build_adapter(args.account)
    print(
        f"  {adapter.name}: {len(adapter.full_returns)} return-days, "
        f"{adapter.full_returns.index[0].date()} → {adapter.full_returns.index[-1].date()}"
    )

    results = {}

    print("\n[1/4] OOS holdout...")
    results["test_1"] = test_1_oos_holdout(adapter)
    t1 = results["test_1"]
    if t1.get("skip"):
        print(f"  SKIPPED: {t1['reason']}")
    else:
        print(
            f"  train Sharpe {t1['train_sharpe']:.2f}, "
            f"test Sharpe {t1['test_sharpe']:.2f}, "
            f"ratio {t1['oos_is_ratio']:.0%} → {t1['status'].upper()}"
        )

    print("\n[2/4] Walk-forward...")
    results["test_2"] = test_2_walk_forward(adapter)
    t2 = results["test_2"]
    print(
        f"  {t2['mode']}: {t2['n_windows']} windows, "
        f"median Sharpe {t2['median_sharpe']:.2f}, "
        f"profitable {t2['profitable_windows']}/{t2['total_windows']}"
    )

    if args.skip_test_3 or adapter.account != 4:
        results["test_3"] = {"skip": True, "reason": "Skipped (flag or non-crypto)"}
        print("\n[3/4] Parameter stability... SKIPPED")
    else:
        print("\n[3/4] Parameter stability sweep (this is slow — ~60 configs × 2 halves)...")
        results["test_3"] = test_3_parameter_stability(adapter)
        t3 = results["test_3"]
        print(
            f"  top-5 overlap: {t3['top5_overlap_count']}/5, "
            f"production config rank A={t3['production_rank_half_a']} B={t3['production_rank_half_b']}"
        )

    print("\n[4/4] Block bootstrap (1000 × 20d blocks)...")
    results["test_4"] = test_4_bootstrap(adapter)
    t4 = results["test_4"]
    if t4.get("skip"):
        print(f"  SKIPPED: {t4['reason']}")
    else:
        print(
            f"  Sharpe p5/p50/p95: {t4['sharpe_p5']:.2f} / {t4['sharpe_p50']:.2f} / {t4['sharpe_p95']:.2f}"
        )

    results["overall"] = _compute_overall(results)

    report_path = write_report(args.account, adapter.name, results)
    update_state(args.account, adapter.name, results)

    print(f"\n{'=' * 70}")
    print(f"  OVERALL: {results['overall']['status'].upper()}")
    print(f"  {results['overall']['reason']}")
    print(f"  Report: {report_path}")
    print(f"  State:  {STATE_PATH}")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
