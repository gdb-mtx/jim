# FIRE Trading System: Two-Mode Architecture

## Reframing

This isn't a hobby project and it isn't desperation either. It's a calculated bet: George has 76 months until 59½, a bridge plan that works (SEPP + RRIF + rental = ~$9.8K/mo), and ~$50K of investable capital. The bridge covers survival. The trading system's job is to compound that $50K at materially better than SPY over 6 years — turning it into $100-150K by 59½ when the retirement accounts unlock.

$50K at 10% for 6 years = $88K. At 15% = $116K. At 20% = $149K. The difference between 10% (slightly above SPY) and 20% (real alpha) is $61K — meaningful money during the bridge. But a -30% drawdown at the wrong time = $15K gone from an already tight cash position. Risk management isn't optional — it's the difference between "this was smart" and "this was reckless."

**The honest constraint:** We cannot afford to lose principal in the first 12 months while the bridge is tightest. After planned asset sales land through late 2026, cash stabilizes. So the trading system should be conservative in months 1-6, then can take more risk as the cash cushion builds.

---

## The Two Modes

### Mode 1: Structural Alpha (5-10yr horizon) — THE FOUNDATION

What we built: 4-account factor diversification (momentum, trend+low-vol, reversal, crypto). Fully automated. Running on Alpaca paper.

**Honest assessment after 5 weeks:**
- Mechanically excellent. Filters fire, orders execute, circuit breakers work.
- Alpha is thin. Factor premiums are published and crowded (McLean & Pontiff 2016: 58% decay).
- The system's value may be less about alpha and more about **disciplined, diversified exposure** — it won't blow up, it rebalances automatically, it manages risk.
- Accounts 1 & 3 are too correlated (0.87 live vs 0.56 backtest). Needs investigation.

**Role going forward:** Steady base that compounds at roughly market rate with lower drawdowns. The SPY filter + circuit breakers protect capital during crashes. This is the "money working while you sleep" layer.

**What's still promising:**
- Account 4 (crypto) sitting in cash with BTC at $70K vs $95K 200d MA. When BTC crosses back above, this strategy captured 356% (2023-2024 bull). Patient capital waiting for the right moment.
- The filter monitor (just built) means we'll react same-day to regime changes going forward.

### Mode 2: Informational Alpha (1-3yr strategy horizon) — THE EDGE

**What makes this different from Mode 1:**
- Mode 1 exploits price patterns that are decades old and well-published
- Mode 2 exploits Claude's ability to REASON about new information — this capability is 2 years old, there's no McLean & Pontiff paper on it, it's not crowded
- Mode 1 is backtestable. Mode 2 largely isn't (the tool didn't exist historically). That's a weakness for validation but a STRENGTH for alpha — you can't arbitrage away an edge you can't backtest for.

**The core thesis:** In a world where every quant has the same price data and the same factor models, the edge is in INTERPRETATION of new information. 500 S&P stocks report earnings every quarter. No human reads all 500 transcripts. No traditional quant model understands management tone, guidance quality, or the difference between a revenue-driven beat and a cost-cutting beat. Claude can. That's the edge — breadth of coverage at depth of analysis.

---

## Mode 2: Design

### Signal Source 1: PEAD (Post-Earnings Announcement Drift) — PRIMARY

The most robust short-term anomaly in finance. Ball & Brown (1968), still profitable 58 years later. After an earnings surprise, stocks drift 3-8% over 60-90 days in the surprise direction. The drift is strongest when:
- The surprise is QUALITY (revenue-driven, not one-time items)
- The guidance changes but analysts haven't fully updated models
- The market misclassifies the surprise (e.g., "earnings miss" that was actually a strategic investment quarter)

**Traditional approach:** Standardized Unexpected Earnings (SUE) = simple number comparison.

**Our edge — what Claude adds:**
- Read the full earnings call transcript (not just headline EPS)
- Score surprise QUALITY: revenue growth vs cost-cutting vs one-time items
- Detect guidance shifts that analysts haven't priced
- Identify management tone changes: confidence vs hedging vs deflection
- Cross-reference with sector peers: is this company-specific or industry-wide?
- Flag the 5-10 best opportunities out of 80+ earnings per week

**Position mechanics:**
- Entry: day after earnings (avoid overnight earnings gap risk)
- Hold: 20-60 days (the drift window)
- Exit: time-based (auto-close at 60 days) or target hit (take profit at 8%)
- Stop: -5% from entry (hard stop, no exceptions)
- Size: 3-5% of portfolio per position ($1.5-2.5K at $50K)
- Max concurrent: 10-12 positions (30-60% of capital deployed at peak)

### Signal Source 2: Macro Regime Overlay

Weekly macro assessment that influences BOTH modes:

**What Claude analyzes:**
- Fed communications and rate path expectations
- Credit spreads (HY OAS) — historically leads equity by 2-4 weeks
- VIX term structure: contango (calm) vs backwardation (stress incoming)
- Yield curve dynamics (steepening = growth, flattening = caution)
- Sector rotation patterns (defensive leadership = late cycle)

**Output → Actions:**
- EXPANSION: Mode 1 full exposure, Mode 2 aggressive (more positions, larger sizes)
- LATE CYCLE: Mode 1 full, Mode 2 defensive (fewer positions, smaller sizes, quality bias)
- CONTRACTION: Mode 1 filters should trigger automatically, Mode 2 goes to cash or short-bias
- CRISIS: Both modes defensive, preserve capital

### Signal Source 3: Event-Driven (Selective, 2-5 trades per quarter)

High-conviction special situations:
- **Spin-offs:** Parent companies forced-selling child companies. Historically +15-20% year 1.
- **Insider buying clusters:** 3+ insiders buying in same month. Strong 6-month predictive power.
- **Index rebalance:** Stocks added to S&P 500 get a predictable demand boost.
- **Activist situations:** 13D filings where the activist has a strong track record.

These are SELECTIVE — maybe 10-15 trades per year. But each one is high-conviction with an identifiable catalyst and timeline.

---

## The Weekly Cycle

```
EVERY WEEKEND (George + Claude):

1. DATA GATHERING (30 min, scriptable):
   - This week's earnings (calendar API)
   - Transcripts for companies that reported (SEC EDGAR or API)
   - Macro data releases (FRED)
   - Portfolio current state (Alpaca API)

2. CLAUDE ANALYSIS (the core work):
   For each earnings report:
   → Score: surprise quality (1-5), guidance direction, management tone
   → Flag: PEAD candidates with thesis, direction, conviction, hold period
   
   Macro update:
   → Regime assessment with supporting data
   → Any regime CHANGE since last week?
   → Implications for Mode 1 factor weights and Mode 2 position sizing
   
   Portfolio review:
   → Which existing positions should be closed? (time limit, thesis invalidated)
   → Which are working and should be held?
   → Overall exposure check

3. STRUCTURED OUTPUT:
   → Weekly Research Report (readable, stored, trackable)
   → Specific recommendations: {ticker, direction, entry zone, stop, target,
     conviction 1-5, thesis, hold period, position size}
   → Updated macro regime + confidence level

4. GEORGE REVIEWS & EXECUTES:
   → Read the report
   → Challenge assumptions, ask follow-up questions
   → Approve/reject/modify each recommendation
   → Execute via dashboard or broker
```

**Time commitment:** ~2-3 hours per weekend. The analysis is the valuable part — the execution is trivial once the thesis is clear.

---

## Risk Framework for $50K

### Hard Rules (Non-Negotiable)

| Rule | Rationale |
|------|-----------|
| Max 5% per position ($2.5K) | No single idea can hurt |
| Hard stop at -5% per position | Cut losers fast, let winners run |
| Max 60% deployed at any time | Always 40% cash reserve |
| No leverage, no options, no shorting | Complexity kills in small accounts |
| No trading during first month | Paper-test Mode 2 recommendations first |

### Phased Deployment

**Month 1 (May 2026): Paper only.** Run the weekly cycle, generate recommendations, track outcomes on paper. Build confidence (or learn that it doesn't work).

**Months 2-3 (Jun-Jul 2026): Small live.** If paper results show >50% hit rate on PEAD trades, deploy $10K real money. Max 3 positions at a time. The planned property sale hasn't happened yet — preserve capital.

**Months 4-6 (Aug-Oct 2026): Scale if working.** a planned property sale closes. If Mode 2 is generating alpha, scale to $25-30K deployed. If not, stay at $10K or pause.

**Months 7+ (Nov 2026+): Full deployment.** Cash cushion is built. Mode 2 can operate at full $50K allocation. Mode 1 can go live too if paper trading results justify it.

### Capital Allocation (Target State)

| Mode | Capital | Role |
|------|---------|------|
| Mode 1 (Structural) | $30K | Steady compounding, automated, lower touch |
| Mode 2 (Informational) | $20K | Active alpha, weekly analysis, higher touch |
| Cash reserve | varies | Dry powder for event-driven, never below 40% of Mode 2 |

---

## What We Need to Build

### Phase A: Research Infrastructure (build first, before any real money)

1. **Earnings calendar + transcript pipeline** ✅ BUILT 2026-04-15
   - Source: Finnhub API (free, EPS surprise + news) + Insider Monkey (free, transcript scraping)
   - NOT FMP or SEC EDGAR — tested 9 sources, these two are best free combo. See `References/mode2-data-sources-research.md`.
   - Finnhub: EPS actual vs estimate, surprise %, company news. Free tier: 60 calls/min.
   - Insider Monkey: Full verbatim transcripts (prepared remarks + Q&A with speaker IDs). Scraped via curl, `<article>` tag parsing, no JS needed.
   - Alpha Vantage transcript endpoint returns empty arrays on free tier — dead end.
   - Code: `mode2/earnings.py` — `get_earnings_surprise()`, `scrape_transcript()`, `get_company_news()`
   - Storage: JSON files in `data/mode2/transcripts/{SYMBOL}_Q{N}_{YEAR}.json`
   - Transcript URL discovery: web search for Insider Monkey URL, add to `TRANSCRIPT_URLS` dict in `run_analysis.py`
   - CLI: `uv run python3 -m mode2.run_analysis fetch --symbols JPM,GS,C --quarter 1 --year 2026`

2. **Claude analysis prompts** ✅ BUILT 2026-04-15
   - PEAD scoring prompt: structured, produces JSON with surprise quality (1-5), guidance direction, management tone, revenue quality, sector context, full trade recommendation. Code: `mode2/pead.py`
   - Quick analysis prompt: shorter version for in-conversation use
   - Macro regime prompt: NOT YET BUILT (Research Thread 4)
   - Portfolio review prompt: NOT YET BUILT (needs open positions first)

3. **Recommendation tracker** ✅ BUILT 2026-04-15
   - JSONL log: `data/mode2/recommendations.jsonl`
   - Every recommendation: timestamp, ticker, direction, conviction, entry, stop, target, thesis, key risks
   - Outcome tracking: actual entry/exit, P&L, hold days, exit reason, thesis validation
   - Summary stats: hit rate, avg winner/loser, P&L by conviction level
   - Code: `mode2/tracker.py` — `log_recommendation()`, `close_recommendation()`, `summary_stats()`
   - CLI: `uv run python3 -m mode2.run_analysis status`

4. **Weekly report generator** — NOT YET BUILT
   - Produces a readable research report from Claude's analysis
   - Stored as markdown, versioned, searchable
   - Tracks conviction accuracy over time (hit rate by conviction level)

### Phase B: Integration

5. **Mode 2 dashboard tab or page**
   - Current recommendations and their status (open/closed/expired)
   - Macro regime indicator
   - Recommendation history with P&L tracking
   - Hit rate and conviction calibration charts

6. **Alpaca integration for Mode 2**
   - Separate account or sub-portfolio tracking
   - Mode 2 positions tagged separately from Mode 1
   - Risk monitoring (exposure, max loss, position count)

### Phase C: Refinement (after 3+ months of data)

7. **Conviction calibration** — Are 5/5 conviction trades actually better than 3/5? Tune position sizing based on calibration data.
8. **Sector analysis prompts** — Deeper sector-specific analysis templates for industries George knows well.
9. **Autoresearch for Mode 2** — Can we automate parts of the weekly analysis? Test whether running Claude on ALL earnings (not just manual picks) finds opportunities humans miss.

---

## The Crypto Angle (Account 4) — OPTIMIZED 2026-04-15

Account 4 is sitting in cash because BTC is below its 150d SMA. But historically:
- BTC crossed ABOVE 150d SMA in Jan 2023 at ~$16K → rose to $73K by Mar 2024 (356%)
- The strategy sat out ALL of 2022 (100% cash while BTC fell from $47K to $16K)
- When the filter flips back on, the strategy captures the bulk of the bull run

**Research Thread 5 completed:** Comprehensive parameter sweep across 22 filter configurations + 6 strategy dimensions. Results:

| Parameter | Old | New | Impact |
|---|---|---|---|
| BTC trend filter | 200d SMA | **150d SMA** | +0.20 Sharpe (crypto cycles faster than equities) |
| Top N coins | 3 | **2** | +0.25 Sharpe (more concentrated momentum) |
| Lookback | 21d | 21d | Already optimal |
| Rebalance | Daily | Daily | Already optimal (3d marginal improvement not worth complexity) |
| Vol target | 15% | 15% | Best risk-adjusted (no vol-scaling has higher Sharpe but -51% MaxDD) |

**Combined result: Sharpe 1.56 → 2.01, CAGR 34.5% → 45.6%, MaxDD -23.5% → -14.1%, Calmar 1.47 → 3.24**

Strategy updated in code and deployed. See `mode2/crypto_filter_backtest.py` and `mode2/crypto_autoresearch.py` for full results.

---

## What "Dig Dig Dig" Looks Like

This is the research agenda. Each of these needs to be PROVEN before real money:

### Research Thread 1: PEAD Baseline ✅ COMPLETED 2026-04-15
- Backtested 14,366 earnings events across S&P 500, S&P 400 MidCap, S&P 600 SmallCap
- Code: `mode2/pead_backtest.py`, results in `data/mode2/pead_backtest_report.json`
- **Finding: Naive PEAD is too thin to be a standalone strategy.** Q5-Q1 spread exists (+1.73% at 60d market-adjusted for S&P 500) but absolute returns for top-quintile beats barely exceed SPY (+0.36%).
- Mid-cap and small-cap PEAD is WORSE, not better — structural underperformance vs SPY in 2024-2026 mega-cap regime dominates.
- "Confirmed quality" beats (big surprise + positive gap) in large-cap is the only viable segment (+1.60% excess).
- EPS surprise magnitude alone is NOT predictive — biggest surprises actually lose money. Quality scoring matters more than size of beat.
- **Implication for Mode 2:** PEAD should be a secondary filter, not the primary alpha source. Event-driven + macro regime should carry more weight. Claude's value is in quality discrimination, not systematic PEAD harvesting.

### Research Thread 2: Claude's Analytical Edge
- Take 20 earnings from last quarter
- Have Claude score them blind (no knowledge of subsequent price action)
- Compare Claude's conviction scores to actual 60-day returns
- Is there signal? If Claude's 5/5 convictions average +6% and 1/5 average +1%, we have something
- **Status:** Deprioritized — base PEAD signal too thin on S&P 500. More valuable to test on mid-caps or in combination with event-driven signals.

### Research Thread 3: Optimal Position Mechanics
- Entry timing: day-after vs wait-for-pullback vs immediate
- Stop placement: -3% vs -5% vs -8% (tighter = more stopped out, looser = bigger losers)
- Exit timing: 30 vs 45 vs 60 vs 90 days
- Backtest these on historical PEAD data
- **Status:** Deprioritized — depends on finding a viable PEAD universe first.

### Research Thread 4: Macro Regime Validation
- Can Claude's weekly macro assessment predict sector returns?
- Take last 12 months of macro data, have Claude assess each week
- Compare regime calls to actual market behavior
- Not expecting perfection — just better than random
- **Status:** Next priority for Mode 2 research. Independent of PEAD, informs both modes.

### Research Thread 5: Crypto Filter Optimization ✅ COMPLETED 2026-04-15
- Tested 22 filter configs (SMA/EMA periods, dual MA crossover, hysteresis bands) + full 6-dimension parameter sweep (lookback, top_n, rebalance freq, vol target, momentum type)
- Code: `mode2/crypto_filter_backtest.py`, `mode2/crypto_autoresearch.py`
- **Finding: 150d SMA + top 2 coins is optimal.** Sharpe 1.56 → 2.01, CAGR +11%, MaxDD improved by 9.4%.
- Crypto cycles are faster than equities — 200d (Faber standard) is too slow.
- Longer filters (250d, 300d) are worse than no filter at all.
- Strategy updated and deployed to Account 4.

### Research Thread 6: Leveraged ETF Momentum Rotation ✅ COMPLETED 2026-04-16 — NEGATIVE RESULT
- Swept 7 dimensions on 12 liquid 3x leveraged ETFs (TQQQ, UPRO, SOXL, TNA, TECL, FAS, ERX, etc.) with 15+ years of history (2010-2026)
- Code: `mode2/leveraged_etf_autoresearch.py`
- **Finding: Does NOT match crypto. Can't beat SPY buy-and-hold on risk-adjusted basis.**
  - Best config (no filter / 63d / top 3 / 10d rebal / 15% vol-target): **Sharpe 0.80, CAGR +11.9%, MaxDD -28.6%**
  - vs Crypto optimized: Sharpe 2.01, CAGR +45.6%, MaxDD -14.1%
  - vs SPY buy-and-hold: Sharpe 0.88, CAGR +14.5%, MaxDD -33.7%
- **Why it fails (unlike crypto):**
  1. **SPY filter hurts, not helps.** Unlike BTC filter (catches 100% of crypto bear markets), SPY filter kills cross-sector momentum — when SPY drops, ERX or FAS might be surging. No single "regime switch" signal works for the whole leveraged ETF universe.
  2. **Vol-scaling is mandatory but kills returns.** Without vol-scaling: CAGR +36.7% but MaxDD -75.1% (untradeable). With 15% vol-target: CAGR drops to +11.9% — worse than unlevered SPY.
  3. **It's leveraged beta, not alpha.** The Sharpe (0.80) is below SPY (0.88). Leverage amplifies returns AND volatility proportionally — no free lunch.
- **Key insight:** The crypto strategy works because BTC is a uniquely clean regime indicator. When BTC trends down, ALL crypto trends down. There's no equivalent single signal for leveraged equity ETFs — they're diversified across uncorrelated sectors.
- **Decision: Not worth pursuing. Moving on to Thread 7 (concentrated sector momentum).**

### Research Thread 7: Sector Momentum with Regime-Adaptive Concentration
- Current cross-sectional momentum (top 6 of 17 ETFs, Sharpe 0.85) is too diversified. Crypto proves concentration (top 2 of 9) dramatically improves Sharpe.
- Apply concentration + binary filter logic to 11 SPDR sector ETFs (XLK, XLF, XLE, XLV, XLI, XLP, XLU, XLY, XLRE, XLC, XLB)
- **Dimensions to sweep:** top N (1-4, hypothesis: top 2 wins like crypto), lookback (21-189d), filter (SPY 200d MA binary), vol-scaling, rebalance (weekly/biweekly/monthly)
- **Key difference from current strategy:** concentration + binary filter — the two changes that took crypto from Sharpe 1.56 to 2.01
- **Status:** Queued — next after Thread 6

### Research Thread 8: Commodity Momentum Rotation
- Commodities have the strongest momentum effect of any asset class (Asness, Moskowitz, Pedersen 2013 — "Value and Momentum Everywhere")
- Universe: 8-12 commodity ETFs — GLD, SLV, USO (oil), UNG (nat gas), DBA (agriculture), CPER (copper), WEAT (wheat), CORN, SOYB, URA (uranium)
- Low correlation to equities (0.05-0.20) — adds genuine diversification
- Binary filter: DBC (broad commodity index) above 200d MA, or individual commodity MA
- **Risk:** Futures-based ETFs have contango drag (roll cost). Need to test only spot-like ETFs or account for roll cost.
- **Status:** Queued

### Research Thread 9: International/Country Momentum Rotation
- Country equity indices have persistent momentum (documented since the 1990s). Less crowded than US sector momentum.
- Universe: 15-20 iShares country ETFs (EWJ, EWZ, EWY, EWT, EWA, EWC, EWG, EWU, EWH, EWS, EPI, INDA, THD, etc.)
- Country-level returns driven by macro cycles, FX, and policy — all slow-moving, momentum-friendly
- Binary filter: VT (total world) or ACWI above 200d MA
- **Status:** Queued

### Research Thread 10: Multi-Asset "All-Weather Momentum"
- Instead of momentum within a single asset class, run it across ALL asset classes simultaneously — equities, bonds, commodities, currencies, crypto
- At any given time something is trending. 2022: commodities. 2023-24: crypto + tech. 2025: gold.
- Universe: ~20 ETFs spanning equities (SPY, QQQ, EFA, EEM), bonds (TLT, IEF, HYG), commodities (GLD, SLV, USO, DBA), currencies (UUP, FXE)
- Multi-timeframe signal: blend of 21d, 63d, 126d, 252d momentum
- Cross-asset momentum has the highest Sharpe of any momentum variant (Moskowitz et al. 2012)
- **Status:** Queued

### Research Thread 11: VIX Term Structure Trading
- VIX futures term structure (contango vs backwardation) is one of the strongest and most persistent signals in finance
- Contango ~80% of the time → short-vol strategies earn structural premium. Backwardation signals crisis within days.
- Products: SVXY (short vol in contango), UVXY (long vol in backwardation), or cash
- Signal: VIX/VIX3M ratio (>1.0 = backwardation = danger)
- **Risk:** Vol strategies can blow up spectacularly (Volmageddon Feb 2018). Binary filter MUST work. Test against 2018, 2020, 2022.
- **Data:** yfinance has ^VIX and ^VIX3M. SVXY/UVXY have limited history (SVXY post-2018 rebalance).
- **Status:** Queued — needs new signal type (term structure), higher build cost than others

---

## Success Criteria

**Paper trading (Month 1):**
- Generate 15+ PEAD recommendations
- Track all outcomes
- Hit rate > 50% (better than coin flip)
- Average winner > average loser (positive expectancy)

**Small live (Months 2-3):**
- Real execution matches paper expectations (slippage check)
- No position loses more than 5%
- Portfolio positive after 8 weeks

**Full deployment (Months 4+):**
- Annualized return > 12% (beating SPY is the minimum bar)
- Max drawdown < -15% (hard ceiling)
- Sharpe > 1.0 on Mode 2 positions
- Weekly time commitment sustainable (~2-3 hours)

---

## First Concrete Step

**This week:** Claude analyzes 5-10 earnings from companies that reported this week. Full PEAD analysis — transcript reading, quality scoring, thesis, entry/stop/target. George reviews. We track outcomes for 60 days. No money at risk. Just proving the concept works or learning that it doesn't.

---

## Progress Log

### 2026-04-15: Week 1 — Pipeline built, first analysis complete

**Infrastructure:**
- Built entire Mode 2 data pipeline in one session: `mode2/earnings.py`, `mode2/pead.py`, `mode2/tracker.py`, `mode2/run_analysis.py`
- Evaluated 9 data sources (Finnhub, Alpha Vantage, FMP, SEC EDGAR, Insider Monkey, Motley Fool, EarningsCall.biz, API Ninjas, Quartr). Settled on Finnhub + Insider Monkey — $0/month.
- Full research documented in `References/mode2-data-sources-research.md`

**First PEAD Analysis — Q1 2026 Banks (6 companies):**

| Symbol | Surprise | Direction | Conv | Rationale |
|---|---|---|---|---|
| **C** | **+13.3%** | **Long** | **4/5** | Revenue-driven beat across all 5 businesses, sandbagged guidance (13.1% ROTCE vs 10-11% target), Investor Day May catalyst |
| JPM | +8.0% | Skip | — | G-SIB capital headwind is JPM-specific (+$20B by 2028), negative operating leverage, no guidance raise |
| BLK | +7.5% | Skip | — | Beat partly acquisition-inflated (HPS/Preqin), mega-cap priced efficiently |
| GS | +3.3% | Skip | — | Below PEAD threshold, trading-driven seasonality |
| WFC | +0.1% | Skip | — | In-line, no surprise |
| JNJ | +0.3% | Skip | — | In-line, no surprise |

**C recommendation:** Entry $131.69, stop $125, target $138 (adjusted from $142 — large-cap drift is 1-3%, not 5-8%). Hold 40 days. Paper only.

**Key learning:** Large-cap PEAD drift is much smaller than the academic literature implies (which skews small-cap). The real hunting ground for PEAD is mid-cap companies with less analyst coverage reporting in weeks 2-4 of earnings season. Mega-cap bank results are a good pipeline test but not the best alpha source.

**Pending:** BAC (+8.6%), MS (+10.9%), PNC (+5.5%) reported same day — transcripts not yet on Insider Monkey. PNC is the most interesting (smallest market cap = less efficient pricing).

### 2026-04-15: Research Threads 1 & 5 — PEAD is thin, Crypto is gold

**Research Thread 1 — PEAD Baseline (completed):**
- Backtested 14,366 earnings events across S&P 500 / 400 MidCap / 600 SmallCap
- Naive PEAD is not a viable standalone strategy on any universe in 2024-2026
- Only "confirmed quality beats" in large-cap shows modest alpha (+1.60% over 60d)
- Mid/small-cap PEAD is WORSE — mega-cap regime bias means everything outside S&P 500 underperforms
- Key insight: EPS surprise magnitude alone doesn't predict drift. The biggest surprises lose money. Quality scoring (what Claude would do) matters, but the base signal is too thin to build a strategy on.
- **Decision: Shift Mode 2 focus toward event-driven + macro regime, keep PEAD as a secondary filter only**

**Research Thread 5 — Crypto Filter Optimization (completed):**
- Comprehensive sweep: 22 filter configs + 6-dimension autoresearch (lookback, top_n, rebalance, vol-target, momentum type)
- Winner: SMA-150 + top 2 coins. Sharpe 1.56 → 2.01, CAGR 34.5% → 45.6%, MaxDD -23.5% → -14.1%
- 150d SMA gets into bull markets earlier. Top 2 concentrates on strongest momentum.
- Strategy updated and deployed to Account 4 (still in cash — BTC below 150d SMA)

**Dashboard fixes:** Backtest chart fitContent fixed (minBarSpacing for crypto's 7-day/week data), horizontal scroll enabled, warmup trimming applied to all strategies, both equity lines start at $10k.
