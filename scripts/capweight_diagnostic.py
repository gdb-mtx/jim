"""Cap-weight diagnostic for Account 1 (SM + SPY Filter).

Re-runs A1 under equal / cap / sqrt-cap weighting and compares each arm's
gap-to-SPY. Answers the question behind the SPY-underperformance
disappointment: is the gap a WEIGHTING artifact (equal-weight in a mega-cap
concentration regime) or GENUINE bad picks? See
docs/research/BREAKTHROUGH_VECTORS_MAY2026.md.

Diagnostic only:
  - Frozen-shares caps (5-20% per-stock error; mega-cap *ordering* is robust).
  - Survivorship-biased universe (current S&P list) — but it biases all arms
    identically, so the RELATIVE gap-closure read is clean.
  - Live A1 is untouched (default weighting_scheme is equal_weight).

Run: uv run python3 scripts/capweight_diagnostic.py
"""

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.pipeline import download_and_cache
from data.sp500 import download_sp500_prices
from data.fundamentals import build_market_caps
from strategies.portfolio_backtest import run_portfolio
from backtesting.metrics import full_scorecard, annualized_return

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("capweight")

START = "2010-01-01"
TRAIN_END = pd.Timestamp("2022-12-31")  # OOS split — matches scripts/run_validation.py
OUT_PATH = "docs/research/capweight_diagnostic_results.md"

ARMS = {
    "equal": {"weighting_scheme": "equal_weight"},
    "cap": {"weighting_scheme": "cap_weight"},
    "sqrt_cap": {"weighting_scheme": "sqrt_cap_weight"},
}


def _spy_returns() -> pd.Series:
    spy = download_and_cache(["SPY"], start=START, end=None, cache_name="spy_benchmark")
    return spy["SPY"].pct_change()


def _excess_cagr(arm_ret: pd.Series, spy_ret: pd.Series) -> float:
    aligned = pd.DataFrame({"a": arm_ret, "s": spy_ret}).dropna()
    if aligned.empty:
        return float("nan")
    return annualized_return(aligned["a"] - aligned["s"], 252)


def _scorecard_row(arm: str, window: str, ret: pd.Series, spy_ret: pd.Series) -> dict:
    sc = full_scorecard(ret, 252)
    return {
        "arm": arm,
        "window": window,
        "cagr": sc["cagr"],
        "maxdd": sc["max_drawdown"],
        "calmar": sc["calmar"],
        "excess_spy": _excess_cagr(ret, spy_ret),
    }


def main():
    # Frozen-shares caps for the stock universe (one-time fetch, then cached).
    stock_prices = download_sp500_prices(start=START)
    n_tickers = stock_prices.shape[1]
    log.info("Building frozen-shares caps for %d tickers...", n_tickers)
    caps = build_market_caps(stock_prices)
    covered = int(caps.notna().any().sum())
    log.info("Cap coverage: %d/%d tickers have shares data (%.0f%%)",
             covered, n_tickers, 100 * covered / max(n_tickers, 1))

    spy_ret = _spy_returns()

    rows: list[dict] = []
    for arm, params in ARMS.items():
        sp = dict(params)
        if arm != "equal":
            sp["market_caps"] = caps
        log.info("Running A1 backtest arm: %s ...", arm)
        _, ret = run_portfolio(
            "sm_filtered", start=START,
            strategy_params={"stock_momentum": sp},
        )
        rows.append(_scorecard_row(arm, "full", ret, spy_ret))
        rows.append(_scorecard_row(arm, "oos", ret[ret.index > TRAIN_END], spy_ret))

    # SPY reference rows.
    for window, mask in (("full", spy_ret.index >= pd.Timestamp(START)),
                         ("oos", spy_ret.index > TRAIN_END)):
        r = spy_ret[mask].dropna()
        sc = full_scorecard(r, 252)
        rows.append({"arm": "SPY", "window": window, "cagr": sc["cagr"],
                     "maxdd": sc["max_drawdown"], "calmar": sc["calmar"],
                     "excess_spy": 0.0})

    df = pd.DataFrame(rows)
    report = _render(df, covered, n_tickers)
    print("\n" + report)
    with open(OUT_PATH, "w") as f:
        f.write(report)
    log.info("Wrote %s", OUT_PATH)


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x * 100:+.1f}%"


def _num(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.2f}"


def _table(df: pd.DataFrame, window: str) -> str:
    sub = df[df["window"] == window]
    span = "2023-01-01 onward" if window == "oos" else "2010 onward"
    lines = [
        f"### {window.upper()} ({span})",
        "",
        "| Arm | CAGR | MaxDD | Calmar | Excess vs SPY (CAGR) |",
        "|---|---|---|---|---|",
    ]
    for arm in ("equal", "cap", "sqrt_cap", "SPY"):
        r = sub[sub["arm"] == arm]
        if r.empty:
            continue
        r = r.iloc[0]
        excess = "—" if arm == "SPY" else _pct(r["excess_spy"])
        lines.append(
            f"| {arm} | {_pct(r['cagr'])} | {_pct(r['maxdd'])} | {_num(r['calmar'])} | {excess} |"
        )
    return "\n".join(lines)


def _verdict(df: pd.DataFrame) -> str:
    oos = df[df["window"] == "oos"].set_index("arm")
    lines = ["## Verdict (OOS — the regime in question)", ""]
    if "equal" not in oos.index or pd.isna(oos.loc["equal", "excess_spy"]):
        return "\n".join(lines + ["Could not compute equal-weight excess — check data."])
    e_eq = oos.loc["equal", "excess_spy"]
    lines.append(f"- Equal-weight OOS gap to SPY: **{_pct(e_eq)}**")
    if e_eq >= 0:
        lines.append(
            "- Equal-weight already beats SPY OOS — there is no gap to close. The "
            "disappointment is then an expectations/benchmark issue, not weighting "
            "and not the picks."
        )
        return "\n".join(lines)

    closures = {}
    for arm in ("cap", "sqrt_cap"):
        if arm in oos.index and not pd.isna(oos.loc[arm, "excess_spy"]):
            e_arm = oos.loc[arm, "excess_spy"]
            closures[arm] = (e_arm - e_eq) / (-e_eq)
            lines.append(
                f"- {arm}: gap **{_pct(e_arm)}** → closes **{closures[arm] * 100:.0f}%** "
                "of the equal-weight gap"
            )
    lines.append("")
    best_closure = max(closures.values()) if closures else 0.0
    if best_closure >= 0.30:
        lines.append(
            f"**Read:** cap-tilting closes ~{best_closure * 100:.0f}% of the SPY gap — a "
            "meaningful chunk of the underperformance is the equal-weight convention in a "
            "concentration regime, not the stock picks. Worth a cap-tilted A1 variant (or A5); "
            "the picks are not the problem."
        )
    else:
        lines.append(
            f"**Read:** cap-tilting closes only ~{best_closure * 100:.0f}% of the gap — weighting "
            "is not the main story. The picks themselves are not beating the market, so the "
            "priority is structurally different edges (the breakthrough vectors), not re-weighting A1."
        )
    return "\n".join(lines)


def _render(df: pd.DataFrame, covered: int, n_tickers: int) -> str:
    return "\n".join([
        "# Cap-Weight Diagnostic — Account 1 (SM + SPY Filter)",
        "",
        "Does A1's SPY underperformance come from **equal-weighting** (in a "
        "mega-cap concentration regime) or from **genuine bad picks**? Same top-15 "
        "momentum selection, three weighting schemes, each compared to SPY.",
        "",
        _verdict(df),
        "",
        _table(df, "oos"),
        "",
        _table(df, "full"),
        "",
        "## Caveats",
        f"- **Frozen shares:** caps = current shares × historical price (5-20% per-stock "
        f"error). Cap coverage: {covered}/{n_tickers} tickers. Adequate for a directional "
        "read; mega-cap ordering is robust to the error.",
        "- **Survivorship bias:** current S&P list only (no delisted names) — absolute "
        "numbers run optimistic, but the bias hits all arms identically so the *relative* "
        "gap-closure is the trustworthy signal.",
        "- Generated by `scripts/capweight_diagnostic.py`.",
    ])


if __name__ == "__main__":
    main()
