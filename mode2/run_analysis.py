"""
Weekly PEAD analysis runner.

Usage:
    # Fetch earnings data + transcripts for this week's reporters
    uv run python3 -m mode2.run_analysis fetch --symbols JPM,GS,C,WFC,BLK

    # Show summary of fetched data
    uv run python3 -m mode2.run_analysis summary

    # Generate analysis context for Claude (in-conversation or API)
    uv run python3 -m mode2.run_analysis analyze --symbol JPM

    # Show recommendation tracker status
    uv run python3 -m mode2.run_analysis status
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from mode2.earnings import (
    get_current_quarter_surprise,
    get_quote,
    get_company_news,
    scrape_transcript,
    save_transcript,
    load_transcript,
)
from mode2.pead import format_pead_prompt, format_quick_prompt
from mode2.tracker import load_recommendations, summary_stats, get_open_recommendations

# Known transcript URLs for this week (discovered via search)
# In production, URL discovery would be automated
TRANSCRIPT_URLS = {
    # Q1 2026 earnings - Week of April 14 (Mon)
    "JPM": "https://www.insidermonkey.com/blog/jpmorgan-chase-co-nysejpm-q1-2026-earnings-call-transcript-1738721/",
    "GS": "https://www.insidermonkey.com/blog/the-goldman-sachs-group-inc-nysegs-q1-2026-earnings-call-transcript-1737974/",
    "C": "https://www.insidermonkey.com/blog/citigroup-inc-nysec-q1-2026-earnings-call-transcript-1738725/",
    "WFC": "https://www.insidermonkey.com/blog/wells-fargo-company-nysewfc-q1-2026-earnings-call-transcript-1738730/",
    "BLK": "https://www.insidermonkey.com/blog/blackrock-inc-nyseblk-q1-2026-earnings-call-transcript-1738734/",
    "JNJ": "https://www.insidermonkey.com/blog/johnson-johnson-nysejnj-q1-2026-earnings-call-transcript-1738732/",
    # Q1 2026 earnings - Week of April 14 (Tue/Wed) — URLs TBD, check Insider Monkey
    # BAC: +8.6% surprise — reported Apr 15
    # MS: +10.9% surprise — reported Apr 15
    # PNC: +5.5% surprise — reported Apr 15
    # SCHW, UNH, ABT, NFLX — not yet reported
}


def cmd_fetch(symbols: list[str], quarter: int, year: int):
    """Fetch earnings data and transcripts for given symbols."""
    print(f"=== Fetching Q{quarter} {year} earnings data ===\n")

    for sym in symbols:
        print(f"--- {sym} ---")

        # 1. Earnings surprise from Finnhub
        surprise = get_current_quarter_surprise(sym)
        if not surprise or surprise.get("actual") is None:
            print(f"  No Q{quarter} {year} earnings data yet. Skipping.")
            continue

        print(f"  EPS: ${surprise['actual']} vs ${surprise['estimate']} "
              f"({surprise['surprisePercent']:+.1f}% surprise)")

        # 2. Current quote
        quote = get_quote(sym)
        print(f"  Price: ${quote['c']} ({quote['dp']:+.1f}% today)")

        # 3. Transcript
        cached = load_transcript(sym, quarter, year)
        if cached:
            print(f"  Transcript: cached ({cached['word_count']:,} words)")
        elif sym in TRANSCRIPT_URLS:
            print(f"  Scraping transcript from Insider Monkey...")
            try:
                transcript = scrape_transcript(TRANSCRIPT_URLS[sym])
                path = save_transcript(transcript, sym, quarter, year)
                print(f"  Transcript: {transcript['word_count']:,} words, "
                      f"{len(transcript['speakers'])} speakers")
                print(f"  Speakers: {', '.join(transcript['speakers'][:5])}")
                print(f"  Saved to: {path}")
            except Exception as e:
                print(f"  Transcript scrape failed: {e}")
        else:
            print(f"  No transcript URL known for {sym}. Add to TRANSCRIPT_URLS.")

        # 4. News summary
        news = get_company_news(sym, days_back=7)
        earnings_news = [n for n in news if "earning" in n.get("headline", "").lower()]
        print(f"  News: {len(news)} articles ({len(earnings_news)} earnings-related)")
        print()


def cmd_summary(quarter: int, year: int):
    """Show summary of all fetched data."""
    print(f"=== Q{quarter} {year} Earnings Data Summary ===\n")

    transcript_dir = Path("data/mode2/transcripts")
    if not transcript_dir.exists():
        print("No transcripts fetched yet. Run 'fetch' first.")
        return

    transcripts = list(transcript_dir.glob(f"*_Q{quarter}_{year}.json"))
    print(f"Transcripts cached: {len(transcripts)}\n")

    for path in sorted(transcripts):
        with open(path) as f:
            t = json.load(f)
        sym = path.stem.split("_")[0]
        surprise = get_current_quarter_surprise(sym)
        eps_str = ""
        if surprise and surprise.get("actual") is not None:
            eps_str = (f"EPS ${surprise['actual']} vs ${surprise['estimate']} "
                      f"({surprise['surprisePercent']:+.1f}%)")

        has_qa = "Yes" if t.get("qa_section") else "No"
        print(f"  {sym:5s} | {t['word_count']:,} words | Q&A: {has_qa} | "
              f"Speakers: {len(t['speakers'])} | {eps_str}")


def cmd_analyze(symbol: str, quarter: int, year: int):
    """Generate PEAD analysis prompt for a specific company.

    Outputs the full prompt to stdout — paste into Claude conversation
    or pipe to Claude API.
    """
    # Load transcript
    transcript = load_transcript(symbol, quarter, year)
    if not transcript:
        print(f"No transcript cached for {symbol} Q{quarter} {year}. Run 'fetch' first.",
              file=sys.stderr)
        sys.exit(1)

    # Get earnings data
    surprise = get_current_quarter_surprise(symbol)
    if not surprise:
        print(f"No earnings data for {symbol}.", file=sys.stderr)
        sys.exit(1)

    quote = get_quote(symbol)

    # Format the prompt
    prompt = format_pead_prompt(
        symbol=symbol,
        quarter=quarter,
        year=year,
        eps_actual=surprise["actual"],
        eps_estimate=surprise["estimate"],
        surprise_pct=surprise["surprisePercent"],
        current_price=quote["c"],
        transcript_text=transcript["raw_text"],
    )

    print(prompt)


def cmd_status():
    """Show recommendation tracker status."""
    recs = load_recommendations()
    if not recs:
        print("No recommendations logged yet.")
        return

    stats = summary_stats()
    print(f"=== Recommendation Tracker ===\n")
    print(f"Total: {stats['total']}  |  Open: {stats['open']}  |  Closed: {stats['closed']}")

    if stats["closed"] > 0:
        print(f"\nHit rate: {stats['hit_rate']:.0f}%  "
              f"({stats['winners']}W / {stats['losers']}L)")
        print(f"Avg winner: {stats['avg_winner_pct']:+.1f}%  |  "
              f"Avg loser: {stats['avg_loser_pct']:+.1f}%")
        print(f"Total P&L: ${stats['total_pnl']:,.2f}")

        if stats.get("by_conviction"):
            print(f"\nBy conviction level:")
            for conv in sorted(stats["by_conviction"]):
                c = stats["by_conviction"][conv]
                print(f"  {conv}/5: {c['hit_rate']:.0f}% hit rate ({c['total']} trades)")

    open_recs = get_open_recommendations()
    if open_recs:
        print(f"\nOpen positions:")
        for r in open_recs:
            days = (datetime.now() - datetime.fromisoformat(r["logged_at"])).days
            print(f"  {r['symbol']:5s} | {r.get('direction','?'):5s} | "
                  f"Conv: {r.get('conviction','?')}/5 | "
                  f"Day {days}/{r.get('hold_days', '?')} | "
                  f"Entry: ${r.get('entry_price', '?')} | "
                  f"Stop: ${r.get('stop_loss', '?')} | "
                  f"Target: ${r.get('target_price', '?')}")


def main():
    parser = argparse.ArgumentParser(description="Mode 2 PEAD Analysis Runner")
    sub = parser.add_subparsers(dest="command")

    # fetch
    fetch_p = sub.add_parser("fetch", help="Fetch earnings data and transcripts")
    fetch_p.add_argument("--symbols", required=True, help="Comma-separated symbols")
    fetch_p.add_argument("--quarter", type=int, default=1)
    fetch_p.add_argument("--year", type=int, default=2026)

    # summary
    summary_p = sub.add_parser("summary", help="Show fetched data summary")
    summary_p.add_argument("--quarter", type=int, default=1)
    summary_p.add_argument("--year", type=int, default=2026)

    # analyze
    analyze_p = sub.add_parser("analyze", help="Generate PEAD analysis prompt")
    analyze_p.add_argument("--symbol", required=True)
    analyze_p.add_argument("--quarter", type=int, default=1)
    analyze_p.add_argument("--year", type=int, default=2026)

    # status
    sub.add_parser("status", help="Show recommendation tracker status")

    args = parser.parse_args()
    if args.command == "fetch":
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
        cmd_fetch(symbols, args.quarter, args.year)
    elif args.command == "summary":
        cmd_summary(args.quarter, args.year)
    elif args.command == "analyze":
        cmd_analyze(args.symbol.upper(), args.quarter, args.year)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
