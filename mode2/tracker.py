"""
Recommendation tracker for Mode 2 PEAD trades.

Logs every recommendation and tracks outcomes over the 60-day drift window.
JSONL format — one record per line, append-only for recommendations,
update in place for outcomes.

This is the evidence base for deciding whether to scale or stop.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

TRACKER_PATH = Path("data/mode2/recommendations.jsonl")


def log_recommendation(rec: dict) -> None:
    """Append a new recommendation to the tracker.

    Expected fields:
        symbol, analysis_date, quarter, year,
        eps_actual, eps_estimate, surprise_pct,
        surprise_quality_score, direction, conviction,
        entry_price, stop_loss, target_price, hold_days,
        position_size_pct, thesis, key_risks
    """
    entry = {
        "id": f"{rec['symbol']}_Q{rec['quarter']}_{rec['year']}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
        **rec,
        # Outcome fields — filled in later
        "actual_entry_price": None,
        "actual_entry_date": None,
        "actual_exit_price": None,
        "actual_exit_date": None,
        "exit_reason": None,  # time_limit | stop_hit | target_hit | thesis_invalidated | manual
        "pnl_dollars": None,
        "pnl_pct": None,
        "hold_days_actual": None,
        "thesis_played_out": None,  # True/False — did the thesis prove correct?
        "notes": None,
    }
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"  Logged recommendation: {entry['id']}")


def load_recommendations() -> list[dict]:
    """Load all recommendations from the tracker."""
    if not TRACKER_PATH.exists():
        return []
    recs = []
    with open(TRACKER_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def get_open_recommendations() -> list[dict]:
    """Get all recommendations with status 'open'."""
    return [r for r in load_recommendations() if r.get("status") == "open"]


def update_recommendation(rec_id: str, updates: dict) -> bool:
    """Update a recommendation by ID (e.g., to record outcome).

    Rewrites the JSONL file with the updated record.
    """
    recs = load_recommendations()
    found = False
    for rec in recs:
        if rec["id"] == rec_id:
            rec.update(updates)
            found = True
            break

    if found:
        with open(TRACKER_PATH, "w") as f:
            for rec in recs:
                f.write(json.dumps(rec) + "\n")
    return found


def close_recommendation(rec_id: str, exit_price: float, exit_date: str,
                          exit_reason: str, thesis_played_out: bool,
                          notes: str = "") -> bool:
    """Close out a recommendation with outcome data."""
    recs = load_recommendations()
    for rec in recs:
        if rec["id"] == rec_id:
            entry_price = rec.get("actual_entry_price") or rec.get("entry_price")
            if entry_price:
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                size = rec.get("position_size_pct", 3) / 100 * 50000
                pnl_dollars = size * pnl_pct / 100
            else:
                pnl_pct = None
                pnl_dollars = None

            entry_date = rec.get("actual_entry_date") or rec.get("analysis_date")
            if entry_date:
                hold_days = (datetime.strptime(exit_date, "%Y-%m-%d") -
                            datetime.strptime(entry_date, "%Y-%m-%d")).days
            else:
                hold_days = None

            return update_recommendation(rec_id, {
                "status": "closed",
                "actual_exit_price": exit_price,
                "actual_exit_date": exit_date,
                "exit_reason": exit_reason,
                "pnl_pct": round(pnl_pct, 2) if pnl_pct else None,
                "pnl_dollars": round(pnl_dollars, 2) if pnl_dollars else None,
                "hold_days_actual": hold_days,
                "thesis_played_out": thesis_played_out,
                "notes": notes,
            })
    return False


def summary_stats() -> dict:
    """Calculate summary statistics across all closed recommendations."""
    recs = load_recommendations()
    closed = [r for r in recs if r.get("status") == "closed"]

    if not closed:
        return {"total": len(recs), "open": len(recs), "closed": 0}

    open_recs = [r for r in recs if r.get("status") == "open"]
    winners = [r for r in closed if (r.get("pnl_pct") or 0) > 0]
    losers = [r for r in closed if (r.get("pnl_pct") or 0) <= 0]

    avg_winner = (sum(r["pnl_pct"] for r in winners) / len(winners)) if winners else 0
    avg_loser = (sum(r["pnl_pct"] for r in losers) / len(losers)) if losers else 0

    return {
        "total": len(recs),
        "open": len(open_recs),
        "closed": len(closed),
        "winners": len(winners),
        "losers": len(losers),
        "hit_rate": len(winners) / len(closed) * 100 if closed else 0,
        "avg_winner_pct": round(avg_winner, 2),
        "avg_loser_pct": round(avg_loser, 2),
        "total_pnl": round(sum(r.get("pnl_dollars", 0) or 0 for r in closed), 2),
        "by_conviction": _stats_by_conviction(closed),
    }


def _stats_by_conviction(closed: list[dict]) -> dict:
    """Break down hit rate by conviction level."""
    by_conv = {}
    for r in closed:
        conv = r.get("conviction", "?")
        if conv not in by_conv:
            by_conv[conv] = {"total": 0, "winners": 0}
        by_conv[conv]["total"] += 1
        if (r.get("pnl_pct") or 0) > 0:
            by_conv[conv]["winners"] += 1
    for conv in by_conv:
        total = by_conv[conv]["total"]
        by_conv[conv]["hit_rate"] = round(by_conv[conv]["winners"] / total * 100, 1) if total else 0
    return by_conv
