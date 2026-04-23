# Book Shape — What We Need to Find

**Created:** 2026-04-23, after a long session that exhausted the "find another uncorrelated A5" search space.
**Context:** See `HUNT_APR2026.md` for the full hunt narrative — 12 vectors tested across two reframing rounds, 1 clean GO (mid-cap buyback drift) shelved for scope, three real opportunities flagged but none genuinely transformative of the book's risk/return profile.

This doc is the **pivot from "hunt for A5" to "complete the book's architecture."** It names what the book currently IS, what it IS NOT, and what we actually need to find next.

---

## The reframing

The A5 hunt asked: *"Find another uncorrelated equity-spot-long-only strategy that clears the validation gates."* After 12 attempts, the honest meta-finding is that **this search space is picked over at our scale**. The incremental A5 hunt is in diminishing returns.

The better question: **what functional shape should the book have?** Legendary systematic books (Bridgewater All-Weather, Medallion, Thorp's Princeton Newport) weren't built by finding "A5 through A12." They were built by identifying **functional components** — growth, defense, crisis alpha, informational edge, regime adaptivity, liquidity buffer — and engineering each.

Applied to FIRE, this reframes the hunt from "more of what we have" to "what's missing."

---

## Map of the current book

| Functional component | Covered by | Quality |
|---|---|---|
| Equity growth engine (trend/momentum) | A1 | Strong — 27% OOS CAGR, Calmar 2.76 |
| Defensive equity leg | A2 | Modest — 11% OOS CAGR, Calmar 1.51 (valid by design, not underperforming) |
| Asymmetric growth engine | A4 (crypto momentum) | Strong — 40% OOS CAGR, Calmar 3.18 |
| **Crisis alpha** | **— nothing** | **MISSING** |
| **Informational / non-price edge** | **— nothing** | **MISSING** |
| **Book-level regime adaptivity** | **— per-account filters only** | **WEAK** |
| Capacity buffer | all three scale | Have headroom ($50K → $500K+) |

The three rows in bold are the real gaps.

---

## The three functional gaps

### Gap 1: Crisis alpha (the biggest)

**What it is:** something that goes UP when the book goes DOWN hard. Genuinely anti-correlated during equity-bond coordinated crashes.

**Why we don't have it:** Every strategy in our book is directional long on equity or crypto. A2's TLT/GLD leg is MODESTLY defensive, but TLT was -29% in 2022 — the "defensive" leg of a coordinated crash is still down. In a 2022-style event, SPY, bonds, BTC all dropped together; all three of our accounts would have lost simultaneously.

**Why it matters:** the backtest Calmar 4.28 assumes A1↔A2↔A4 correlations stay at 0.05-0.38 in stress. They won't — the C3 retirement (A1↔A3 live correlation 0.84 vs backtest 0.38) is the cautionary example. Realistic live Calmar under a coordinated crash compresses toward 1.5-2.5, and the first 20-30% drawdown happens before any individual account's trend filter triggers.

**What fills it:** managed futures on actual futures (CTA trend-following), long-vol overlays, systematic tail-hedging. None accessible on Alpaca spot.
- **DBMF (ETF proxy)**: scouted 2026-04-23. EV-negative at bridge horizon as unconditional sleeve, but viable as CRISIS-CONDITIONAL TRIGGER (swap A2 → DBMF if A2 live Calmar < 1.0 or a 2022-class event fires). Already logged in HUNT_APR2026.
- **IBKR + futures**: real solution, real infrastructure work. Months, not days. Unlocks 50+ years of documented CTA premium literature.

### Gap 2: Informational / non-price edge

**What it is:** any signal that doesn't derive from price series. Fundamentals, events, sentiment, filings, language, positioning.

**Why we don't have it:** every signal in A1/A2/A4 is price-derived (momentum, mean-reversion, realized vol, 52-week high proximity, trend quality, etc.). Mode 2 PEAD was the attempt to add a fundamental/transcript-text edge; it produced 1 C recommendation and stalled out at mega-cap banks.

**Why it matters:** price-signal strategies have a documented factor-decay problem (McLean-Pontiff 58% post-publication decay average). Non-price signals — especially event-driven with real economic mechanism — tend to decay more slowly and are genuinely orthogonal to momentum.

**What fills it:**
- **Mid-cap buyback drift** — GO verdict from 2026-04-23 scout, shelved on scope. Asymmetric-decay insight: mega-cap arbed out, mid-cap retains because big shops don't fish in $2-20B market caps. Our size is an advantage here. Clearest path available. 1.5-2 days for POC (EDGAR scraper is the new cost).
- **13D activist filings** — Brav-Jiang-Partnoy-Thomas (2008) documented 5-7% yr excess. Secondary candidate.
- **Spinoff drift** — Greenblatt thesis, ~20-30 US spinoffs/year too thin for standalone but could layer with buybacks.
- **Mode 2 PEAD on mid-caps** — the original PEAD attempt failed on mega-cap banks. Mid-cap PEAD has more drift per literature, never tested in-house.

### Gap 3: Book-level regime adaptivity

**What it is:** a mechanism that COORDINATES de-risking across accounts when macro conditions shift, BEFORE individual trend filters trigger.

**Why we don't have it:** each account has its own static filter (SPY 200d for A1/A2, BTC 125d for A4). In 2022, SPY's 200d filter triggered months after the top; A1/A2 were already deep into drawdowns. No inter-account coordination, no anticipation, no front-running of regime change.

**Why it matters:** this is the difference between "defensive strategies that lose less" and "actively de-risked book." Even 2-3 weeks of anticipation (triggered by rate-vol / credit-spread / yield-curve / VIX-term-structure / central-bank-text composite) could meaningfully reduce drawdowns across all accounts simultaneously.

**What fills it:**
- **Macro regime detector from PRICE signals** (preferred) — WALCL + DXY + M2 + credit spreads + VIX term structure composite. HUNT_APR2026 Breakthrough #2 Candidate C shape; never prosecuted. Zero broker change, zero AI involvement. ~1 week of work. This is the lowest-risk option — all inputs are deterministic, well-behaved data series.
- **AI FOMC overlay with Day-3 look-ahead gate** (HIGH SKEPTICISM) — 2026-04-23 scout's recommended vector. Uses LLM multi-document synthesis on FOMC statements + minutes + press conferences for hawkish/dovish regime score. The priors on this working in OUR system are LOW — we have two failed AI-alpha attempts already (HUNT_APR2026 Breakthrough #1: Claude-as-stock-filter, -1.68%/month; and Mode 2 PEAD on mega-cap banks, produced 1 trade out of 6 and stalled). Academic literature (BIS 2024, IMF 2025) distinguishes single-name LLM filtering — which reproducibly fails — from macro regime classification — which reproducibly works. *Extrapolating from academic reproduction to live edge is exactly the optimism bias we've been burned by.* If this gets prosecuted, the Day-3 look-ahead gate is not just a nice-to-have; it's the only honest way to kill it cheap before it becomes the third AI-alpha casualty.

---

## Ranked paths forward

**Tier 1 — no broker change, prosecutable now:**

| Work | Effort | Gap filled | Expected lift | Priors |
|---|---|---|---|---|
| cap=1.5 engineering sprint | 3-5 days | (existing account lift, not a gap) | ~2pp book CAGR | Deterministic — high confidence |
| Mid-cap buyback drift POC | 1.5-2 days | Gap 2 | ~2-3pp book CAGR at 20% sleeve | Documented literature, minimum-test kill-switch — moderate confidence |
| Macro regime composite (WALCL/DXY/M2/curve) | ~1 week | Gap 3 | Drawdown reduction, not CAGR lift | All price/macro data deterministic — moderate confidence |
| AI FOMC overlay with Day-3 gate | ~1 week | Gap 3 | Drawdown reduction + methodology foundation | **LOW — two prior AI-alpha kills in this system; skip unless Gap 3 remains unsolved after price-based composite** |

**Tier 2 — broker change required:**

| Work | Effort | Gap filled | Expected lift |
|---|---|---|---|
| IBKR migration + futures CTA sleeve | Months | Gap 1 (the big one) | Transformative — true crisis alpha unlock |
| Margin equity for cap >1.5 / vol-selling / pairs | Weeks | (amplification, not a new gap) | ~1-2pp book CAGR |

**Tier 3 — zero work, conditional:**

| Trigger | Action |
|---|---|
| A2 live Calmar < 1.0 by 2026-Q4 OR 2022-class crisis fires | Swap A2 → DBMF for crisis alpha |
| A4 signal-trading clock reaches 6 months (2026-10-22 earliest) with live Calmar ≥ 2.0 | A4 33% → 40% upgrade per pre-committed path |
| Rate-vol regime re-emerges (MOVE > 120 sustained) | Revisit MOVE×TLT reversal Candidate A with updated data |

---

## The success criteria for "book complete"

A complete book, by this framing, would have:
- Growth engines (A1 + A4): present ✓
- Defensive leg (A2): present ✓
- **Crisis alpha**: ≥5% CAGR with NEGATIVE correlation in equity-bond coordinated crashes
- **Non-price edge**: 5-8% CAGR, episodic, uncorrelated to price-signal factors
- **Regime overlay**: coordinated de-risking 2-3 weeks before individual filters trigger
- Combined book target: **22-28% live-realistic CAGR, Calmar 3.5-4.5 through one full crisis cycle**

Note the Calmar target is LOWER than the current backtest 4.28 — that's intentional realism (live correlations inflate under stress). The goal is a book that holds up *through* a crisis, not one that looks pretty in quiet years.

---

## Open questions / counter-arguments

**Is the reframe over-engineering?** Possibly. If the next 3.5 years stay mostly benign, the current book at ~26.5% live-realistic CAGR delivers the bridge-plan math. Crisis alpha is insurance with a cost, and insurance you don't use was wasted premium. The case for investing in it is probabilistic (we've gone ~15 years with two coordinated-crash episodes, another one likely within the bridge window).

**Is broker change too much work?** Depends on how much of the Tier-1 list pays off. If buyback drift + cap=1.5 + macro regime composite together lift book CAGR by 4-6pp at marginal engineering cost, the IBKR case weakens. If they underdeliver, the IBKR move becomes more compelling.

**Is AI FOMC overlay just another hype candidate?** Probably. We have two prior AI-alpha kills in this system (Breakthrough #1 and Mode 2 PEAD). A third attempt on thin priors is not obviously warranted. The Day-3 look-ahead gate is designed to kill fast if the attempt is made, and the methodology check itself is a durable contribution regardless — but the honest default is **skip** until/unless the price-based regime composite proves regime adaptivity is the actual binding constraint. Don't be the third AI-alpha casualty on hope.

**What if the honest answer is "do nothing new, let A1+A2+A4 run"?** That is a legitimate answer. The session's real finding is that the existing book is GOOD (efficient-frontier-ish under constraints), not broken. Patience + the pre-committed A4 upgrade path might be the highest-EV move for the next 6 months, regardless of what else gets built.

---

## How this relates to HUNT_APR2026.md

`HUNT_APR2026.md` documents the JOURNEY — 12 vectors tested, the kills, the false alarms, the user's reframe challenge, the final scoreboard. It's a time-capsule of the 2026-04-23 session.

`BOOK_SHAPE.md` is the DESTINATION ANALYSIS — what the session taught us about where the book actually stands and what we genuinely need next. Points forward, not backward.

A fresh session should read HUNT_APR2026 for context, then read BOOK_SHAPE for direction.

---

## Pointer updates needed (not yet done)

- Add to `CLAUDE.md` Key Documents list when this doc is accepted
- Link from `PLAN.md` next-steps section (current PLAN.md predates this reframe)
