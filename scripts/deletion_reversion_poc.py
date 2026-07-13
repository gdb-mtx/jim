"""S&P 500 index-deletion reversion — 1-day kill test (POC).

Event stream #2 of the A5-Events candidate pool (AUDIT_FABLE §5.1).
Thesis: index funds are forced sellers on the effective date regardless of
price; deleted-but-still-trading stocks bounce over the following weeks.
(Additions are the dead side — not tested.)

Harvest: Wikipedia "List of S&P 500 companies" constituent-change table.
Tradeable deletions only — rows whose reason implies the company kept
trading (index migration / market-cap) are kept; acquisitions, mergers,
take-privates, bankruptcies are excluded (nothing to buy).

Event study: enter at close of the first trading day ON/AFTER the
effective date, hold 21/42/63 trading days, abnormal vs SPY and MDY
(deletes land in mid-cap space).

Kill criteria (fixed before first run):
  KILL      mean 63d abnormal vs MDY < +1.0% or t < 1.0
  GO        mean 63d abnormal vs MDY >= +2.0%, t >= 1.5, 2024+ mean >= 0
  MARGINAL  between
Survivorship caveat is one-directional: post-deletion delistings missing
from yfinance REMOVE losers, so a KILL is extra credible and a GO needs
the missing-count caveat.

Usage: uv run python3 scripts/deletion_reversion_poc.py [--refresh]
"""

import argparse
import io
import os
import re

import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "research_cache")
EVENTS_CSV = os.path.join(CACHE_DIR, "deletion_events.csv")
PRICES_PQ = os.path.join(CACHE_DIR, "deletion_prices.parquet")

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = {"User-Agent": "Mozilla/5.0 (research; gdborshukov@gmail.com)"}
BENCH = ["SPY", "MDY"]
HORIZONS = [21, 42, 63]
START_YEAR = 2016  # table completeness degrades earlier; 10y is plenty of N

# reasons meaning the removed company stopped trading -> no tradeable event
DEAD_RE = re.compile(
    r"acquir|merg|taken private|take.private|purchas|bought|bankrupt|"
    r"chapter 11|delist|ceased|liquidat|combin|split into",
    re.I,
)


def harvest_events() -> pd.DataFrame:
    html = requests.get(WIKI_URL, headers=UA, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    ch = tables[1].copy()
    # columns are a 2-level header: (Date, Date) (Added, Ticker) (Added,
    # Security) (Removed, Ticker) (Removed, Security) (Reason, Reason)
    ch.columns = ["date", "added", "added_name", "removed", "removed_name", "reason"]
    ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
    ch = ch.dropna(subset=["date", "removed"])
    ch = ch[ch["removed"].astype(str).str.strip().ne("")]
    ch = ch[ch["date"].dt.year >= START_YEAR]
    ch["reason"] = ch["reason"].fillna("")
    ch["tradeable"] = ~ch["reason"].str.contains(DEAD_RE)
    ch["ticker"] = ch["removed"].astype(str).str.strip().str.replace(".", "-", regex=False)
    ch = ch[ch["ticker"].str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]
    return ch[["date", "ticker", "removed_name", "reason", "tradeable"]].reset_index(drop=True)


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    todo = sorted(set(tickers) | set(BENCH))
    frames = []
    for i in range(0, len(todo), 100):
        chunk = todo[i : i + 100]
        px = yf.download(chunk, start="2015-06-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        frames.append(px)
    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    out.index = pd.to_datetime(out.index)
    return out


def event_study(events: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    idx = px.index
    recs = []
    for _, ev in events.iterrows():
        t = ev["ticker"]
        if t not in px.columns:
            recs.append({**ev, "status": "no_prices"})
            continue
        s = px[t].dropna()
        pos = idx.searchsorted(ev["date"])  # first trading day >= effective date
        if pos >= len(idx):
            recs.append({**ev, "status": "too_recent"})
            continue
        entry_day = idx[pos]
        if entry_day not in s.index or pd.isna(s.get(entry_day)):
            recs.append({**ev, "status": "no_entry_px"})
            continue
        rec = {**ev, "status": "ok", "entry_date": entry_day}
        for h in HORIZONS:
            xp = pos + h
            if xp >= len(idx) or idx[xp] not in s.index or pd.isna(s.get(idx[xp])):
                rec[f"ret_{h}"] = np.nan
                continue
            r = s[idx[xp]] / s[entry_day] - 1
            rec[f"ret_{h}"] = r
            for b in BENCH:
                br = px[b][idx[xp]] / px[b][entry_day] - 1
                rec[f"ab{b.lower()}_{h}"] = r - br
        recs.append(rec)
    return pd.DataFrame(recs)


def table(df: pd.DataFrame, col: str, by=None) -> pd.DataFrame:
    groups = [("ALL", df)] if by is None else list(df.groupby(by))
    rows = []
    for name, g in groups:
        x = g[col].dropna()
        if len(x) < 3:
            rows.append({"group": name, "N": len(x)})
            continue
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std(ddof=1) > 0 else np.nan
        rows.append(
            {
                "group": name,
                "N": len(x),
                "mean": f"{x.mean():+.2%}",
                "median": f"{x.median():+.2%}",
                "hit": f"{(x > 0).mean():.0%}",
                "t": f"{t:.2f}",
            }
        )
    return pd.DataFrame(rows).set_index("group")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.refresh or not os.path.exists(EVENTS_CSV):
        print("Harvesting Wikipedia constituent changes…")
        harvest_events().to_csv(EVENTS_CSV, index=False)
    events = pd.read_csv(EVENTS_CSV, parse_dates=["date"])
    trade = events[events["tradeable"]].copy()
    print(f"Deletions since {START_YEAR}: {len(events)} total, {len(trade)} tradeable "
          f"({len(events) - len(trade)} excluded as acquired/merged/dead)")

    if args.refresh or not os.path.exists(PRICES_PQ):
        print("Fetching prices…")
        fetch_prices(trade["ticker"].tolist()).to_parquet(PRICES_PQ)
    px = pd.read_parquet(PRICES_PQ)

    res = event_study(trade, px)
    ok = res[res["status"] == "ok"].copy()
    n_missing = (res["status"].isin(["no_prices", "no_entry_px"])).sum()
    print(f"Usable: {len(ok)} | missing prices (survivorship — removes LOSERS here): "
          f"{n_missing} ({n_missing / max(len(res), 1):.0%})")

    ok["year"] = ok["date"].dt.year
    for b in ["abspy", "abmdy"]:
        print(f"\n=== 63d abnormal vs {b[2:].upper()} ===")
        print(table(ok, f"{b}_63"))
    print("\n=== by year (vs MDY, 63d) ===")
    print(table(ok, "abmdy_63", "year"))
    print("\n=== horizon (vs MDY) ===")
    for h in HORIZONS:
        print(table(ok, f"abmdy_{h}").rename(index={"ALL": f"{h}d"}))

    x = ok["abmdy_63"].dropna()
    mean, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    recent = ok[ok["year"] >= 2024]["abmdy_63"].dropna().mean()
    print(f"\nN={len(x)} mean(abMDY,63d)={mean:+.2%} t={t:.2f} 2024+mean={recent:+.2%}")
    print("NOTE: survivorship here removes post-deletion delistings (losers) — "
          "GO would be overstated; KILL is conservative.")
    if mean >= 0.02 and t >= 1.5 and recent >= 0:
        print("VERDICT: GO — deletion stream earns a slot in the A5-Events pool.")
    elif mean < 0.01 or t < 1.0:
        print("VERDICT: KILL — no exploitable deletion bounce in our sample.")
    else:
        print("VERDICT: MARGINAL — decide with eyes open.")


if __name__ == "__main__":
    main()
