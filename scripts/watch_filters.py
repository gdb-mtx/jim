#!/usr/bin/env python3
"""Travel-window filter watcher.

Designed to run in GitHub Actions every ~30 min while the laptop is off.
Compares live BTC/SPY prices against MA thresholds in
`filter_watch_thresholds.json` and pings ntfy.sh on a state transition
(above-MA <-> below-MA). State persists across runs via the workflow
cache so we alert exactly once per crossing instead of every 30 min.

Stdlib only (urllib + json) — no uv/pip install needed in the workflow.

Env vars (passed by the workflow from GitHub secrets):
- NTFY_TOPIC: the ntfy.sh topic name to push to.
- ALPACA_API_KEY / ALPACA_SECRET_KEY: any account's data-API credentials.

Optional:
- FORCE_TEST=1: send a test ntfy regardless of crossings (verify pipeline).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).parent / "filter_watch_thresholds.json"
STATE_PATH = Path(__file__).parent / "filter_watch_state.json"


def fetch_btc_price() -> float:
    """Spot BTC/USD from CoinGecko (free, no key)."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)
    return float(data["bitcoin"]["usd"])


def fetch_spy_price() -> float:
    """Latest SPY trade from Alpaca data API.

    Outside market hours this returns the most recent close, which is
    exactly what the MA filter compares against.
    """
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    url = "https://data.alpaca.markets/v2/stocks/SPY/trades/latest"
    req = urllib.request.Request(
        url,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return float(data["trade"]["p"])


def send_ntfy(title: str, message: str, *, priority: str = "high", tags: str = "warning") -> None:
    topic = os.environ["NTFY_TOPIC"]
    # HTTP headers must be latin-1; ntfy's Title header is no exception.
    # Drop unicode (em-dash, smart quotes, emoji) to '?' so the request
    # never raises. Body is utf-8 in the payload and unaffected.
    safe_title = title.encode("ascii", "replace").decode("ascii")
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": safe_title, "Priority": priority, "Tags": tags},
    )
    urllib.request.urlopen(req, timeout=15)


def main() -> int:
    if not THRESHOLDS_PATH.exists():
        print(f"ERROR: {THRESHOLDS_PATH.name} missing. Refresh before travel.", file=sys.stderr)
        return 1

    thresholds = json.loads(THRESHOLDS_PATH.read_text())
    btc_ma = thresholds.get("btc_125_ma")
    spy_ma = thresholds.get("spy_200_ma")
    if btc_ma is None or spy_ma is None:
        print(f"ERROR: thresholds incomplete: {thresholds}", file=sys.stderr)
        return 1

    btc_price = fetch_btc_price()
    spy_price = fetch_spy_price()
    btc_above = btc_price > btc_ma
    spy_above = spy_price > spy_ma

    # First run = no prior state; assume both above (= bull) so the first
    # crossing into "below" fires correctly. If you start travel during a
    # bear regime, set last_*_above=false in filter_watch_state.json before
    # the first run.
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
    else:
        state = {"last_btc_above": True, "last_spy_above": True}

    last_btc_above = state.get("last_btc_above", True)
    last_spy_above = state.get("last_spy_above", True)

    alerts: list[str] = []
    if btc_above != last_btc_above:
        direction = "ABOVE" if btc_above else "BELOW"
        alerts.append(f"BTC crossed {direction} 125d MA: ${btc_price:,.0f} vs ${btc_ma:,.0f}")
    if spy_above != last_spy_above:
        direction = "ABOVE" if spy_above else "BELOW"
        alerts.append(f"SPY crossed {direction} 200d MA: ${spy_price:,.2f} vs ${spy_ma:,.2f}")

    if os.environ.get("FORCE_TEST") == "1":
        send_ntfy(
            "Jim Filter Watch - TEST",
            f"Pipeline OK. BTC ${btc_price:,.0f} ({'above' if btc_above else 'below'} ${btc_ma:,.0f}); "
            f"SPY ${spy_price:,.2f} ({'above' if spy_above else 'below'} ${spy_ma:,.2f}).",
            priority="default",
            tags="white_check_mark",
        )
        print("Test notification sent.")

    # Daily heartbeat at 14:00 UTC — confirmation the watcher is alive (otherwise silent unless a flip fires).
    now = datetime.now(timezone.utc)
    last_heartbeat_iso = state.get("last_heartbeat_date")
    today_str = now.date().isoformat()
    in_heartbeat_window = now.hour == 14 and now.minute < 30
    if in_heartbeat_window and last_heartbeat_iso != today_str:
        send_ntfy(
            "Jim Filter Watch - daily heartbeat",
            f"All green. BTC ${btc_price:,.0f} ({'above' if btc_above else 'below'} ${btc_ma:,.0f}); "
            f"SPY ${spy_price:,.2f} ({'above' if spy_above else 'below'} ${spy_ma:,.2f}).",
            priority="low",
            tags="white_check_mark",
        )
        print(f"Heartbeat sent ({today_str}).")

    if alerts:
        body = "\n".join(alerts) + "\n\nOpen laptop and rebalance affected accounts."
        send_ntfy("Jim Filter Flip", body, priority="high", tags="rotating_light")
        print(f"Sent {len(alerts)} alert(s):")
        for a in alerts:
            print(f"  - {a}")
    else:
        print(
            f"No crossings. BTC ${btc_price:,.0f} ({'above' if btc_above else 'below'} ${btc_ma:,.0f}); "
            f"SPY ${spy_price:,.2f} ({'above' if spy_above else 'below'} ${spy_ma:,.2f})."
        )

    # Persist new state — the workflow's cache action picks this up.
    new_state = {
        "last_btc_above": btc_above,
        "last_spy_above": spy_above,
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "btc_price": btc_price,
        "spy_price": spy_price,
        "last_heartbeat_date": today_str if (in_heartbeat_window and last_heartbeat_iso != today_str)
                               else last_heartbeat_iso,
    }
    STATE_PATH.write_text(json.dumps(new_state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
