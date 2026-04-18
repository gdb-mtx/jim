# Breakthrough Hunt — April 2026

**Status:** Updated 2026-04-18 with test results. Breakthrough #1 was tested and killed. Breakthrough #2 is paused pending validation of the underlying crypto Sharpe (which turned out to be in-sample optimized, not out-of-sample verified). The next concrete work is in `VALIDATION_PLAN.md`.

**Context for a fresh session:** Read `PLAN_MODE2.md` first for the strategic frame. Then `CLAUDE.md` for the current system state. Then this doc (especially the "Update — 2026-04-18" section below) for what we learned. Then `VALIDATION_PLAN.md` for what we do next.

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

## Update — 2026-04-18: What the tests actually said

We ran Breakthrough #1 on 2026-04-17. We then went to run Breakthrough #2 and discovered a bigger problem with the premise.

### Breakthrough #1 result: KILLED.

Test design followed the plan below to the letter. Dec 2025 / Jan / Feb / Mar 2026 monthly rebalances, top-30 S&P 500 momentum candidates per date, 54 unique symbols, 47 transcripts successfully scraped from Insider Monkey (7 missing — AMAT, GLW, LRCX, LVS, MRNA, APA, C — excluded from both portfolios for fairness). 10 parallel subagents scored each transcript 1-5 on forward conviction using the rubric in this doc, writing to `data/mode2/mode1_filter/scores/group{1..10}.json`.

**Headline result:** Portfolio M (top-15 by momentum) averaged **+1.40%/month**. Portfolio C (top-15 by Claude conviction score) averaged **-0.28%/month**. Excess: **-1.68%/month**. Claude didn't just fail to add alpha — it actively destroyed it.

**Score → 30d return relationship:** correlation **+0.07** (basically zero). 5/5 conviction names hit positive 40% of the time — below the 65% target and below pure momentum's hit rate.

**What Claude got wrong specifically:** every month, Claude swapped out the dirty-momentum names (ANET, HII, NEM, WBD, ALB) and swapped in consensus AI narratives (NVDA, GOOG, GOOGL, DELL, AVGO). Those swaps consistently hurt. Claude's "beat-and-raise + specific forward catalysts" heuristic overweighted names already priced to perfection.

**What this tells us:** pure momentum already encodes most of what transcript-reading would tell you. Claude's qualitative read didn't concentrate alpha — it added consensus bias. The "Claude concentrates existing alpha" thesis is disproven.

Per the decision tree in this doc: **<0.5% excess → kill Mode 2. Redirect to Mode 1 infrastructure.** We got -1.68%, not just below the kill line but deep into negative.

### Breakthrough #2 status: PAUSED (and the reason matters)

Breakthrough #2 was premised on one sentence: *"Account 4 is already the quiet star — Sharpe 2.01, CAGR 45.6%, MaxDD -14.1%."* When we went to test Candidate A (Claude noise filter on top-2 selections), we looked at where that 2.01 came from. It came from `mode2/crypto_autoresearch.py`, which sweeps ~40 parameter configurations (filter type × lookback × top-N × rebalance cadence × vol target × momentum type) on the **full 2018-2026 sample** and picks the winning Sharpe. No train/test split. No walk-forward. No out-of-sample period held back.

`git log -S "walk_forward_analysis"` and `git log -S "full_validation"` both return only the initial commit. `backtesting/validation.py` was built, documented, and never called on any strategy. PLAN.md line 197 explicitly says "No Live Money Without Statistical Validation" with a reject threshold at line 647 — the rule existed, the framework existed, the rule was not enforced.

**This means every Sharpe / CAGR / MaxDD currently in CLAUDE.md is in-sample tuned, not out-of-sample verified.** Running Breakthrough #2 would measure a Sharpe lift on top of a phantom number. Not useful.

### What's next

`VALIDATION_PLAN.md`. Walk-forward + Monte Carlo + parameter-stability tests on all 4 accounts, crypto first (most suspect, shortest history, most tuning). Accept whatever OOS numbers come out. Add an enforcement gate (`data/risk_state/validation_state.json` + `execute_rebalance` check) so this can't happen again. Pre-committed thresholds in the plan — no moving goalposts.

If the crypto Sharpe holds up OOS at >1.3, we have a real anchor and can re-entertain Candidate B (dynamic universe) and Candidate C (macro liquidity overlay) — *neither of which requires Claude*, both of which are standard quant work. Candidate A is dead by the same logic that killed Breakthrough #1: Claude as filter on quant alpha doesn't work.

If the crypto Sharpe collapses OOS, we have a priority-one problem (paper trading on phantom numbers, bridge-plan math based on inflated expected returns) and the whole agenda shifts.

The meta-lesson: we asked "can Claude add alpha on top of Mode 1?" before asking "is the Mode 1 alpha even real?" Both questions had to be answered, but in that order.

---

## Breakthrough #1: Mode 2 as a Mode 1 filter, not a standalone strategy

**Status: KILLED 2026-04-17.** See Update section above for results. Original reasoning preserved below.

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

**Status: PAUSED 2026-04-18.** Premised on the Account 4 Sharpe 2.01 being real. That number is in-sample optimized from a ~40-config parameter sweep with no OOS holdout, so the "ceiling" and "lift from 2.01 → 2.3+" framing below is not currently measurable. Foundation has to be validated (`VALIDATION_PLAN.md`) before any extension test is meaningful. Candidate A (Claude noise filter) is also dead-on-arrival by the same logic that killed Breakthrough #1 — don't build it. Candidates B (dynamic universe) and C (macro liquidity overlay) remain interesting and neither requires Claude, but they wait until the crypto base is OOS-verified.

Original reasoning preserved below.

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

## Concrete next steps (updated 2026-04-18)

Both original tests are now resolved or paused:

- ~~Step 1 — Breakthrough #1 test~~ **DONE 2026-04-17. Killed.** Artifacts in `data/mode2/mode1_filter/` and `mode2/mode1_filter_*.py`.
- ~~Step 2 — Breakthrough #2 test~~ **PAUSED.** Premise (crypto Sharpe 2.01) is in-sample tuned. Running this test without first validating the crypto base would measure lift on top of a phantom number.

**Actual next step:** `VALIDATION_PLAN.md`. Walk-forward + Monte Carlo + parameter-stability tests across all 4 accounts, crypto first. Pre-committed OOS Sharpe thresholds. Build the enforcement gate so `execute_rebalance` refuses to trade an unvalidated account.

After validation completes, come back here and decide which (if any) of the following is still worth building:
- **Candidate A** — dead (Claude-as-filter thesis is killed).
- **Candidate B** — dynamic universe. Requires Claude to tag narratives by quarter. Test only after crypto base is OOS-verified AND there's evidence fixed universe is the binding constraint.
- **Candidate C** — macro liquidity overlay (WALCL + DXY + M2 via FRED). Doesn't require Claude. Straight quant work. Lowest risk path to a Sharpe lift if the crypto base is real.

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

## The meta-point (revised 2026-04-18)

The original meta-point stands: we went into this week to get a real answer on whether Claude's reading capability has any commercial application in this system. We got one. It doesn't, at least not as a single-name filter on momentum candidates. That's a clean negative result in 2 hours of execution — exactly what the doc promised.

But the week's bigger finding was accidental. Pressure-testing Breakthrough #2 surfaced that the entire Mode 1 validation layer was built and never run. The numbers we'd been treating as ground truth (Sharpe 1.38 on Account 1, Sharpe 2.01 on Account 4, Sharpe 1.59 on the combined portfolio) are in-sample tuned and have no out-of-sample verification. That's the real load-bearing problem, and finding it was more valuable than any extension we might have built on top.

Revised framing: **Claude's commercial application in this system is not as an alpha source — it's as a discipline layer.** The value in today's work wasn't the filter test itself; it was running the test honestly, pre-committing to thresholds, and accepting a negative result without moving goalposts. That same discipline now has to be applied to the strategies we're already running with real exposure (paper, for now). That's what `VALIDATION_PLAN.md` is for.

Not a new strategy. A clearer reading of what actually matters.
