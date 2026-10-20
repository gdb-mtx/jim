"""Alpaca SIP daily closes for equities — the live/validation price source.

Why Alpaca for equities (2026-10-20; yfinance retired from every live and
validation path — DATA_SOURCES.md):
- `feed=sip` is the consolidated tape, free tier included for historical
  daily bars; `adjustment=all` is split- and dividend-adjusted. Tested
  against the yfinance panel on 2026-10-20: median close difference
  0.002%, A1's top-15 identical on 44/46 grid dates (Jaccard 0.995), OOS
  Calmar 1.92 vs 1.87. Where the two disagree (WDC, TDG, LEN, FTV: >1%)
  Alpaca adjusts spin-offs / special dividends as distributions; yfinance
  doesn't.
- Explicit symbol in, explicit symbol out — no cross-contamination class.
- 499 symbols × 2016→ take ~4.5 min at the free-tier limit (200 req/min),
  deterministic, vs yfinance's 5-45 min with DNS timeouts.

History floor: 2016-01-04 (ALPACA_EQUITY_FLOOR). Earlier bars come from
the one-time banked yfinance segment in data/banked/ (scripts/bank_pre2016.py)
spliced by `splice_banked`.

What still applies: during the session the latest bar is the forming
day — callers drop it with `drop_unsettled_equity_rows` before caching.
"""

import logging
import time
from typing import Iterable

import pandas as pd
import requests

from data.alpaca_crypto_bars import _auth_headers

log = logging.getLogger("fire.alpaca_equity")

API_BASE = "https://data.alpaca.markets/v2/stocks"
ALPACA_EQUITY_FLOOR = "2016-01-04"
_TIMEOUT_S = 30
_THROTTLE_S = 0.32          # 200 requests/min on the free tier
_MIN_COVERAGE = 0.95        # refuse to return a panel missing >5% of symbols
MAX_SEAM_DISPERSION = 0.01  # overlap-ratio MAD/median above this = not the same instrument


def _alpaca_symbol(sym: str) -> str:
    """yfinance hyphens → Alpaca dots for share classes (BF-B → BF.B)."""
    return sym.replace("-", ".")


def _fetch_symbol(symbol: str, start: str, end: str | None) -> pd.Series | None:
    params: dict = {"timeframe": "1Day", "start": start, "adjustment": "all",
                    "feed": "sip", "limit": 10000, "sort": "asc"}
    if end is not None:
        params["end"] = end
    closes: dict[str, float] = {}
    for attempt in range(4):
        r = requests.get(f"{API_BASE}/{_alpaca_symbol(symbol)}/bars", headers=_auth_headers(),
                         params=params, timeout=_TIMEOUT_S)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        body = r.json()
        for bar in body.get("bars") or []:
            closes[bar["t"]] = float(bar["c"])
        token = body.get("next_page_token")
        if not token:
            break
        params["page_token"] = token
    else:
        raise RuntimeError(f"Alpaca rate-limited {symbol} four times")
    if not closes:
        return None
    s = pd.Series(closes, name=symbol, dtype=float)
    s.index = pd.to_datetime(s.index, utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
    return s


def get_equity_closes(
    symbols: Iterable[str], start: str = ALPACA_EQUITY_FLOOR, end: str | None = None
) -> pd.DataFrame:
    """Daily adjusted closes, yfinance-shaped: tz-naive ET DatetimeIndex, one
    column per symbol in yfinance form (BRK-B). Symbols Alpaca has no bars
    for are dropped (logged); fewer than 95% returned raises — a thin panel
    must never become the shared cache (2026-04-26 lesson)."""
    symbols = list(symbols)
    series: dict[str, pd.Series] = {}
    missing: list[str] = []
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        s = _fetch_symbol(sym, start, end)
        if s is None:
            missing.append(sym)
        else:
            series[sym] = s
        if i % 100 == 0:
            log.info(f"alpaca equity closes: {i}/{len(symbols)} symbols, {time.time() - t0:.0f}s")
        time.sleep(_THROTTLE_S)
    if missing:
        log.warning(f"alpaca equity closes: no bars for {missing}")
    if len(series) < _MIN_COVERAGE * len(symbols):
        raise RuntimeError(
            f"Alpaca returned {len(series)}/{len(symbols)} symbols — refusing to build a thin panel"
        )
    df = pd.DataFrame(series).sort_index()
    df.index.name = "Date"
    return df


def splice_banked(banked: pd.DataFrame, fresh: pd.DataFrame, overlap_end: str) -> pd.DataFrame:
    """Prepend banked history to a freshly-adjusted panel.

    Adjusted closes are re-based by every dividend, so the two segments
    disagree by a per-symbol level. For each symbol the banked segment is
    scaled by the median fresh/banked ratio over [fresh start, overlap_end],
    then the part before the fresh start is kept. Symbols only in `banked`
    stay as they are (delisted before the fresh floor); symbols only in
    `fresh` are passed through.

    A ratio that is not constant over the overlap (MAD/median above
    MAX_SEAM_DISPERSION) means the two series are different instruments —
    a reused ticker (SW: Alpaca's pre-2024 "SW" is not WestRock) or a
    reorganisation (JCI/Tyco 2016). Those symbols get no banked history
    (NaN before the fresh start) instead of a fake seam return.
    """
    if fresh.empty:
        return banked
    fresh_start = fresh.index[0]
    overlap = banked.index[(banked.index >= fresh_start) & (banked.index <= pd.Timestamp(overlap_end))]
    pre = banked.loc[banked.index < fresh_start].copy()
    for col in pre.columns:
        if col not in fresh.columns:
            continue
        both = overlap.intersection(fresh.index)
        if len(both) == 0:
            continue
        ratio = (fresh.loc[both, col] / banked.loc[both, col]).replace([float("inf"), -float("inf")], float("nan")).dropna()
        if not len(ratio):
            continue
        med = float(ratio.median())
        dispersion = float((ratio - med).abs().median() / med)   # MAD: one bad print can't trip it
        if dispersion > MAX_SEAM_DISPERSION:
            log.warning(f"splice_banked: {col} overlap ratio unstable (median {med:.3f}, "
                        f"MAD/median {dispersion:.3f}) — different instrument, dropping banked history")
            pre[col] = float("nan")
            continue
        pre[col] = pre[col] * float(ratio.median())
    out = pd.concat([pre, fresh]).sort_index()
    out.index.name = "Date"
    return out
