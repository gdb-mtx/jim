"""
Validation Runner — VALIDATION_PLAN.md Tests 1-4 on a live-paper account.

CAGR-first framework (reaffirmed 2026-04-18). Project thesis: maximize
CAGR subject to tolerable drawdowns over a 3-5 year horizon. Sharpe is
explicitly de-emphasized — retained for reference only.

Primary pass gates (ALL must hold):
  - OOS CAGR       >= 15% (minimum viable contribution to bridge plan)
  - OOS MaxDD      >= -40% (survivability cap for a satellite)
  - OOS Calmar     >= 1.0 (minimum return per unit of worst-case pain)
  - OOS/IS CAGR    >= 70% (no catastrophic degradation from training)

Marginal band:
  - OOS CAGR       >= 10% AND OOS MaxDD >= -50% AND OOS Calmar >= 0.5

Fail-safes (trip to FAIL regardless of primary gates):
  - Test 3 production-config Calmar < 0.5 in EITHER half (crypto only)
  - Test 4 bootstrap 5th-percentile CAGR < 0

Writes a scorecard markdown to data/validation_reports/ and updates
data/risk_state/validation_state.json.

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
    calmar_ratio,
    full_scorecard,
    marginal_portfolio_contribution,
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


# ── Pre-committed CAGR-first thresholds ────────────────────────────────
PASS_CAGR_MIN = 0.15         # 15% CAGR minimum for pass
PASS_MAXDD_MIN = -0.40       # -40% MaxDD ceiling
PASS_CALMAR_MIN = 1.0        # Calmar 1.0 minimum
PASS_OOS_IS_CAGR_RATIO = 0.70  # OOS CAGR >= 70% of IS CAGR

MARGINAL_CAGR_MIN = 0.10
MARGINAL_MAXDD_MIN = -0.50
MARGINAL_CALMAR_MIN = 0.5

BOOTSTRAP_P5_CAGR_FAIL = 0.0  # 5th-percentile forward CAGR < 0 = fail
T3_PRODUCTION_CALMAR_MIN_HALF = 0.5  # Calmar floor per half for crypto Test 3


def _status_from_thresholds(
    cagr: float, maxdd: float, calmar: float, cagr_ratio: float
) -> tuple[str, str]:
    """Classify a strategy's OOS scorecard. Returns (status, short reason)."""
    fails = []
    if cagr < MARGINAL_CAGR_MIN:
        fails.append(f"CAGR {cagr:.1%} < {MARGINAL_CAGR_MIN:.0%}")
    if maxdd < MARGINAL_MAXDD_MIN:
        fails.append(f"MaxDD {maxdd:.1%} < {MARGINAL_MAXDD_MIN:.0%}")
    if calmar < MARGINAL_CALMAR_MIN:
        fails.append(f"Calmar {calmar:.2f} < {MARGINAL_CALMAR_MIN}")
    if fails:
        return "fail", "; ".join(fails)

    passes_all = (
        cagr >= PASS_CAGR_MIN
        and maxdd >= PASS_MAXDD_MIN
        and calmar >= PASS_CALMAR_MIN
        and cagr_ratio >= PASS_OOS_IS_CAGR_RATIO
    )
    if passes_all:
        return "pass", (
            f"CAGR {cagr:.1%}, MaxDD {maxdd:.1%}, Calmar {calmar:.2f}, ratio {cagr_ratio:.0%}"
        )
    parts = [f"CAGR {cagr:.1%}", f"MaxDD {maxdd:.1%}", f"Calmar {calmar:.2f}", f"ratio {cagr_ratio:.0%}"]
    return "marginal", " / ".join(parts)


# ── Test 1: OOS holdout with full scorecard ───────────────────────────
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

    train_sc = full_scorecard(train, ppy)
    test_sc = full_scorecard(test, ppy)

    cagr_ratio = test_sc["cagr"] / train_sc["cagr"] if abs(train_sc["cagr"]) > 1e-6 else 0.0

    status, reason = _status_from_thresholds(
        test_sc["cagr"], test_sc["max_drawdown"], test_sc["calmar"], cagr_ratio
    )

    return {
        "train_period": f"{train.index[0].date()} to {train.index[-1].date()}",
        "test_period": f"{test.index[0].date()} to {test.index[-1].date()}",
        "train_days": int(len(train)),
        "test_days": int(len(test)),
        "train_scorecard": train_sc,
        "test_scorecard": test_sc,
        "oos_is_cagr_ratio": float(cagr_ratio),
        "status": status,
        "reason": reason,
        "pass": status == "pass",
    }


# ── Test 2: Walk-forward with CAGR + Calmar per window ────────────────
def test_2_walk_forward(adapter: AccountAdapter) -> dict:
    if adapter.walk_forward_supported:
        train_size = int(3 * adapter.periods_per_year)
        test_size = int(adapter.periods_per_year)
        step = int(adapter.periods_per_year / 2)
        wf_results = walk_forward_analysis(
            adapter.prices,
            adapter.strategy_fn,
            train_size=train_size,
            test_size=test_size,
            step_size=step,
            warmup=adapter.warmup_days,
        )
        mode = "walk_forward_refit"
        # Rebuild per-window scorecards since walk_forward_analysis stores Sharpe-centric fields
        windows = []
        for w in wf_results:
            # Re-slice returns from the stored window
            # (We don't re-run strategy — just reuse the computed test return stats
            # augmented with Calmar which we can compute from return/DD.)
            ret = w["test_return"]
            dd = w["test_max_dd"]
            windows.append(
                {
                    "window": w["window"],
                    "test_start": str(w["test_start"].date()),
                    "test_end": str(w["test_end"].date()),
                    "cagr": float(ret),
                    "maxdd": float(dd),
                    "calmar": float(ret / abs(dd)) if abs(dd) > 1e-6 else 0.0,
                    "sharpe": float(w["test_sharpe"]),
                }
            )
    else:
        mode = "rolling_full_sample"
        returns = adapter.full_returns
        ppy = adapter.periods_per_year
        window = int(ppy)
        step = int(ppy / 2)
        windows = []
        for start in range(0, len(returns) - window + 1, step):
            s = returns.iloc[start : start + window]
            sc = full_scorecard(s, ppy)
            windows.append(
                {
                    "window": len(windows) + 1,
                    "test_start": str(s.index[0].date()),
                    "test_end": str(s.index[-1].date()),
                    "cagr": float(sc["cagr"]),
                    "maxdd": float(sc["max_drawdown"]),
                    "calmar": float(sc["calmar"]),
                    "sharpe": float(sc["sharpe"]),
                }
            )

    if not windows:
        return {"mode": mode, "n_windows": 0, "pass": False, "reason": "No windows"}

    cagrs = [w["cagr"] for w in windows]
    calmars = [w["calmar"] for w in windows]
    profitable = sum(1 for c in cagrs if c > 0)
    median_cagr = float(np.median(cagrs))
    min_cagr = float(min(cagrs))
    median_calmar = float(np.median(calmars))
    min_calmar = float(min(calmars))

    # Pass: median CAGR >= 10% AND profitable in >=80% of windows
    passes = median_cagr >= 0.10 and profitable / len(windows) >= 0.80

    return {
        "mode": mode,
        "n_windows": len(windows),
        "profitable_windows": profitable,
        "median_cagr": median_cagr,
        "min_cagr": min_cagr,
        "median_calmar": median_calmar,
        "min_calmar": min_calmar,
        "windows": windows,
        "pass": passes,
        "reason": (
            f"Median CAGR {median_cagr:.1%}, profitable {profitable}/{len(windows)} "
            f"({'PASS' if passes else 'FAIL'}: need median >= 10% AND >= 80% profitable)"
        ),
    }


# ── Test 3: Parameter stability — now Calmar-based ────────────────────
def test_3_parameter_stability(adapter: AccountAdapter) -> dict:
    """Crypto-only. Re-rank configs by Calmar (not Sharpe). Pass if
    production config delivers Calmar >= T3_PRODUCTION_CALMAR_MIN_HALF
    in BOTH halves — the spirit shifts from 'are top configs stable?'
    to 'does our chosen config survive regime changes?'"""
    if adapter.account != 4:
        return {"skip": True, "reason": "Parameter stability test is crypto-only"}

    from mode2.crypto_autoresearch import Config, run_config  # noqa: E402

    prices = adapter.prices
    from data.crypto import download_btc_prices
    btc = download_btc_prices()

    sweep: list[Config] = []
    for filter_type, filter_period in [
        ("sma", 100), ("sma", 125), ("sma", 150), ("sma", 175), ("sma", 200),
        ("ema", 100), ("ema", 150), ("ema", 200),
        ("none", 0),
    ]:
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
                calmar = (r.cagr / 100) / (abs(r.max_dd) / 100) if r.max_dd else 0.0
                results.append(
                    {
                        "name": cfg.name,
                        "sharpe": r.sharpe,
                        "cagr": r.cagr / 100,  # run_config returns % — normalize to decimal
                        "max_dd": r.max_dd / 100,
                        "calmar": calmar,
                    }
                )
            except Exception as e:
                results.append({"name": cfg.name, "error": str(e)})
        # Rank by Calmar, not Sharpe
        return sorted(
            [r for r in results if "error" not in r],
            key=lambda r: r["calmar"],
            reverse=True,
        )

    half_a = _run_half("2020-01-01", "2022-12-31")
    half_b = _run_half("2023-01-01", "2026-12-31")

    from strategies.crypto_momentum import CryptoMomentum as _CM
    _cm = _CM()
    production_name = f"sma-{_cm.btc_ma_period}/lb{_cm.lookback_days}/top{_cm.top_n}"

    prod_a = next((r for r in half_a if r["name"] == production_name), None)
    prod_b = next((r for r in half_b if r["name"] == production_name), None)
    prod_rank_a = next((i for i, r in enumerate(half_a) if r["name"] == production_name), -1)
    prod_rank_b = next((i for i, r in enumerate(half_b) if r["name"] == production_name), -1)

    # Also report the overlap-by-Calmar metric for reference (how coherent is the surface)
    top_a = {r["name"] for r in half_a[:5]}
    top_b = {r["name"] for r in half_b[:5]}
    overlap = top_a & top_b

    # Pass gate: production Calmar >= 0.5 in BOTH halves
    prod_calmar_a = prod_a["calmar"] if prod_a else 0.0
    prod_calmar_b = prod_b["calmar"] if prod_b else 0.0
    passes = (
        prod_calmar_a >= T3_PRODUCTION_CALMAR_MIN_HALF
        and prod_calmar_b >= T3_PRODUCTION_CALMAR_MIN_HALF
    )

    return {
        "n_configs": len(sweep),
        "half_a_range": "2020-01-01 to 2022-12-31",
        "half_b_range": "2023-01-01 to 2026-12-31",
        "top_5_half_a_by_calmar": half_a[:5],
        "top_5_half_b_by_calmar": half_b[:5],
        "top5_overlap_count": len(overlap),
        "top5_overlap": sorted(overlap),
        "production_config": production_name,
        "production_rank_half_a": prod_rank_a + 1 if prod_rank_a >= 0 else None,
        "production_rank_half_b": prod_rank_b + 1 if prod_rank_b >= 0 else None,
        "production_calmar_half_a": prod_calmar_a,
        "production_calmar_half_b": prod_calmar_b,
        "production_cagr_half_a": prod_a["cagr"] if prod_a else None,
        "production_cagr_half_b": prod_b["cagr"] if prod_b else None,
        "pass": passes,
        "reason": (
            f"Production Calmar: half A {prod_calmar_a:.2f}, half B {prod_calmar_b:.2f} "
            f"(need >= {T3_PRODUCTION_CALMAR_MIN_HALF} in both)"
        ),
    }


# ── Test 4: Block bootstrap with CAGR percentiles ─────────────────────
def test_4_bootstrap(adapter: AccountAdapter) -> dict:
    """Block bootstrap. Primary metric is now CAGR p5 (forward worst-case
    compounding rate), not Sharpe. Pass if p5 CAGR >= 0."""
    result = block_bootstrap(
        adapter.full_returns,
        block_size=20,
        n_simulations=1000,
        periods_per_year=adapter.periods_per_year,
        seed=42,
    )
    if result.get("skip"):
        return result

    # block_bootstrap only returns Sharpe percentiles currently — compute
    # CAGR percentiles from final_values (re-run manually here to keep it
    # self-contained, avoiding bootstrap.py signature changes).
    rng = np.random.default_rng(42)
    arr = adapter.full_returns.dropna().values
    n = len(arr)
    block = 20
    sims = 1000
    n_blocks = n // block
    cagrs = np.empty(sims)
    ppy = adapter.periods_per_year
    for i in range(sims):
        start_idx = rng.integers(0, n - block + 1, size=n_blocks)
        sample = np.concatenate([arr[s : s + block] for s in start_idx])
        total = float(np.prod(1 + sample))
        years = len(sample) / ppy
        cagrs[i] = total ** (1 / years) - 1 if years > 0 and total > 0 else -1.0

    cagr_p5 = float(np.percentile(cagrs, 5))
    cagr_p50 = float(np.percentile(cagrs, 50))
    cagr_p95 = float(np.percentile(cagrs, 95))
    cagr_positive_pct = float((cagrs > 0).mean())

    passes_cagr = cagr_p5 >= BOOTSTRAP_P5_CAGR_FAIL

    result["cagr_p5"] = cagr_p5
    result["cagr_p50"] = cagr_p50
    result["cagr_p95"] = cagr_p95
    result["cagr_positive_pct"] = cagr_positive_pct
    result["pass"] = passes_cagr
    result["reason"] = (
        f"5th-pct CAGR {cagr_p5:+.1%} {'>=' if passes_cagr else '<'} "
        f"{BOOTSTRAP_P5_CAGR_FAIL:.0%}"
    )
    return result


# ── Portfolio fit (satellite marginal contribution) ───────────────────
def portfolio_fit(adapter: AccountAdapter) -> dict:
    """How much does adding this account to the 3-account core lift CAGR?
    Satellite weight 25% by default."""
    if adapter.account == 4:
        weight = 0.25
    else:
        weight = 1 / 3  # core account in the 3-account blend

    # Need existing portfolio returns — reconstruct 3-account mean
    from strategies.portfolio import run_combined_portfolio
    _, combined = run_combined_portfolio(start="2010-01-01")
    combined = combined.dropna()
    combined_test = combined[combined.index > TRAIN_END]
    candidate_test = adapter.full_returns[adapter.full_returns.index > TRAIN_END]

    if adapter.account == 4:
        # Satellite: measure what Account 4 would add to the 3-account core.
        # marginal_portfolio_contribution uses union-calendar alignment so
        # crypto weekend returns are preserved — pass the crypto ppy (365).
        marginal = marginal_portfolio_contribution(
            candidate_test, combined_test, weight=weight, periods_per_year=adapter.periods_per_year
        )
    else:
        # Core accounts are already part of `combined` — skip
        return {"skip": True, "reason": "Core account is already inside combined portfolio"}

    return marginal


# ── Report + state I/O ────────────────────────────────────────────────
def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _scorecard_block(sc: dict, period_label: str, days: int) -> list[str]:
    return [
        f"### {period_label} ({days}d)",
        "",
        "| Metric | Value | Metric | Value |",
        "|---|---|---|---|",
        f"| **CAGR** | **{_fmt_pct(sc['cagr'])}** | Win rate | {sc.get('win_rate', 0) * 100 if 'win_rate' in sc else 0:.1f}% |",
        f"| **Max Drawdown** | **{_fmt_pct(sc['max_drawdown'])}** | Time underwater | {_fmt_pct(sc['time_underwater_pct'])} |",
        f"| **Calmar** | **{sc['calmar']:.2f}** | Max recovery (d) | {sc['max_recovery_days']} |",
        f"| MAR | {sc['mar']:.2f} | Sterling | {sc['sterling']:.2f} |",
        f"| Burke | {sc['burke']:.2f} | Pain ratio | {sc['pain_ratio']:.2f} |",
        f"| Ulcer Index | {_fmt_pct(sc['ulcer_index'])} | UPI | {sc['ulcer_performance_index']:.2f} |",
        f"| Sortino | {sc['sortino']:.2f} | Omega | {sc['omega']:.2f} |",
        f"| Gain-to-Pain | {sc['gain_to_pain']:.2f} | *Sharpe (info)* | *{sc['sharpe']:.2f}* |",
        "",
    ]


def write_report(account: int, name: str, results: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"account_{account}_{ts}.md"

    t1 = results["test_1"]
    t2 = results["test_2"]
    t3 = results["test_3"]
    t4 = results["test_4"]
    pfit = results.get("portfolio_fit", {})
    overall = results["overall"]

    lines = [
        f"# Validation Report — Account {account}: {name}",
        "",
        f"Run: {datetime.now().isoformat(timespec='seconds')}",
        f"**Overall: {overall['status'].upper()}** — {overall['reason']}",
        "",
        "## Test 1 — Out-of-Sample Holdout (full scorecard)",
        "",
    ]
    if t1.get("skip"):
        lines.append(f"SKIPPED: {t1['reason']}")
    else:
        lines += _scorecard_block(t1["train_scorecard"], f"Train ({t1['train_period']})", t1["train_days"])
        lines += _scorecard_block(t1["test_scorecard"], f"Test ({t1['test_period']})", t1["test_days"])
        lines += [
            f"- OOS / IS CAGR ratio: **{t1['oos_is_cagr_ratio']:.1%}**",
            f"- Test 1 status: **{t1['status'].upper()}** — {t1['reason']}",
            "",
        ]

    lines += ["## Test 2 — Walk-Forward (per window)"]
    lines.append(f"Mode: `{t2['mode']}` — {t2['n_windows']} windows, profitable {t2.get('profitable_windows', 0)}/{t2['n_windows']}")
    lines += [
        f"- Median CAGR: **{t2.get('median_cagr', 0) * 100:+.1f}%**, min CAGR: {t2.get('min_cagr', 0) * 100:+.1f}%",
        f"- Median Calmar: {t2.get('median_calmar', 0):.2f}, min Calmar: {t2.get('min_calmar', 0):.2f}",
        f"- Pass: {t2['pass']} — {t2['reason']}",
        "",
        "| # | Window | CAGR | MaxDD | Calmar | Sharpe |",
        "|---|---|---|---|---|---|",
    ]
    for w in t2.get("windows", []):
        lines.append(
            f"| {w['window']} | {w['test_start']} → {w['test_end']} | "
            f"{w['cagr'] * 100:+.1f}% | {w['maxdd'] * 100:+.1f}% | "
            f"{w['calmar']:.2f} | {w['sharpe']:.2f} |"
        )

    lines += ["", "## Test 3 — Parameter Stability (crypto only, Calmar-ranked)"]
    if t3.get("skip"):
        lines.append(f"SKIPPED: {t3['reason']}")
    else:
        lines += [
            f"- Sweep: {t3['n_configs']} configs, ranked by Calmar",
            "",
            f"Half A ({t3['half_a_range']}) top 5 by Calmar:",
            "",
            "| Rank | Config | CAGR | MaxDD | Calmar |",
            "|---|---|---|---|---|",
        ]
        for i, r in enumerate(t3["top_5_half_a_by_calmar"], 1):
            lines.append(f"| {i} | {r['name']} | {r['cagr'] * 100:+.1f}% | {r['max_dd'] * 100:+.1f}% | {r['calmar']:.2f} |")
        lines += [
            "",
            f"Half B ({t3['half_b_range']}) top 5 by Calmar:",
            "",
            "| Rank | Config | CAGR | MaxDD | Calmar |",
            "|---|---|---|---|---|",
        ]
        for i, r in enumerate(t3["top_5_half_b_by_calmar"], 1):
            lines.append(f"| {i} | {r['name']} | {r['cagr'] * 100:+.1f}% | {r['max_dd'] * 100:+.1f}% | {r['calmar']:.2f} |")
        lines += [
            "",
            f"- Production config: **{t3['production_config']}**",
            f"  - Half A: rank {t3['production_rank_half_a']}/{t3['n_configs']}, CAGR {t3['production_cagr_half_a'] * 100 if t3['production_cagr_half_a'] is not None else 0:+.1f}%, Calmar {t3['production_calmar_half_a']:.2f}",
            f"  - Half B: rank {t3['production_rank_half_b']}/{t3['n_configs']}, CAGR {t3['production_cagr_half_b'] * 100 if t3['production_cagr_half_b'] is not None else 0:+.1f}%, Calmar {t3['production_calmar_half_b']:.2f}",
            f"- Top-5 Calmar overlap across halves: {t3['top5_overlap_count']}/5 (descriptive only)",
            f"- Pass: {t3['pass']} — {t3['reason']}",
        ]

    lines += ["", "## Test 4 — Block Bootstrap (CAGR-centric)"]
    if t4.get("skip"):
        lines.append(f"SKIPPED: {t4.get('reason')}")
    else:
        lines += [
            f"- N simulations: {t4['n_simulations']}, block size {t4['block_size']}d",
            f"- **CAGR p5 / p50 / p95:** {t4['cagr_p5'] * 100:+.1f}% / {t4['cagr_p50'] * 100:+.1f}% / {t4['cagr_p95'] * 100:+.1f}%",
            f"- Positive-CAGR resamples: {t4['cagr_positive_pct']:.1%}",
            f"- Sharpe p5 / p50 / p95 (info only): {t4['sharpe_p5']:.2f} / {t4['sharpe_p50']:.2f} / {t4['sharpe_p95']:.2f}",
            f"- MaxDD p5 / p95: {_fmt_pct(t4['maxdd_p5'])} / {_fmt_pct(t4['maxdd_p95'])}",
            f"- Pass: {t4['pass']} — {t4['reason']}",
        ]

    if pfit and not pfit.get("skip"):
        lines += ["", "## Portfolio Fit — satellite marginal contribution"]
        lines += [
            f"- Candidate weight: {pfit['weight']:.0%}",
            f"- Correlation to existing combined book: **{pfit['correlation']:.2f}**",
            f"- Base combined CAGR: {_fmt_pct(pfit['base_cagr'])}  →  New combined CAGR: **{_fmt_pct(pfit['combined_cagr'])}**  (Δ {_fmt_pct(pfit['delta_cagr'])})",
            f"- Base combined MaxDD: {_fmt_pct(pfit['base_maxdd'])}  →  New combined MaxDD: {_fmt_pct(pfit['combined_maxdd'])}  (Δ {_fmt_pct(pfit['delta_maxdd'])})",
            f"- Base combined Calmar: {pfit['base_calmar']:.2f}  →  New combined Calmar: **{pfit['combined_calmar']:.2f}**  (Δ {pfit['delta_calmar']:+.2f})",
        ]

    lines += ["", "## Decision thresholds"]
    lines += [
        "- **Pass**: CAGR ≥ 15% AND MaxDD ≥ -40% AND Calmar ≥ 1.0 AND OOS/IS CAGR ≥ 70%",
        "- **Marginal**: CAGR ≥ 10% AND MaxDD ≥ -50% AND Calmar ≥ 0.5",
        "- **Fail**: below marginal",
        "- Fail-safe 1 (crypto only): Test 3 production Calmar < 0.5 in either half",
        "- Fail-safe 2: Test 4 bootstrap 5th-percentile CAGR < 0",
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
    sc = t1.get("test_scorecard") or {}
    state[f"account_{account}"] = {
        "name": name,
        "last_run": datetime.now().date().isoformat(),
        "status": overall["status"],
        "oos_cagr": sc.get("cagr"),
        "oos_maxdd": sc.get("max_drawdown"),
        "oos_calmar": sc.get("calmar"),
        "oos_mar": sc.get("mar"),
        "oos_sterling": sc.get("sterling"),
        "oos_ulcer_perf_index": sc.get("ulcer_performance_index"),
        "oos_sortino": sc.get("sortino"),
        "oos_sharpe_info_only": sc.get("sharpe"),
        "oos_is_cagr_ratio": t1.get("oos_is_cagr_ratio"),
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
        notes.append(f"Test 3 parameter stability: {t3['reason']}")
        status = "fail"

    if not t4.get("skip") and t4.get("cagr_p5") is not None:
        if t4["cagr_p5"] < BOOTSTRAP_P5_CAGR_FAIL:
            notes.append(f"Test 4 bootstrap 5th-pct CAGR {t4['cagr_p5']:+.1%} < 0")
            status = "fail"

    reason = t1["reason"] + (("; " + "; ".join(notes)) if notes else "")
    return {"status": status, "reason": reason}


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--skip-test-3", action="store_true", help="Skip parameter stability sweep (slow, crypto-only)")
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print(f"  VALIDATION — Account {args.account}  (CAGR-first scorecard)")
    print(f"{'=' * 70}")

    print("\nLoading adapter...")
    adapter = build_adapter(args.account)
    print(
        f"  {adapter.name}: {len(adapter.full_returns)} return-days, "
        f"{adapter.full_returns.index[0].date()} → {adapter.full_returns.index[-1].date()}"
    )

    results = {}

    print("\n[1/5] OOS holdout (full scorecard)...")
    results["test_1"] = test_1_oos_holdout(adapter)
    t1 = results["test_1"]
    if t1.get("skip"):
        print(f"  SKIPPED: {t1['reason']}")
    else:
        sc = t1["test_scorecard"]
        print(
            f"  test CAGR {sc['cagr'] * 100:+.1f}%, MaxDD {sc['max_drawdown'] * 100:+.1f}%, "
            f"Calmar {sc['calmar']:.2f}, ratio {t1['oos_is_cagr_ratio']:.0%} → {t1['status'].upper()}"
        )

    print("\n[2/5] Walk-forward (CAGR per window)...")
    results["test_2"] = test_2_walk_forward(adapter)
    t2 = results["test_2"]
    print(
        f"  {t2['mode']}: {t2['n_windows']} windows, "
        f"median CAGR {t2.get('median_cagr', 0) * 100:+.1f}%, "
        f"median Calmar {t2.get('median_calmar', 0):.2f}"
    )

    if args.skip_test_3 or adapter.account != 4:
        results["test_3"] = {"skip": True, "reason": "Skipped (flag or non-crypto)"}
        print("\n[3/5] Parameter stability... SKIPPED")
    else:
        print("\n[3/5] Parameter stability (Calmar-ranked sweep across halves)...")
        results["test_3"] = test_3_parameter_stability(adapter)
        t3 = results["test_3"]
        print(
            f"  production Calmar: half A {t3['production_calmar_half_a']:.2f}, "
            f"half B {t3['production_calmar_half_b']:.2f} → {'PASS' if t3['pass'] else 'FAIL'}"
        )

    print("\n[4/5] Block bootstrap (CAGR percentiles)...")
    results["test_4"] = test_4_bootstrap(adapter)
    t4 = results["test_4"]
    if t4.get("skip"):
        print(f"  SKIPPED: {t4['reason']}")
    else:
        print(
            f"  CAGR p5/p50/p95: {t4['cagr_p5'] * 100:+.1f}% / "
            f"{t4['cagr_p50'] * 100:+.1f}% / {t4['cagr_p95'] * 100:+.1f}%"
        )

    print("\n[5/5] Portfolio fit (satellite contribution)...")
    try:
        results["portfolio_fit"] = portfolio_fit(adapter)
        pfit = results["portfolio_fit"]
        if pfit.get("skip"):
            print(f"  {pfit['reason']}")
        else:
            print(
                f"  corr {pfit['correlation']:.2f}, "
                f"Δ CAGR {pfit['delta_cagr'] * 100:+.1f}%, "
                f"Δ MaxDD {pfit['delta_maxdd'] * 100:+.1f}%, "
                f"Δ Calmar {pfit['delta_calmar']:+.2f}"
            )
    except Exception as e:
        results["portfolio_fit"] = {"skip": True, "reason": f"Error: {e}"}
        print(f"  ERROR: {e}")

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
