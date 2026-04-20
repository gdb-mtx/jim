"""Daily equity snapshot storage for performance tracking.

Stores one row per trading day per account in parquet files under data/processed/.
Supports backfill from Alpaca's portfolio history API to recover missed days.
"""

import os
from datetime import date, datetime

import numpy as np
import pandas as pd

from execution.alpaca_broker import AlpacaBroker

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "processed")


def _snapshot_path(account: int) -> str:
    return os.path.join(SNAPSHOT_DIR, f"snapshots_acct{account}.parquet")


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["equity", "cash", "daily_pnl", "positions_count"],
        index=pd.DatetimeIndex([], name="date"),
    ).astype(
        {"equity": float, "cash": float, "daily_pnl": float, "positions_count": int}
    )


def load_snapshots(account: int) -> pd.DataFrame:
    """Load snapshot history for an account. Returns empty DF if no file."""
    path = _snapshot_path(account)
    if not os.path.exists(path):
        return _empty_df()
    df = pd.read_parquet(path)
    df.index = pd.DatetimeIndex(df.index, name="date")
    return df.sort_index()


def save_snapshot(
    account: int,
    snap_date: str,
    equity: float,
    cash: float,
    daily_pnl: float,
    positions_count: int,
) -> bool:
    """Append a single day's snapshot. Returns False if date already exists."""
    df = load_snapshots(account)
    dt = pd.Timestamp(snap_date).normalize()

    if dt in df.index:
        return False

    new_row = pd.DataFrame(
        {"equity": [equity], "cash": [cash], "daily_pnl": [daily_pnl], "positions_count": [positions_count]},
        index=pd.DatetimeIndex([dt], name="date"),
    )
    df = pd.concat([df, new_row]).sort_index()

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    df.to_parquet(_snapshot_path(account))
    return True


def take_snapshot(account: int) -> dict:
    """Take a live snapshot from Alpaca for one account."""
    broker = AlpacaBroker(account=account)
    acct = broker.get_account()
    positions = broker.get_positions()
    today = date.today().isoformat()

    created = save_snapshot(
        account=account,
        snap_date=today,
        equity=acct["equity"],
        cash=acct["cash"],
        daily_pnl=acct["daily_pnl"],
        positions_count=len(positions),
    )
    return {
        "account": account,
        "date": today,
        "equity": acct["equity"],
        "cash": acct["cash"],
        "daily_pnl": acct["daily_pnl"],
        "positions_count": len(positions),
        "created": created,
    }


def take_all_snapshots() -> list[dict]:
    """Take snapshots for all 4 accounts."""
    results = []
    for acct in (1, 2, 3, 4):
        try:
            results.append(take_snapshot(acct))
        except Exception as e:
            results.append({"account": acct, "error": str(e), "created": False})
    return results


def backfill_from_alpaca(account: int) -> int:
    """Backfill historical equity from Alpaca portfolio history API.

    Returns number of new rows added.
    """
    broker = AlpacaBroker(account=account)
    # get_portfolio_history returns an object with timestamp, equity, profit_loss
    history = broker.api.get_portfolio_history(period="3M", timeframe="1D")

    if not history or not hasattr(history, "timestamp") or not history.timestamp:
        return 0

    df = load_snapshots(account)

    # Collect all new rows, then append in one batch
    new_rows = []
    for ts, equity, pl in zip(history.timestamp, history.equity, history.profit_loss):
        dt = pd.Timestamp(datetime.fromtimestamp(ts).strftime("%Y-%m-%d")).normalize()
        if equity is None or float(equity) == 0:
            continue
        if dt in df.index:
            continue
        new_rows.append({
            "date": dt,
            "equity": float(equity),
            "cash": np.nan,  # Not available from history API
            "daily_pnl": float(pl) if pl is not None else 0.0,
            "positions_count": np.nan,  # Not available from history API
        })

    if not new_rows:
        return 0

    new_df = pd.DataFrame(new_rows).set_index("date")
    df = pd.concat([df, new_df]).sort_index()

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    df.to_parquet(_snapshot_path(account))
    return len(new_rows)


# ── Query functions ──────────────────────────────────────────────────


def get_equity_history(account: int) -> list[dict]:
    """Return equity time series in EquityPoint format [{time, value}]."""
    df = load_snapshots(account)
    if df.empty:
        return []
    return [
        {"time": idx.strftime("%Y-%m-%d"), "value": float(row["equity"])}
        for idx, row in df.iterrows()
    ]


def get_combined_equity_history() -> list[dict]:
    """Sum equity across active accounts by date. Retired accounts are
    excluded so the combined curve tracks the live book only."""
    from execution.alpaca_broker import active_accounts

    frames = []
    for acct in active_accounts():
        df = load_snapshots(acct)
        if not df.empty:
            frames.append(df[["equity"]].rename(columns={"equity": f"acct_{acct}"}))

    if not frames:
        return []

    combined = pd.concat(frames, axis=1).dropna()
    combined["total"] = combined.sum(axis=1)
    return [
        {"time": idx.strftime("%Y-%m-%d"), "value": float(row["total"])}
        for idx, row in combined.iterrows()
    ]


def get_all_equity_histories() -> dict[str, list[dict]]:
    """Return equity curves for active accounts + combined, keyed for frontend.
    Retired account history remains available via per-account `/history`."""
    from execution.alpaca_broker import active_accounts

    result = {}
    for acct in active_accounts():
        result[f"acct_{acct}"] = get_equity_history(acct)
    result["combined"] = get_combined_equity_history()
    return result


def get_spy_benchmark(dates: list[str], start_value: float) -> list[dict]:
    """Return SPY normalized to start_value over the given dates.

    Downloads SPY prices, aligns to the provided dates, and scales so the
    first data point equals start_value. Returns [{time, value}] format.
    """
    if not dates or start_value <= 0:
        return []

    try:
        from data.pipeline import download_prices

        spy = download_prices(["SPY"], start="2025-01-01").squeeze()
        # Align to snapshot dates
        snap_dates = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
        spy = spy.reindex(snap_dates).ffill().dropna()
        if spy.empty:
            return []

        # Normalize: first SPY value maps to start_value
        spy_normalized = spy / spy.iloc[0] * start_value
        return [
            {"time": idx.strftime("%Y-%m-%d"), "value": round(float(val), 2)}
            for idx, val in spy_normalized.items()
        ]
    except Exception:
        return []


def get_performance_summary(
    live_equity: dict[int, float] | None = None,
) -> list[dict]:
    """Compute per-account and combined returns vs SPY since tracking started.

    Each account's SPY return is computed from that account's own start date.
    Combined SPY return uses the combined equity curve start date (latest of
    all account first dates, matching the chart's SPY benchmark).

    When live_equity is provided, fetches fresh SPY price for an apples-to-apples
    comparison with live portfolio values.

    Returns a list of {account, label, return_pct, spy_return_pct, alpha_pct}
    for each account plus a "Combined" row.
    """
    from execution.alpaca_broker import ACCOUNT_INFO

    results = []
    all_start = 0.0
    all_current = 0.0

    # Load SPY prices — fetch fresh data when comparing to live portfolio values
    try:
        if live_equity:
            from data.pipeline import download_prices
            spy = download_prices(["SPY"], start="2025-01-01").squeeze()
        else:
            from data.pipeline import download_and_cache
            spy = download_and_cache(
                ["SPY"], start="2025-01-01", cache_name="spy_filter"
            ).squeeze()
    except Exception:
        spy = pd.Series(dtype=float)

    def _spy_return_from(start_date: pd.Timestamp) -> float:
        """Compute SPY return from a given start date to latest available."""
        if spy.empty or start_date is None:
            return 0.0
        spy_aligned = spy[spy.index >= start_date]
        if len(spy_aligned) >= 2:
            return round(
                (float(spy_aligned.iloc[-1]) / float(spy_aligned.iloc[0]) - 1) * 100, 2
            )
        return 0.0

    # Load per-account snapshots and compute returns
    combined_start_date = None  # latest first date (when all accounts are live)
    for acct in (1, 2, 3, 4):
        df = load_snapshots(acct)
        if df.empty or len(df) < 2:
            results.append({
                "account": acct,
                "label": ACCOUNT_INFO[acct]["label"],
                "return_pct": 0.0,
                "spy_return_pct": 0.0,
                "alpha_pct": 0.0,
            })
            continue

        start_val = float(df["equity"].iloc[0])
        current_val = (
            live_equity[acct]
            if live_equity and acct in live_equity
            else float(df["equity"].iloc[-1])
        )
        ret = round((current_val / start_val - 1) * 100, 2) if start_val > 0 else 0.0

        # SPY return from this account's own start date
        acct_spy_ret = _spy_return_from(df.index[0])

        results.append({
            "account": acct,
            "label": ACCOUNT_INFO[acct]["label"],
            "return_pct": ret,
            "spy_return_pct": acct_spy_ret,
            "alpha_pct": round(ret - acct_spy_ret, 2),
        })

        all_start += start_val
        all_current += current_val

        # Track combined start date (latest first date across accounts)
        first = df.index[0]
        if combined_start_date is None or first > combined_start_date:
            combined_start_date = first

    # Combined row — SPY from combined start date (matches chart benchmark)
    combined_ret = round((all_current / all_start - 1) * 100, 2) if all_start > 0 else 0.0
    combined_spy_ret = _spy_return_from(combined_start_date)
    results.append({
        "account": 0,
        "label": "Combined",
        "return_pct": combined_ret,
        "spy_return_pct": combined_spy_ret,
        "alpha_pct": round(combined_ret - combined_spy_ret, 2),
    })

    return results


def get_daily_returns(account: int) -> pd.Series:
    """Compute daily returns from equity series."""
    df = load_snapshots(account)
    if df.empty or len(df) < 2:
        return pd.Series(dtype=float)
    returns = df["equity"].pct_change().dropna()
    # Replace inf/-inf with 0 (can happen if equity was 0)
    returns = returns.replace([np.inf, -np.inf], 0.0)
    return returns


def get_all_daily_returns() -> pd.DataFrame:
    """Daily returns for active accounts, aligned by date.
    Retired accounts are excluded — their returns would be ~0 going forward
    (cash) and would dilute correlation signal."""
    from execution.alpaca_broker import active_accounts

    frames = {}
    for acct in active_accounts():
        r = get_daily_returns(acct)
        if not r.empty:
            frames[f"acct_{acct}"] = r

    if not frames:
        return pd.DataFrame()

    return pd.DataFrame(frames).dropna()
