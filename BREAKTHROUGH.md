# Breakthrough Hunt — April 2026

**Status:** Not committed. This is a working document — a handoff from a mobile/web session where the sandbox had no HTTP egress, so the tests couldn't run. Pick this up on the laptop where yfinance, FRED, Finnhub, and Insider Monkey actually work.

**Context for a fresh session:** Read `PLAN_MODE2.md` first for the strategic frame. Then `CLAUDE.md` for the current system state. Then this doc for where research goes next.

---

## The honest diagnosis

Mode 1 is mechanically excellent but alpha is thin (McLean & Pontiff 58% factor decay). Mode 2's PEAD baseline (Research Thread 1, 4,895 events across S&P 500) showed:
- Market-adjusted Q5-Q1 spread at 60d = +1.73%. Thin.
- Q5_best (avg +82% surprise) = +0.36% adjusted at 60d. The biggest surprises don't drift.
- Mid-cap and small-cap PEAD is **worse**, not better — structural mega-cap outperformance in 2024-26 dominates.
- "Confirmed quality" beats (Q4 surprise + positive gap) in large-cap = +1.60% excess. Real but small.

Week 1 analysis (6 mega-cap banks) produced 1 trade. That's not the universe — it's the TRUTH that mega-cap banks are picked over and the setup is wrong.

**The original Mode 2 thesis — "Claude does PEAD better by reading transcripts" — is disproven as a standalone strategy.** The alpha isn't there to harvest.

So: kill the old plan or reframe? Reframe.

---

## Breakthrough #1: Mode 2 as a Mode 1 filter, not a standalone strategy

**The reframe in one sentence:** Claude's value isn't finding new alpha — it's **concentrating existing Mode 1 alpha** by vetoing the momentum names where the qualitative read says the ride is over.

### Why this is the bet

- Every other Mode 2 idea requires proving alpha exists in a new place (PEAD, 13D, event-driven). This only requires proving alpha is **concentrable**.
- Mode 1 Account 1 already runs at Sharpe 1.38. We don't need new infrastructure, new broker, new universe, new paper-to-live transition.
- Claude's *actual* unique capability is qualitative reading at scale — no human is going to read 30 transcripts before every monthly rebalance. That's exactly what a filter layer needs.
- **Binary outcome in 2 days of work:** either the filter lifts Sharpe or it doesn't. Clean signal either way.
- If it works on Account 1, the same filter generalises to Accounts 2 and 3. Structural leverage.
- If it fails, we've proven Mode 2 as a concept doesn't pay off, and we redirect to Mode 1 infrastructure (walk-forward, regime overlay, live scaling). No 6 months lost chasing the wrong thesis.

### The specific test (2 days, laptop-only)

1. **Get 4 months of Account 1 candidate universes.** For each monthly rebalance date in 2026 Jan–Apr, pull the top-30 momentum-ranked S&P 500 stocks (not the 15 picked — the full ranked 30). `strategies/stock_momentum.py` has the ranking logic; you can replay historical signals.

2. **Pull the most recent pre-rebalance earnings transcript for each name.** Insider Monkey URLs via search. Expect ~80 unique symbols across 4 months (lots of overlap). Cache in `data/mode2/transcripts/`.

3. **Claude scores each 1-5 on forward conviction, blind to subsequent price action.** Score rubric is in `mode2/pead.py` (`PEAD_SCORING_PROMPT`). For THIS test, override the rubric: we're not scoring PEAD drift potential, we're scoring "will this name's momentum continue or reverse?" Fields: management tone, guidance credibility, revenue quality, competitive position, guidance-vs-analyst gap.

4. **Build two portfolios from the same universe of 30:**
   - **Portfolio M (momentum baseline):** top-15 by momentum rank (what Account 1 currently does).
   - **Portfolio C (Claude-filtered):** top-15 by Claude conviction score, ties broken by momentum rank.

5. **Measure realised 30-day returns for both portfolios, across the 4 months.** If Portfolio C beats Portfolio M by >1%/month average — the filter is real.

### Success criteria

- **Clear breakthrough:** Portfolio C averages ≥1.5% higher 30d return than Portfolio M, and hit rate on Claude's 5/5 conviction names >65%.
- **Marginal:** 0.5-1.5% excess. Worth a live paper trial for 3 months.
- **No:** <0.5% excess or negative. Mode 2 as concept is dead — reallocate to Mode 1.

### What to build if it works

- `mode2/filter_mode1.py` — runs monthly, reads Account 1 top-30 candidates, scores via Claude, returns top-15 for execution.
- Dashboard: "Mode 1 Filter" panel showing which names were kept / vetoed + Claude's rationale.
- Extend to Account 2 (34 stocks) and Account 3 (52 stocks). Each one gets a filter pass.

### Fallback moonshot (only if #1 works)

**Cross-transcript industry synthesis.** Read all 80 weekly earnings transcripts in a week. Not per-name scores — sector-level shifts. "Tech enterprise spend is weakening across 12 reports" → de-risk tech exposure. This is the one thing no human analyst and no existing quant can do. High ceiling, but only worth building after you've proven Claude adds value on single-name transcript reads.

---

## Breakthrough #2: Narrative-aware crypto

Account 4 is already the quiet star — **Sharpe 2.01, CAGR 45.6%, MaxDD -14.1%, Calmar 3.24, 0.18 SPY correlation** after the 150d/top-2 optimisation. The rebalance scheduler runs at 00:05 UTC daily. The filter monitor catches BTC cross-backs same-day. This is the cleanest strategy in the whole system.

But there's a ceiling coming: **the 9-coin universe is static, and crypto is the most narrative-driven asset class on Earth.** When the AI narrative hits, top coins rotate to NEAR / TAO / RNDR / FET. When memes hit, WIF / BONK / PEPE. L2 season, DePIN, RWAs, restaking — each lasts 2-6 weeks and doesn't touch the 9-coin majors. A fixed universe silently caps the strategy's Sharpe.

### The crypto breakthrough candidates

**Candidate A (easiest test, cleanest signal) — Noise filter on top-2 selection.**

Some days, top-1 momentum is a coin pumping on a single-event catalyst (exchange listing, whale move, false rumor, rug pull front-run). Claude reads the last 3 days of news / Twitter / on-chain activity for the selected coins and scores the momentum as *organic* or *suspect*. If top-1 is suspect, skip to top-2/top-3. The strategy's core math is untouched — we just filter false positives.

Testable: pull the last 2 years of daily rebals (~700 rebal events), identify the top-2 selections each day, have Claude score in 2026 blind. Measure Sharpe lift from dropping "suspect" selections.

**Candidate B (highest ceiling) — Dynamic universe by weekly narrative.**

Expand from 9 fixed coins to ~30 liquid coins. Each week, Claude identifies the 1-2 active narratives (AI, meme, L2, etc.) and the coins aligned with each. Momentum strategy runs on the dynamic "narrative-aligned" subset. You capture Solana summer, AI winter, meme season — regime shifts the fixed universe misses entirely.

Testable but harder: historical narrative reconstruction is messy. Start by manually tagging Q1 2023 through Q1 2026 by quarter (Claude can do this from crypto news archives), then run the momentum strategy on the per-quarter dynamic universe, compare to the fixed 9-coin baseline.

**Candidate C (high ceiling, hard) — Macro liquidity overlay.**

Global M2 + Fed balance sheet (WALCL) + DXY lead BTC by 2-3 months. The 150d SMA is reactive; a liquidity composite is *leading*. Use it to size up before BTC crosses the SMA, and size down when liquidity contracts before the SMA breaks. Extends the binary filter to a smooth gradient driven by a leading indicator.

Testable: pull WALCL, DXY, M2 via FRED from 2018. Compute liquidity score (90d slope + level). Composite filter = BTC 150d SMA AND liquidity score > 0. Compare Sharpe vs. current.

### Which one first

**A first.** Highest signal-to-noise in 2 days of work. Same logic as Breakthrough #1: Claude concentrates existing quant alpha by filtering false positives. Doesn't require universe expansion, doesn't require reconstructing history. If it lifts Sharpe from 2.01 to 2.3+, that's a measurable win and the narrative-universe work (B) becomes the natural follow-on.

### The bridge between both breakthroughs

If Claude's "narrative check" lifts crypto momentum, the same narrative-detection pipeline could drive **equity sector rotation signals** inside Mode 1. Example: "AI narrative is hot" → overweight AI-exposed equities in Account 1's selection. "Risk-off rotating to defensives" → bias Account 2 to low-vol. One narrative engine, feeding both modes. That's the architectural unlock — Mode 2 stops being a separate bucket and becomes the qualitative intelligence layer that sharpens Mode 1 equity + Mode 1 crypto simultaneously.

---

## What NOT to do (kill list)

These all looked attractive but don't clear the bar after the data review:

- **Mid/small-cap PEAD backtest rerun** — Research Thread 1 already showed it's worse, not better. In 2024-26 mega-cap regime, anything outside S&P 500 structurally underperforms. Chasing this is denial.
- **13D activist / insider cluster / spin-off pipeline** — academically real alpha (~5-7%/yr) but crowded and well-known. Not a breakthrough, just a sideline.
- **Macro regime module** — highest ceiling but untestable quickly. Needs multiple regime changes in data. Right for year 2, wrong for first bet.
- **Weekly report generator, auto-close feedback loop, transcript URL discovery, SI/insider overlays** — infrastructure chores. Build these only if Breakthrough #1 works and we go to real money.

---

## Concrete next steps for the laptop session

```bash
# Step 1 — Breakthrough #1 test (2 days)
# Build the test harness
touch mode2/mode1_filter_backtest.py

# Pull 4 months of Account 1 candidate universes
# Cache transcripts for ~80 unique symbols
# Run Claude blind scoring (API or in-conversation)
# Compute Portfolio M vs Portfolio C 30d returns
# Decision: go / no-go on Mode 2 as filter concept

# Step 2 — Breakthrough #2 test (2 days, only if #1 is go or marginal)
touch mode2/crypto_noise_filter_backtest.py

# Pull last 2 years of daily rebalance history
# Score top-2 selections for noise vs organic
# Measure Sharpe lift from dropping suspect selections
```

### Decision tree after test #1

```
Portfolio C - Portfolio M ≥ 1.5% / month  →  BUILD: filter layer for Accounts 1, 2, 3.
                                              Mode 2 pivots to filter service. Kill PEAD tracker.

Portfolio C - Portfolio M = 0.5-1.5%      →  LIVE PAPER: 3-month real-time trial on Account 1.
                                              Commit only if it holds up out-of-sample.

Portfolio C - Portfolio M < 0.5%          →  KILL Mode 2. Redirect to Mode 1 walk-forward,
                                              regime overlay, live scaling. Don't waste 6 more
                                              months chasing a disproven thesis.
```

---

## The meta-point

We spent 5 weeks proving Mode 2 as originally conceived (standalone PEAD trader) doesn't have enough signal to stand on its own. That's not a failure — that's what the evidence said. The question now is whether Claude's reading capability has **any** commercial application in this system.

The test above answers that in 2 days. If yes, the architecture of the system changes — Mode 2 becomes a filter layer, not a standalone account. If no, we know, and we stop burning time on it. Either way, we come out of this week with a real answer to the bet we placed when we wrote PLAN_MODE2.md.

That's the breakthrough. Not a new strategy — a clearer reading of where Claude actually adds value in a trading system.
