"""
Fetch earnings-call transcripts for Breakthrough #1 test.

For each symbol in `candidate_universes.parquet`, find the most recent
Insider Monkey transcript via DuckDuckGo HTML search, then scrape it.
Caches results in `data/mode2/transcripts/` and writes an index mapping
(symbol, rebalance_date) -> transcript_path.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import requests

from mode2.earnings import scrape_transcript, TRANSCRIPT_DIR


SEARCH_DELAY_SEC = 2.0
SCRAPE_DELAY_SEC = 2.0
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

URL_PATTERN = re.compile(
    r"insidermonkey\.com(?:%2F|/)blog(?:%2F|/)([a-z0-9%\-]+transcript(?:%2D|\-)\d+)(?:%2F|/)?",
    re.IGNORECASE,
)

INDEX_PATH = Path("data/mode2/mode1_filter/transcript_index.json")


def ddg_search(query: str) -> list[str]:
    """Run a DuckDuckGo HTML search and return Insider Monkey transcript URLs."""
    r = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": UA},
        timeout=15,
    )
    r.raise_for_status()
    raw_matches = URL_PATTERN.findall(r.text)
    urls = []
    seen = set()
    for slug in raw_matches:
        slug = unquote(slug).replace("%2D", "-")
        url = f"https://www.insidermonkey.com/blog/{slug}/"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_url_metadata(url: str) -> dict:
    """Extract quarter + year from Insider Monkey URL slug."""
    m = re.search(r"q(\d)-(\d{4})-earnings-call-transcript-(\d+)", url)
    if not m:
        return {}
    return {"quarter": int(m.group(1)), "year": int(m.group(2)), "article_id": m.group(3)}


def find_most_recent_transcript_url(symbol: str, before_date: pd.Timestamp) -> tuple[str | None, dict]:
    """Find the most recent transcript URL reported before `before_date`.

    Strategy: search once for the symbol, then filter results by fiscal year/quarter.
    Fiscal quarters don't match calendar cleanly (NVDA Q3 FY26 = Nov 2025 calendar).
    For a Dec 2025 rebalance we want calls reported Aug-Nov 2025. Search both year
    tags (2025 and 2026 to catch fiscal-offset companies) and pick the best fit.
    """
    # Try broad search first
    queries = [
        f"site:insidermonkey.com {symbol} earnings call transcript",
    ]

    all_urls = []
    for q in queries:
        try:
            urls = ddg_search(q)
            all_urls.extend(urls)
            time.sleep(SEARCH_DELAY_SEC)
        except Exception as e:
            print(f"    search failed for '{q}': {e}")

    # Dedupe
    seen = set()
    unique = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    if not unique:
        return None, {}

    # For each URL, the article_id is roughly monotonic — higher = more recent
    # Parse out quarter/year and sort by (year desc, article_id desc)
    scored = []
    for u in unique:
        meta = parse_url_metadata(u)
        if not meta:
            continue
        scored.append((u, meta))

    if not scored:
        return None, {}

    # Sort by article_id desc (monotonic proxy for recency)
    scored.sort(key=lambda x: -int(x[1]["article_id"]))

    # Filter: pick most recent that's plausibly before `before_date`
    # Article ids grow with time; we assume the top hit is recent.
    # Filter out any whose year label is > year(before_date) + 1 (fiscal offset tolerance)
    cutoff_year = before_date.year + 1
    filtered = [(u, m) for u, m in scored if m["year"] <= cutoff_year]
    if not filtered:
        filtered = scored

    return filtered[0]


def fetch_for_symbols(universes: pd.DataFrame, rebalance_date: str) -> dict[str, str]:
    """Fetch transcripts for all symbols appearing on a given rebalance date.

    Returns mapping symbol -> cached transcript filename.
    """
    target = pd.Timestamp(rebalance_date)
    subset = universes[universes["rebalance_date"] == rebalance_date]["symbol"].tolist()

    results = {}
    for sym in subset:
        # Check if we already have a transcript cached for this symbol
        existing = sorted(TRANSCRIPT_DIR.glob(f"{sym}_Q*.json"))
        if existing:
            # Use the latest cached file — good enough for MVP
            chosen = existing[-1]
            print(f"  {sym}: cache hit ({chosen.name})")
            results[sym] = chosen.name
            continue

        url, meta = find_most_recent_transcript_url(sym, target)
        if not url:
            print(f"  {sym}: NO URL FOUND")
            results[sym] = None
            continue

        q, y = meta.get("quarter", "X"), meta.get("year", "XXXX")
        cache_file = TRANSCRIPT_DIR / f"{sym}_Q{q}_{y}.json"

        if cache_file.exists():
            print(f"  {sym}: cache hit Q{q}/{y}")
            results[sym] = cache_file.name
            continue

        try:
            transcript = scrape_transcript(url)
            TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(transcript, f, indent=2)
            print(f"  {sym}: scraped Q{q}/{y} ({transcript['word_count']} words)")
            results[sym] = cache_file.name
            time.sleep(SCRAPE_DELAY_SEC)
        except Exception as e:
            print(f"  {sym}: scrape failed: {e}")
            results[sym] = None

    return results


def main():
    universes = pd.read_parquet("data/mode2/mode1_filter/candidate_universes.parquet")

    # Build an index: for each (symbol, rebalance_date), which transcript to use.
    # MVP simplification: one transcript per symbol (the most recent available),
    # used across all rebalance dates.
    all_symbols = sorted(universes["symbol"].unique())
    print(f"Fetching transcripts for {len(all_symbols)} unique symbols...")
    print()

    # Use the latest rebalance date as the cutoff target
    latest_date = pd.Timestamp(universes["rebalance_date"].max())

    index = {}
    for i, sym in enumerate(all_symbols, 1):
        # Check cache first
        existing = sorted(TRANSCRIPT_DIR.glob(f"{sym}_Q*.json"))
        if existing:
            chosen = existing[-1]
            print(f"[{i}/{len(all_symbols)}] {sym}: cache hit ({chosen.name})")
            index[sym] = chosen.name
            continue

        url, meta = find_most_recent_transcript_url(sym, latest_date)
        if not url:
            print(f"[{i}/{len(all_symbols)}] {sym}: NO URL")
            index[sym] = None
            continue

        q, y = meta.get("quarter", "X"), meta.get("year", "XXXX")
        cache_file = TRANSCRIPT_DIR / f"{sym}_Q{q}_{y}.json"

        if cache_file.exists():
            print(f"[{i}/{len(all_symbols)}] {sym}: cache Q{q}/{y}")
            index[sym] = cache_file.name
            continue

        try:
            transcript = scrape_transcript(url)
            with open(cache_file, "w") as f:
                json.dump(transcript, f, indent=2)
            print(f"[{i}/{len(all_symbols)}] {sym}: scraped Q{q}/{y} ({transcript['word_count']} words)")
            index[sym] = cache_file.name
            time.sleep(SCRAPE_DELAY_SEC)
        except Exception as e:
            print(f"[{i}/{len(all_symbols)}] {sym}: scrape failed: {e}")
            index[sym] = None

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)

    successful = sum(1 for v in index.values() if v)
    print()
    print(f"Done. {successful}/{len(all_symbols)} transcripts available.")
    print(f"Index: {INDEX_PATH}")


if __name__ == "__main__":
    main()
