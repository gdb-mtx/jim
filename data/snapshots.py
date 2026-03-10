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
    added = 0

    for ts, equity, pl in zip(history.timestamp, history.equity, history.profit_loss):
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        if equity is None or float(equity) == 0:
            continue
        created = save_snapshot(
            account=account,
            snap_date=dt,
            equity=float(equity),
            cash=0.0,  # Not available from history API
            daily_pnl=float(pl) if pl is not None else 0.0,
            positions_count=0,  # Not available from history API
        )
        if created:
            added += 1

    return added


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
    """Sum equity across all 4 accounts by date."""
    frames = []
    for acct in (1, 2, 3, 4):
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
    """Return equity curves for all 4 accounts + combined, keyed for frontend."""
    result = {}
    for acct in (1, 2, 3, 4):
        result[f"acct_{acct}"] = get_equity_history(acct)
    result["combined"] = get_combined_equity_history()
    return result


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
    """Daily returns for all 4 accounts, aligned by date."""
    frames = {}
    for acct in (1, 2, 3, 4):
        r = get_daily_returns(acct)
        if not r.empty:
            frames[f"acct_{acct}"] = r

    if not frames:
        return pd.DataFrame()

    return pd.DataFrame(frames).dropna()
