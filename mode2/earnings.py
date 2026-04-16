"""
Earnings data pipeline for Mode 2 PEAD analysis.

Data sources:
- Finnhub: EPS surprise data, company news, quotes
- Insider Monkey: Full earnings call transcripts (scraping)
- SEC EDGAR: Supplementary press release data

See References/mode2-data-sources-research.md for full source evaluation.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_BASE = "https://finnhub.io/api/v1"
TRANSCRIPT_DIR = Path("data/mode2/transcripts")

# Polite scraping delay between requests
SCRAPE_DELAY_SEC = 1.5
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ──────────────────────────────────────────────
# Finnhub: Earnings Surprise Data
# ──────────────────────────────────────────────

def get_earnings_surprise(symbol: str) -> list[dict]:
    """Get historical EPS surprise data for a symbol from Finnhub.

    Returns list of dicts with keys:
        actual, estimate, period, quarter, surprise, surprisePercent, symbol, year
    Most recent quarter first.
    """
    resp = requests.get(
        f"{FINNHUB_BASE}/stock/earnings",
        params={"symbol": symbol, "token": FINNHUB_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_current_quarter_surprise(symbol: str) -> dict | None:
    """Get the most recent quarter's earnings surprise if it matches current earnings season.

    Returns dict with surprise data, or None if not yet reported.
    """
    data = get_earnings_surprise(symbol)
    if not data:
        return None
    latest = data[0]
    # Check if this is a recent report (within last 30 days)
    period = latest.get("period", "")
    if period:
        period_date = datetime.strptime(period, "%Y-%m-%d")
        if (datetime.now() - period_date).days > 120:
            return None  # Too old, hasn't reported current quarter
    return latest


def get_company_news(symbol: str, days_back: int = 7) -> list[dict]:
    """Get recent news articles for a company from Finnhub."""
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    resp = requests.get(
        f"{FINNHUB_BASE}/company-news",
        params={
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": FINNHUB_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_quote(symbol: str) -> dict:
    """Get current quote for a symbol from Finnhub."""
    resp = requests.get(
        f"{FINNHUB_BASE}/quote",
        params={"symbol": symbol, "token": FINNHUB_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def batch_earnings_surprises(symbols: list[str], quarter: int | None = None,
                              year: int | None = None) -> list[dict]:
    """Get earnings surprise data for multiple symbols.

    Filters to specific quarter/year if provided. Respects Finnhub rate limits.
    Returns list of dicts with symbol, actual, estimate, surprisePercent, period.
    """
    results = []
    for sym in symbols:
        try:
            data = get_earnings_surprise(sym)
            if not data:
                continue
            for entry in data:
                if quarter and entry.get("quarter") != quarter:
                    continue
                if year and entry.get("year") != year:
                    continue
                results.append(entry)
                break  # Only take the matching quarter
            time.sleep(0.1)  # Stay well under 60 calls/min
        except Exception as e:
            print(f"  Warning: Failed to get earnings for {sym}: {e}")
    return results


# ──────────────────────────────────────────────
# Insider Monkey: Transcript Scraping
# ──────────────────────────────────────────────

def scrape_transcript(url: str) -> dict:
    """Scrape an earnings call transcript from Insider Monkey.

    Returns dict with keys:
        url, title, raw_text, prepared_remarks, qa_section,
        speakers, word_count, scraped_at
    """
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract article content
    article = soup.find("article")
    if not article:
        raise ValueError(f"No <article> tag found at {url}")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Get clean text from article, preserving paragraph breaks
    paragraphs = []
    for p in article.find_all(["p", "h2", "h3"]):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(text)

    raw_text = "\n\n".join(paragraphs)

    # Remove boilerplate at the end (fund manager tables, related articles)
    # These typically start with patterns like "Funds" or "Warren Buffett"
    boilerplate_markers = [
        "Funds Warren Buffett",
        "Disclosure:",
        "Want to see what other hedge funds",
        "Click here to see",
        "Insider Monkey focuses on",
    ]
    for marker in boilerplate_markers:
        idx = raw_text.find(marker)
        if idx > 0:
            raw_text = raw_text[:idx].rstrip()
            break

    # Try to split into prepared remarks and Q&A
    prepared_remarks, qa_section = _split_transcript_sections(raw_text)

    # Extract speaker names
    speakers = _extract_speakers(raw_text)

    return {
        "url": url,
        "title": title,
        "raw_text": raw_text,
        "prepared_remarks": prepared_remarks,
        "qa_section": qa_section,
        "speakers": speakers,
        "word_count": len(raw_text.split()),
        "scraped_at": datetime.now().isoformat(),
    }


def _split_transcript_sections(text: str) -> tuple[str, str]:
    """Split transcript into prepared remarks and Q&A sections."""
    # Common section markers
    qa_markers = [
        "Question-and-Answer Session",
        "Question-and-Answer",
        "Questions And Answers",
        "Q&A Session",
        "Operator: Thank you. We will now begin the question-and-answer",
        "Operator: Thank you. Our first question",
        "Operator: We will now begin the question and answer",
    ]
    for marker in qa_markers:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx].rstrip(), text[idx:].lstrip()

    # Fallback: look for the pattern where Operator introduces first question
    match = re.search(
        r"(Operator:.*?(?:first question|open the line|begin.*?Q&A))",
        text,
        re.IGNORECASE,
    )
    if match:
        idx = match.start()
        return text[:idx].rstrip(), text[idx:].lstrip()

    # Can't split — return all as prepared remarks
    return text, ""


def _extract_speakers(text: str) -> list[str]:
    """Extract unique speaker names from transcript.

    Looks for patterns like "Name:" or "Name --" at the start of paragraphs.
    """
    # Pattern: name followed by colon, typically at start of a line/paragraph
    # e.g., "Jamie Dimon:" or "Jeremy Barnum:"
    speaker_pattern = re.compile(r"^([A-Z][a-z]+ (?:[A-Z]\. )?[A-Z][a-z]+)\s*(?:--|:)", re.MULTILINE)
    speakers = list(dict.fromkeys(speaker_pattern.findall(text)))  # Deduplicate, preserve order

    # Also catch "Operator:"
    if "Operator:" in text and "Operator" not in speakers:
        speakers.insert(0, "Operator")

    return speakers


def save_transcript(transcript: dict, symbol: str, quarter: int, year: int) -> Path:
    """Save scraped transcript to disk as JSON."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_Q{quarter}_{year}.json"
    path = TRANSCRIPT_DIR / filename
    with open(path, "w") as f:
        json.dump(transcript, f, indent=2)
    return path


def load_transcript(symbol: str, quarter: int, year: int) -> dict | None:
    """Load a previously saved transcript, or None if not cached."""
    path = TRANSCRIPT_DIR / f"{symbol}_Q{quarter}_{year}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


# ──────────────────────────────────────────────
# SEC EDGAR: Press Release Data (supplementary)
# ──────────────────────────────────────────────

EDGAR_HEADERS = {"User-Agent": "FIRE Trading gdborshukov@gmail.com"}


def search_edgar_filings(company_name: str, form_type: str = "8-K",
                          days_back: int = 14) -> list[dict]:
    """Search SEC EDGAR for recent filings."""
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    resp = requests.get(
        "https://efts.sec.gov/LATEST/search-index",
        params={
            "q": f'"{company_name}" "earnings"',
            "forms": form_type,
            "dateRange": "custom",
            "startdt": from_date,
            "enddt": to_date,
        },
        headers=EDGAR_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("hits", {}).get("hits", [])


# ──────────────────────────────────────────────
# Convenience: Weekly Earnings Summary
# ──────────────────────────────────────────────

def get_weekly_earnings_summary(symbols: list[str], quarter: int,
                                 year: int) -> list[dict]:
    """Get earnings summary for a list of symbols.

    Returns enriched data: EPS surprise + current price + basic news count.
    """
    results = []
    for sym in symbols:
        try:
            surprise = get_current_quarter_surprise(sym)
            if not surprise or surprise.get("actual") is None:
                continue

            quote = get_quote(sym)
            news = get_company_news(sym, days_back=7)
            earnings_news = [n for n in news if "earning" in n.get("headline", "").lower()]

            results.append({
                "symbol": sym,
                "quarter": surprise.get("quarter"),
                "year": surprise.get("year"),
                "eps_actual": surprise.get("actual"),
                "eps_estimate": surprise.get("estimate"),
                "eps_surprise_pct": surprise.get("surprisePercent"),
                "current_price": quote.get("c"),
                "price_change_pct": quote.get("dp"),
                "news_count": len(news),
                "earnings_news_count": len(earnings_news),
            })
            time.sleep(0.2)  # Respect rate limits
        except Exception as e:
            print(f"  Warning: {sym} failed: {e}")

    # Sort by absolute surprise magnitude (most surprising first)
    results.sort(key=lambda x: abs(x.get("eps_surprise_pct", 0)), reverse=True)
    return results


if __name__ == "__main__":
    # Quick test
    print("Testing Finnhub connection...")
    jpm = get_earnings_surprise("JPM")
    if jpm:
        latest = jpm[0]
        print(f"  JPM Q{latest['quarter']} {latest['year']}: "
              f"${latest['actual']} vs ${latest['estimate']} "
              f"({latest['surprisePercent']:+.1f}% surprise)")
    else:
        print("  No data returned")

    print("\nTesting Insider Monkey scraper...")
    url = "https://www.insidermonkey.com/blog/jpmorgan-chase-co-nysejpm-q1-2026-earnings-call-transcript-1738721/"
    transcript = scrape_transcript(url)
    print(f"  Title: {transcript['title']}")
    print(f"  Word count: {transcript['word_count']:,}")
    print(f"  Speakers: {transcript['speakers']}")
    print(f"  Has Q&A: {'Yes' if transcript['qa_section'] else 'No'}")
    print(f"  Prepared remarks: {len(transcript['prepared_remarks']):,} chars")
    print(f"  Q&A section: {len(transcript['qa_section']):,} chars")
