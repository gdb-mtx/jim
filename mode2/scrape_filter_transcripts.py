"""
Scrape the 47 Insider Monkey transcript URLs collected for the Mode 1 filter test.
Caches to data/mode2/transcripts/. Uses existing earnings.scrape_transcript.
"""

import json
import re
import time
from pathlib import Path

from mode2.earnings import scrape_transcript, TRANSCRIPT_DIR


URLS_PATH = Path("data/mode2/mode1_filter/transcript_urls.json")
INDEX_PATH = Path("data/mode2/mode1_filter/transcript_index.json")
SCRAPE_DELAY = 2.0


def url_to_cache_name(symbol: str, url: str) -> str:
    m = re.search(r"q(\d)-(\d{4})-earnings-call-transcript-", url)
    if m:
        return f"{symbol}_Q{m.group(1)}_{m.group(2)}.json"
    return f"{symbol}_unknown.json"


def main():
    urls = json.load(open(URLS_PATH))
    index = {}

    to_scrape = [(s, u) for s, u in urls.items() if u]
    print(f"Scraping {len(to_scrape)} transcripts...")
    print()

    for i, (sym, url) in enumerate(to_scrape, 1):
        cache_name = url_to_cache_name(sym, url)
        cache_path = TRANSCRIPT_DIR / cache_name

        if cache_path.exists():
            print(f"[{i}/{len(to_scrape)}] {sym}: cache hit ({cache_name})")
            index[sym] = cache_name
            continue

        try:
            t = scrape_transcript(url)
            TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(t, f, indent=2)
            print(f"[{i}/{len(to_scrape)}] {sym}: scraped {cache_name} ({t['word_count']} words)")
            index[sym] = cache_name
            time.sleep(SCRAPE_DELAY)
        except Exception as e:
            print(f"[{i}/{len(to_scrape)}] {sym}: FAIL {e}")
            index[sym] = None

    INDEX_PATH.write_text(json.dumps(index, indent=2, sort_keys=True))
    successful = sum(1 for v in index.values() if v)
    print()
    print(f"Done. {successful}/{len(to_scrape)} transcripts cached.")


if __name__ == "__main__":
    main()
