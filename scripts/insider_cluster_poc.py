"""Insider cluster buying — 1-day kill test (POC).

Event stream #4 (the strongest-documented) of the A5-Events candidate pool
(AUDIT_FABLE §5.1). Thesis (Lakonishok-Lee 2001): 3+ distinct officers/
directors buying their own stock open-market within a month is the
highest-conviction insider signal; historically +6-9% abnormal over 6
months, concentrated in smaller caps.

Data: SEC insider-transactions structured datasets (quarterly ZIPs,
2022q1-2026q1, already in data/research_cache/form345/). Form 4 only,
transaction code P (open-market purchase), acquired, price>0,
value >= $25K, owner is Director or Officer.

Cluster event: >= 3 distinct owner CIKs purchasing within a trailing 30
calendar days for one issuer. Event date = FILING_DATE of the triggering
purchase (the moment the cluster becomes publicly knowable). Same-issuer
events suppressed for 90 days after a fire.

Event study: entry T+1 trading day after event date; holds 63 and 126
trading days; abnormal vs SPY and MDY. Cap band from current shares x
entry price (split-safe approximation, same as buyback POC).

Kill criteria (fixed before first run), keyed on the $200M-$5B target
band, 126d hold, vs MDY:
  GO        mean >= +3.0%, t >= 1.5, 2024+ mean >= 0
  KILL      mean < +1.0% or t < 1.0
  MARGINAL  between

Usage: uv run python3 scripts/insider_cluster_poc.py [--refresh]
"""

import argparse
import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "research_cache")
ZIP_DIR = os.path.join(CACHE_DIR, "form345")
EVENTS_CSV = os.path.join(CACHE_DIR, "insider_cluster_events.csv")
SHARES_CSV = os.path.join(CACHE_DIR, "insider_cluster_shares.csv")
PRICES_PQ = os.path.join(CACHE_DIR, "insider_cluster_prices.parquet")

MIN_DOLLARS = 25_000
MIN_INSIDERS = 3
CLUSTER_DAYS = 30
SUPPRESS_DAYS = 90
BENCH = ["SPY", "MDY"]
HORIZONS = [63, 126]


def _read_tsv(zf: zipfile.ZipFile, name: str, usecols: list[str]) -> pd.DataFrame:
    with zf.open(name) as f:
        return pd.read_csv(
            io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
            sep="\t", usecols=usecols, low_memory=False,
        )


def harvest_events() -> pd.DataFrame:
    buys = []
    for fn in sorted(os.listdir(ZIP_DIR)):
        if not fn.endswith(".zip"):
            continue
        with zipfile.ZipFile(os.path.join(ZIP_DIR, fn)) as zf:
            sub = _read_tsv(zf, "SUBMISSION.tsv",
                            ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
                             "ISSUERCIK", "ISSUERTRADINGSYMBOL"])
            own = _read_tsv(zf, "REPORTINGOWNER.tsv",
                            ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"])
            trn = _read_tsv(zf, "NONDERIV_TRANS.tsv",
                            ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE",
                             "TRANS_ACQUIRED_DISP_CD", "TRANS_SHARES", "TRANS_PRICEPERSHARE"])
        sub = sub[sub["DOCUMENT_TYPE"].astype(str).str.strip() == "4"]
        trn = trn[
            (trn["TRANS_CODE"] == "P")
            & (trn["TRANS_ACQUIRED_DISP_CD"] == "A")
            & (trn["TRANS_SHARES"] > 0)
            & (trn["TRANS_PRICEPERSHARE"] > 0)
        ].copy()
        trn["dollars"] = trn["TRANS_SHARES"] * trn["TRANS_PRICEPERSHARE"]
        trn = trn[trn["dollars"] >= MIN_DOLLARS]
        own = own[own["RPTOWNER_RELATIONSHIP"].astype(str).str.contains(
            "Director|Officer", case=False, na=False)]
        df = trn.merge(sub, on="ACCESSION_NUMBER").merge(
            own[["ACCESSION_NUMBER", "RPTOWNERCIK"]], on="ACCESSION_NUMBER")
        buys.append(df[["ISSUERCIK", "ISSUERTRADINGSYMBOL", "FILING_DATE",
                        "RPTOWNERCIK", "dollars"]])
        print(f"  {fn}: {len(df)} qualifying purchases")
    allb = pd.concat(buys, ignore_index=True)
    allb["FILING_DATE"] = pd.to_datetime(allb["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
    allb = allb.dropna(subset=["FILING_DATE"])
    allb["ticker"] = (
        allb["ISSUERTRADINGSYMBOL"].astype(str).str.strip().str.upper()
        .str.replace(".", "-", regex=False)
    )
    allb = allb[allb["ticker"].str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]

    # cluster detection per issuer
    events = []
    for (cik, tkr), g in allb.groupby(["ISSUERCIK", "ticker"]):
        g = g.sort_values("FILING_DATE")
        dates = g["FILING_DATE"].to_numpy()
        owners = g["RPTOWNERCIK"].to_numpy()
        dollars = g["dollars"].to_numpy()
        suppress_until = None
        for i in range(len(g)):
            d = dates[i]
            if suppress_until is not None and d < suppress_until:
                continue
            lo = d - np.timedelta64(CLUSTER_DAYS, "D")
            win = (dates >= lo) & (dates <= d)
            n_own = len(set(owners[win]))
            if n_own >= MIN_INSIDERS:
                events.append({
                    "ticker": tkr, "cik": cik, "event_date": pd.Timestamp(d),
                    "n_insiders": n_own, "window_dollars": float(dollars[win].sum()),
                })
                suppress_until = d + np.timedelta64(SUPPRESS_DAYS, "D")
    ev = pd.DataFrame(events).sort_values("event_date").reset_index(drop=True)
    return ev


def fetch_shares(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    def one(t):
        try:
            return t, float(yf.Ticker(t).fast_info["shares"])
        except Exception:
            return t, np.nan

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(one, tickers))
    return pd.DataFrame(out, columns=["ticker", "shares"])


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    todo = sorted(set(tickers) | set(BENCH))
    frames = []
    for i in range(0, len(todo), 100):
        chunk = todo[i : i + 100]
        px = yf.download(chunk, start="2021-06-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        frames.append(px)
        print(f"  prices {i + len(chunk)}/{len(todo)}", flush=True)
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
        pos = idx.searchsorted(ev["event_date"]) + 1  # T+1 after filing
        if pos >= len(idx):
            recs.append({**ev, "status": "too_recent"})
            continue
        eday = idx[pos]
        if eday not in s.index or pd.isna(s.get(eday)):
            recs.append({**ev, "status": "no_entry_px"})
            continue
        rec = {**ev, "status": "ok", "entry_date": eday, "entry_px": s[eday]}
        for h in HORIZONS:
            xp = pos + h
            if xp >= len(idx) or idx[xp] not in s.index or pd.isna(s.get(idx[xp])):
                rec[f"ret_{h}"] = np.nan
                continue
            r = s[idx[xp]] / s[eday] - 1
            rec[f"ret_{h}"] = r
            for b in BENCH:
                br = px[b][idx[xp]] / px[b][eday] - 1
                rec[f"ab{b.lower()}_{h}"] = r - br
        recs.append(rec)
    return pd.DataFrame(recs)


def bucket(cap):
    if pd.isna(cap):
        return "unknown"
    if cap < 200e6:
        return "micro<200M"
    if cap <= 5e9:
        return "target200M-5B"
    if cap <= 20e9:
        return "mid5-20B"
    return "large>20B"


def table(df: pd.DataFrame, col: str, by=None) -> pd.DataFrame:
    groups = [("ALL", df)] if by is None else list(df.groupby(by))
    rows = []
    for name, g in groups:
        x = g[col].dropna()
        if len(x) < 3:
            rows.append({"group": name, "N": len(x)})
            continue
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std(ddof=1) > 0 else np.nan
        rows.append({
            "group": name, "N": len(x), "mean": f"{x.mean():+.2%}",
            "median": f"{x.median():+.2%}", "hit": f"{(x > 0).mean():.0%}",
            "t": f"{t:.2f}",
        })
    return pd.DataFrame(rows).set_index("group")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.refresh or not os.path.exists(EVENTS_CSV):
        print("Parsing Form 4 datasets…")
        harvest_events().to_csv(EVENTS_CSV, index=False)
    events = pd.read_csv(EVENTS_CSV, parse_dates=["event_date"])
    print(f"Cluster events: {len(events)} across {events['ticker'].nunique()} tickers; "
          f"per year: {events['event_date'].dt.year.value_counts().sort_index().to_dict()}")

    if args.refresh or not os.path.exists(SHARES_CSV):
        print("Fetching shares outstanding…")
        fetch_shares(sorted(events["ticker"].unique())).to_csv(SHARES_CSV, index=False)
    shares = pd.read_csv(SHARES_CSV).set_index("ticker")["shares"]

    if args.refresh or not os.path.exists(PRICES_PQ):
        print("Fetching prices…")
        fetch_prices(events["ticker"].tolist()).to_parquet(PRICES_PQ)
    px = pd.read_parquet(PRICES_PQ)

    res = event_study(events, px)
    ok = res[res["status"] == "ok"].copy()
    n_missing = res["status"].isin(["no_prices", "no_entry_px"]).sum()
    print(f"Usable: {len(ok)} | missing prices (survivorship): {n_missing} "
          f"({n_missing / max(len(res), 1):.0%}) | too recent: "
          f"{(res['status'] == 'too_recent').sum()}")

    ok["cap"] = ok.apply(lambda r: shares.get(r["ticker"], np.nan) * r["entry_px"], axis=1)
    ok["bucket"] = ok["cap"].map(bucket)
    ok["year"] = ok["event_date"].dt.year

    for h in HORIZONS:
        print(f"\n=== {h}d abnormal vs MDY, by cap bucket ===")
        print(table(ok, f"abmdy_{h}", "bucket"))
    tgt = ok[ok["bucket"] == "target200M-5B"]
    print("\n=== TARGET band by year (vs MDY, 126d) ===")
    print(table(tgt, "abmdy_126", "year"))
    print("\n=== TARGET band vs SPY (126d) ===")
    print(table(tgt, "abspy_126"))
    print("\n=== TARGET band by n_insiders (vs MDY, 126d) ===")
    print(table(tgt, "abmdy_126", tgt["n_insiders"].clip(upper=5)))

    x = tgt["abmdy_126"].dropna()
    if len(x) < 10:
        print(f"\nTarget-band N={len(x)} — too thin to verdict.")
        return
    mean, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    recent = tgt[tgt["year"] >= 2024]["abmdy_126"].dropna().mean()
    print(f"\nTARGET band N={len(x)} mean(abMDY,126d)={mean:+.2%} t={t:.2f} "
          f"2024+mean={recent:+.2%}")
    print("NOTE: overlapping windows + clustering inflate t; survivorship removes "
          "delisted losers. Both favor GO — KILL is conservative.")
    if mean >= 0.03 and t >= 1.5 and recent >= 0:
        print("VERDICT: GO — the anchor stream for A5-Events exists.")
    elif mean < 0.01 or t < 1.0:
        print("VERDICT: KILL — cluster buying carries no exploitable drift in our sample.")
    else:
        print("VERDICT: MARGINAL — decide with eyes open.")


if __name__ == "__main__":
    main()
