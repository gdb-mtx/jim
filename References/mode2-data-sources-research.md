# Mode 2 Data Sources Research

**Date:** 2026-04-15
**Purpose:** Identify free/cheap data sources for the PEAD (Post-Earnings Announcement Drift) proof-of-concept pipeline. We need three things: (1) earnings surprise data (EPS actual vs estimate), (2) earnings call transcripts (full Q&A text for Claude analysis), (3) earnings calendar (who reports when).

---

## Final Architecture — $0/month

| Need | Source | Cost | Status |
|---|---|---|---|
| **Transcripts** | Insider Monkey (scraping) | Free | Verified working |
| **EPS surprise data** | Finnhub API | Free (60 calls/min) | Verified working |
| **Earnings calendar** | Finnhub API | Free | 504 timeout on date-range query; per-symbol works |
| **Company news** | Finnhub API | Free (243 articles for JPM) | Verified working |
| **Price data** | yfinance | Free (already in project) | Existing infrastructure |
| **SEC filings** | SEC EDGAR | Free (10 req/sec) | Supplementary — press releases in 8-K exhibits |

API keys stored in `.env`:
- `FINNHUB_API_KEY` — free tier, 60 calls/min, no daily cap
- `ALPHA_VANTAGE_API_KEY` — free tier, 25 calls/day (transcripts don't work — see below)

---

## Detailed Source Evaluations

### 1. Finnhub (finnhub.io) — PRIMARY for quantitative data

**Free tier:** 60 API calls/minute, no daily cap, no credit card required.

**What works on free tier:**
- `GET /stock/earnings?symbol=JPM` — Historical EPS actual vs estimate, surprise %, by quarter. Excellent data quality. Tested JPM, GS, WFC, C, BLK — all returned accurate Q1 2026 results.
- `GET /quote?symbol=AAPL` — Real-time quotes. Works.
- `GET /company-news?symbol=JPM&from=...&to=...` — News articles. JPM returned 243 articles for a 5-day window. Good for market reaction context.

**What does NOT work on free tier:**
- `GET /stock/transcripts?symbol=JPM` — Returns `{"error": "You don't have access to this resource."}`. Transcripts are a "professional" add-on.
- `GET /calendar/earnings?from=...&to=...` — Returned 504 timeout on date-range queries. May be free-tier throttled or temporarily down. The first successful call returned data (80+ companies for one week) but subsequent calls timed out.

**What transcripts would cost:** Finnhub uses modular pricing. Transcript module is not publicly priced — requires contacting sales. Estimated $50-100/month based on GitHub issues and community reports. Enterprise "all-in-one" is ~$3,500/month. Too expensive for PoC.

**Verdict:** Excellent free source for earnings surprise data and news. Not viable for transcripts.

---

### 2. Insider Monkey (insidermonkey.com) — PRIMARY for transcripts

**Cost:** Free. No login required. No API — web scraping.

**Coverage tested (Q1 2026 earnings, all verified available):**
- JPMorgan Chase (JPM) — 12,005 words, 71,708 chars
- Goldman Sachs (GS) — available
- Citigroup (C) — available
- Wells Fargo (WFC) — available
- BlackRock (BLK) — available
- Johnson & Johnson (JNJ) — available
- Delta Air Lines (DAL) — available

**Scraping details:**
- Standard `curl` with browser User-Agent works — no JS rendering required
- Transcript is in `<article>` tag, clean HTML
- Full prepared remarks + complete Q&A section (JPM had 16 Operator turns, 28 CFO mentions, 57 question references)
- URL pattern: `insidermonkey.com/blog/{company-name-nyseTICKER}-q{N}-{YEAR}-earnings-call-transcript-{id}/`
- The trailing article ID varies — need to discover URLs via search or sitemap
- Page includes some site navigation/boilerplate at the end (fund manager tables) — needs trimming in parser

**URL discovery approach:** Google search `site:insidermonkey.com "{TICKER}" "Q1 2026 earnings call transcript"` reliably finds the correct URL. Alternatively, Insider Monkey's own search works.

**Transcript quality:** Complete verbatim transcripts including:
- Operator introductions
- CEO/CFO prepared remarks (full text)
- Q&A session with analyst names and full exchanges
- Closing remarks
- Speaker identification throughout

**Rate limiting:** No documented rate limits. Should use polite delays (1-2 sec between requests). ~10 transcripts/week is minimal load.

**Risks:**
- TOS may prohibit scraping (not explicitly tested)
- HTML structure could change (but `<article>` tag is standard)
- URL pattern requires search-based discovery (no predictable URL scheme)

**Verdict:** Best free transcript source found. Full Q&A with speaker IDs, no paywall, no JS rendering needed. Reliable S&P 500 coverage for current earnings season.

---

### 3. SEC EDGAR (sec.gov) — SUPPLEMENTARY

**Cost:** Completely free. 10 requests/second, no daily cap. Requires User-Agent header with contact email.

**What it has:**
- 8-K filings with earnings press releases (Exhibit 99.1/99.2)
- JPM's Q1 2026 press release is a rich document: $50.5B revenue, $16.5B net income, segment breakdowns, Dimon's commentary, full financial tables
- XBRL structured financial data for 10-K/10-Q
- Full-text search API: `https://efts.sec.gov/LATEST/search-index?q=...&forms=8-K`

**What it does NOT have:**
- Actual earnings call transcripts. Searched for `"earnings call transcript"` in 8-K filings — only ~6% of S&P 500 companies voluntarily file transcripts with the SEC.
- Specifically: `"earnings call transcript"` in 8-Ks returned 0 results for the current week. `"conference call transcript"` returned only 17 results for all of 2026 YTD.

**Verdict:** Useful as a supplementary source for the earnings press release (CEO commentary, guidance, financial details). Not viable as primary transcript source. The press release captures ~60-70% of the analytical signal (numbers, guidance, CEO prepared remarks) but misses the Q&A (management tone under pressure, analyst skepticism, unscripted comments).

---

### 4. Alpha Vantage (alphavantage.co) — TESTED, NOT VIABLE

**Free tier:** 25 API requests/day, 5/minute.

**Transcript endpoint:** `GET /query?function=EARNINGS_CALL_TRANSCRIPT&symbol=JPM&quarter=1&year=2026`

**Test results:** The endpoint exists and returns valid JSON structure `{"symbol": "JPM", "quarter": "1", "transcript": []}` — but the transcript array is **always empty** on the free tier. Tested JPM Q1 2026, JPM Q4 2025, AAPL Q4 2024, IBM Q3 2024 — all returned `"transcript": []`.

This appears to be a "premium endpoint" that returns empty data instead of an error on the free tier. The API documentation lists it as part of the "Alpha Intelligence" suite which may require a paid plan ($49.99-$249.99/month).

**Verdict:** Dead end for free transcript access. Key saved in `.env` in case we need other AV endpoints later.

---

### 5. Financial Modeling Prep (FMP) — NOT TESTED (requires signup)

**Free tier:** 250 API requests/day, but reportedly limited to ~100 sample symbols (AAPL, TSLA, AMZN, etc.) on the free plan.

**Paid plans:** Starting at ~$19/month for real S&P 500 coverage.

**Transcript endpoints:** Available (`/api/v3/earning_call_transcript/{symbol}`) but could not test without an API key. Demo key returned "Invalid API KEY."

**Verdict:** Cheapest paid fallback at $19/month if free sources break. Not needed for PoC since Insider Monkey works.

---

### 6. Motley Fool (fool.com) — TESTED, MIXED RESULTS

**Cost:** Free to read. No API — scraping only.

**Coverage:** S&P 500 + select companies. Transcripts are actively being posted for Q1 2026 season (PNC, ADT, IMAX, etc. found in search results).

**Scraping results:**
- Main transcript listing page (`/earnings/call-transcripts/`) returned 0 transcript links via curl — likely JS-rendered
- Direct URL guessing for JPM transcript returned 404 — URL pattern is not predictable
- Proven third-party scrapers exist on GitHub (`talsan/foolcalls`, `hamid-vakilzadeh/motley-fool-scraper`)

**Risks:** TOS explicitly prohibits scraping. Selenium/JS rendering may be required for some pages.

**Verdict:** Workable but more fragile than Insider Monkey. Insider Monkey is simpler (no JS rendering needed). Keep as backup source.

---

### 7. Other Sources Evaluated (not tested hands-on)

| Source | Cost | Transcripts? | Notes |
|---|---|---|---|
| **EarningsCall.biz** | $60/month minimum | Yes, with audio | Purpose-built API, 15-min latency. Too expensive for PoC. |
| **API Ninjas** | $39/month minimum | Yes, 8K+ companies | No free tier at all. |
| **Quartr** | Enterprise pricing | Yes, 13K companies | Contact sales. No self-serve API. |
| **Seeking Alpha** | Free to read | Yes, 4,500 calls/season | Actively blocks scrapers, JS-heavy, login required for some content. |
| **MarketBeat** | Free to read | S&P 500 | No API, browsing only. |
| **Yahoo Finance** | Free to read | Full transcripts on earnings pages | No official API (shut down 2017). Tested URL returned 404. |
| **Benzinga** | Unknown | Yes (found JPM Q1 2026) | Likely paywalled API. |
| **GuruFocus** | Unknown | Yes (found JPM Q1 2026) | Returned 403 on fetch — may require login. |

### 8. DIY Whisper + Audio Pipeline

**Concept:** Download earnings call audio from company IR pages → transcribe with OpenAI Whisper (free, local) → post-process.

**Assessment:** Technically feasible but high maintenance. Every company's IR page is different (no standard URL format). Webcasts often use third-party platforms (Verint, Chorus) with non-trivial audio extraction. Speaker diarization adds complexity. Not worth the engineering effort when free transcript text is available from Insider Monkey.

### 9. Historical Transcript Datasets (for backtesting only)

- Kaggle: `ashwinm500/earnings-call-transcripts` (NASDAQ 2016-2020)
- Kaggle: `tpotterer/motley-fool-scraped-earnings-call-transcripts`
- Kaggle: `puspendrakumar77/earning-call-scripts-us-companies-seeking-alpha`
- HuggingFace: `lamini/earnings-calls-qa` (CC-BY license)

These are historical only — useful for backtesting PEAD NLP strategies but not for live pipeline.

---

## Key Learnings

1. **Transcripts are universally paywalled in APIs.** Every financial data API (Finnhub, Alpha Vantage, FMP, EarningsCall, API Ninjas) either paywalls transcripts or makes them a premium add-on. The cheapest paid option is FMP at ~$19/month.

2. **Free transcripts exist on the web, just not via API.** Insider Monkey, Seeking Alpha, Motley Fool, and Yahoo Finance all publish full transcripts for free on their websites. The difference is scrapeability — Insider Monkey is the easiest (plain HTML, no JS rendering, no login).

3. **SEC EDGAR has press releases but not call transcripts.** Only ~6% of companies voluntarily file transcripts. The press release is detailed (especially for megacaps like JPM) but misses the Q&A.

4. **Alpha Vantage's "free" transcript endpoint is a ghost.** Returns valid JSON with empty arrays. Effectively a premium-only feature disguised as a free endpoint.

5. **Finnhub's free tier is excellent for quantitative data** (EPS surprise, news, quotes) but not for transcripts.

---

## Architecture Decision

For the PEAD proof-of-concept (Month 1, paper trading):

```
Earnings Calendar ──→ Finnhub API (per-symbol earnings query)
                      + web search for weekly calendar

Transcripts ────────→ Insider Monkey scraping (curl + article parsing)
                      Backup: Motley Fool scraping

EPS Surprise Data ──→ Finnhub API (/stock/earnings)

Company News ───────→ Finnhub API (/company-news)

Price Data ─────────→ yfinance (existing infrastructure)

SEC Filings ────────→ EDGAR API (supplementary press release data)
```

**Upgrade path:** If Insider Monkey blocks scraping or changes structure, FMP at $19/month is the fallback. If the PEAD strategy proves profitable in paper trading, $19/month is trivially justified.
