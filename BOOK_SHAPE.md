# Book Shape — What We Need to Find

> **Update 2026-05-26 — operator sentiment:** The gaps named in this doc (crisis alpha, non-price edge, regime adaptivity) have not been filled in the month since this was written. None of the Tier 1 strategy/research items have been prosecuted. Mechanics are solid, strategies are middle-of-the-road, the book runs but is not what we hoped for. **George wants a breakthrough, not coast** — these gaps remain real and worth pushing on. Treat the body of this doc as still-current strategic prioritization. Pitching candidate work against any of the named gaps is welcomed; evaluate against each gap's own success criteria, not reflexive CAGR/Calmar gates.

**Created:** 2026-04-23, after a long session that exhausted the "find another uncorrelated A5" search space.
**Context:** See `docs/archive/HUNT_APR2026.md` for the full hunt narrative — 12 vectors tested across two reframing rounds, 1 clean GO (mid-cap buyback drift) shelved for scope, three real opportunities flagged but none genuinely transformative of the book's risk/return profile.

This doc is the **pivot from "hunt for A5" to "complete the book's architecture."** It names what the book currently IS, what it IS NOT, and what we actually need to find next.

**Updated 2026-04-23 after outside-review round:** three parallel independent agents (auditor, prioritizer, creative scout) read all strategic docs and produced honest synthesis. Their main correction: this doc was silent on OPERATIONAL / INFRASTRUCTURE levers. Phase 1 cloud deployment and the C3 survivorship fix are higher-priority than anything in the original Tier 1 list because the real-money clock can't start without them. See *"Priority corrections from outside review"* section below.

---

## Priority corrections from outside review (2026-04-23)

All three outside agents independently flagged the same pattern: **infrastructure maturity is outpacing alpha evidence**, and the highest-EV moves in the next 30-90 days are OPERATIONAL, not research. Concrete corrections:

1. **Phase 1 Fly.io deployment is the #1 lever, and this doc didn't name it.** Per `DEPLOYMENT_PLAN.md`, earliest real-money date is 2026-07-20, gated on ≥8 weeks of deployed-paper. Phase 1 target is ~2026-05-04. Every week Phase 1 slips, real money slips. Unlike all other levers which add CAGR *after* real money, Phase 1 is the gate *to* real money. Boring but existential.

2. **C3 survivorship fix is a real-money prerequisite, and this doc treated it as "hygiene."** Actually subtractive to A1 CAGR (27.2% → ~25-26%) but required per CAPABILITIES.md before real capital. ~1 week of work using CRSP or Kenneth French point-in-time constituents.

3. **AI FOMC overlay should be "skip, period" — not "skip unless."** Two prior AI-alpha kills in this system (Breakthrough #1, Mode 2 PEAD). The academic reproduction of macro regime classification is not evidence that IT works for US. Extrapolating is the exact optimism bias the discipline layer is designed to resist. Revisit only if the price-based regime composite (VIX term-structure + credit + curve) has been built AND proven insufficient.

4. **"Do nothing new for 6 months" is a legitimate top-tier answer, not a counter-argument footnote.** All three agents landed on this. Let A1+A2+A4 run, ship to Fly, close C3, wait for live evidence. The bias-toward-action during the A5 hunt was itself a signal that operator fatigue is creating bored-operator risk.

5. **The headline "26.5% CAGR / Calmar 4.28" leans heavily on A4, which has ~1 day of actual live signal exposure.** Drop A4 and the equity core is 19% / 3.13. Until A4 accumulates 6+ months of signal-trading days, the combined number is mostly backtest, not live evidence.

6. **Consider a documentation freeze until real money.** 14+ markdown files. Docs are starting to lead reality (CAPABILITIES.md updated before capability is demonstrated live). The auditor's observation — "self-mythologizing risk" — is real and worth naming.

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

**Why everything above is factor/price-based:** The system was built around what we could validate rigorously — price-based signals with 16 years of backtest data, pre-committed thresholds, and walk-forward testing. Factor strategies (momentum, trend, mean-reversion, low-vol) have the deepest academic literature, the longest data, and the clearest mechanisms. Vol-scaling (Moreira & Muir 2017) replaced Kelly for sizing because our signals tell us *which* assets to hold, not *how much we expect to earn* — and vol-scaling is the reduced-form Kelly that sidesteps the hardest estimation problem (forward expected returns). This was the right foundation. But it also means every account shares the same vulnerability: they all need price to move in our favor to make money. A yield/carry strategy that generates distributions mechanically — or a non-price signal that fires on fundamentals — would be structurally different from everything in the map, which is itself a form of diversification the current book lacks. The A4 live performance gap (-7% live vs +5% signal in 3 weeks, as of 2026-05-13) is a reminder that backtest-validated factor strategies and real-world execution are different things.

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

**Tier 0 — OPERATIONAL, gates real-money graduation (must come first):**

| Work | Effort | Why | Priors |
|---|---|---|---|
| **Phase 1 Fly.io deployment** | ~1 week | Clock is burning. Earliest real-money 2026-07-20 needs 8wk deployed-paper. | Deterministic. Plan fully scoped. |
| **C3 survivorship fix** | ~1 week | A1's 27.2% is 1-2pp overstated. Hard prereq for real money per CAPABILITIES.md. | Mechanical. CRSP or Kenneth French data. |
| -10% alert smoke test | ~1 afternoon | Alert was shipped 2026-04-21, never fired live. Synthetic test before first real stress. | Trivial. |

**Tier 1 — strategy/research, prosecutable now:**

| Work | Effort | Gap filled | Expected lift | Priors |
|---|---|---|---|---|
| cap=1.5 engineering sprint (reframed as book-level vol controller) | 3-5 days | (existing-account lift, not a gap) | ~2pp book CAGR | Deterministic — high confidence |
| **VIX term-structure regime overlay** (NEW, from outside scout) | ~1 week | Gap 3 | Drawdown reduction (pre-triggers SPY 200d filter) | 20yr signal, pure FRED data, zero AI — MEDIUM-HIGH confidence |
| Mid-cap buyback drift POC (1-day minimal test first) | 1 day → 1.5-2d | Gap 2 | ~2-3pp book CAGR at 20% sleeve if it clears | Documented literature, kill-switch at 2% drift — moderate confidence |
| Price-based macro composite (WALCL/DXY/M2/curve) | ~1 week | Gap 3 | Drawdown reduction | Deterministic — moderate confidence |
| AI FOMC overlay | — | Gap 3 | — | **SKIP — two prior AI-alpha kills; revisit only if price-based composites prove insufficient** |

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

## Fresh creative ideas from outside scout (2026-04-23)

These are genuinely new directions an independent creative scout proposed after reading the full project history. None are proposed for immediate prosecution — they're the **research surface for later**, after Tier 0 + Tier 1 are cleared. Ranked by scout's honest viability estimate:

| Idea | Mechanism | Viability | Notes |
|---|---|---|---|
| **VIX term-structure regime overlay** | VIX9D/VIX3M ratio + backwardation sign → de-risk A1/A2 pre-trigger | HIGH | Already promoted to Tier 1 above. FRED data, zero AI, 20yr history. |
| **Book-level vol controller (evolved cap=1.5 sprint)** | Aggregate book vol targeting, not per-account | HIGH | Evolve the cap=1.5 sprint into this — same engineering, better result. |
| **Country momentum** (EWJ/EWZ/EWY/INDA/FXI/EWG/EWU/EZA) | Classic momentum across 8-12 country ETFs, top-3, monthly | MEDIUM | Hyper-US-coupled book; international momentum is genuinely different universe. 2 days to falsify. |
| **CEF discount-to-NAV mean reversion** | Buy closed-end funds at 1yr-extreme discount, revert to median | MEDIUM | Truly orthogonal mechanism (structural capital flight), non-price signal in Gap 2. Pontiff (1997). |
| **Commodity futures ETF momentum** (DBA/DBB/DBE/DBP/PDBC/USO/UNG/UUP) | Actual commodity factor, not producer-equity beta | MEDIUM | Different from the producer-XSM scouted; A2's MAT uses only DBC+GLD. |
| **Duration-carry via Treasury term structure** (SHY/IEI/IEF/TLT) | Hold long duration when curve steep, short when flat — NOT the rate-vol reversal | MEDIUM | Different mechanism from the rate-vol KILL. Curve-carry, not mean-reversion. |
| **Options on Alpaca** (cash-secured puts, defined-risk spreads) | VRP harvest, Level 1-3 available on Alpaca | MEDIUM | Self-imposed constraint; Alpaca now supports. Israelov-Nielsen caveat applies — mostly short-vol factor, not alpha. |
| **Business Development Companies with credit-spread filter** | Hold 5-BDC equal-weight when HYG-SPY momentum positive | LOW | Interesting yield angle but 40-60% BDC drawdowns in 2020/2022 Q4 are unforgiving. |
| **Merger-arb via MNA ETF** | Packaged merger-arb, 10-20% sleeve | LOW | Genuinely uncorrelated but deal volume has been weak post-2022; fees 0.77%. |

**Scout's dealer's-choice top picks:** VIX term-structure overlay (cleanest Gap 3 shot), book-vol controller merged with cap=1.5 (highest ROI/hour), and country momentum as a 2-day falsifiability test of the hyper-US-coupling concentration risk.

---

## Prediction markets bookmark (2027+ revisit)

**Kalshi (CFTC-regulated US)**: legitimate venue, API access, event contracts on macro (CPI, Fed, elections, weather). Two real alpha angles: (a) macro-data-release arb — CPI prints historically surprise Kalshi prices by measurable amounts (unsophisticated bettor base), (b) election market closing-price bias (favorite-longshot bias in Rothschild 2015, Forsythe et al. 1992). Contract sizes small; $50K book doesn't move markets.

**Why NOT 2026:** (a) Kalshi's product surface is still small — ~50 live markets at a time, weak strategy diversification; (b) genuine alpha requires the same macro-text / LLM pipeline that Mode 2 would need, so scope is "whole new research program" not "small bookmark test"; (c) CFTC regulatory posture on expanded event contracts is in flux. Revisit 2027 when Kalshi has 200+ markets, CME ticker event contracts have launched, and systematic backtest papers exist.

**Polymarket**: geo-blocked for US retail. VPN violates ToS + creates tax/withdrawal headaches. Skip.

---

## Non-instrument creative angles (reframes, not new strategies)

From the outside scout's reframing work:

1. **Bridge-capital as optionality acquisition, not return-chasing.** At $50K over 3.5 years, even perfect 40% CAGR → $192K, still short of existing NW anchor. The marginal CAGR point matters less than "what keeps me from liquidating in a crisis?" Crisis alpha allocation is buying optionality on NOT selling at the bottom — different objective function than Calmar-maximize.

2. **Factor-timing via regime states, not strategy-selection.** A1/A2/A4 already span the return surface. A regime-conditional weight vector (risk-on / risk-off / crypto-bull) could extract 2-4pp book CAGR with zero new strategies. Same infrastructure; different allocator. This ties into Gap 3 (regime adaptivity) as a framework, not a new account.

3. **The "reframe moment" from mid-session was the highest-value insight of the entire day.** When the user asked "am I defending the book vs. trying to expand it?" — that question flipped the low_ivol-as-A2-replacement test from assumed-good to actually-measured, and the book-level Calmar 3.13→2.09 degradation was the real finding. Generalize this: before prosecuting any future hunt, ask explicitly "am I testing this fairly or defending my priors?"

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

**What if the honest answer is "do nothing new, let A1+A2+A4 run"?** That is a legitimate answer — **and all three outside-review agents independently arrived at some version of it.** The session's real finding is that the existing book is GOOD (efficient-frontier-ish under constraints), not broken. Patience + Phase 1 deployment + C3 fix + the pre-committed A4 upgrade path is plausibly the highest-EV move for the next 6 months, regardless of what else gets built.

**Operator-fatigue signal:** The fact that the A5 hunt stretched to 12 vectors in a single session, and that each successive candidate was more exotic than the last, is itself evidence that the productive research space is getting thinner. The auditor's observation — "the operator is exhausted and knows it" — should be taken as the strongest argument for a 60-day hunting pause.

**The documentation growing faster than capability.** 14+ strategic markdown files as of 2026-04-23. Consider a doc freeze until real money is on. Update CLAUDE.md and operational files as facts change; resist the urge to write new strategy docs until a strategy has generated a real-money trade.

---

## How this relates to HUNT_APR2026.md

`docs/archive/HUNT_APR2026.md` documents the JOURNEY — 12 vectors tested, the kills, the false alarms, the user's reframe challenge, the final scoreboard. It's a time-capsule of the 2026-04-23 session.

`BOOK_SHAPE.md` is the DESTINATION ANALYSIS — what the session taught us about where the book actually stands and what we genuinely need next. Points forward, not backward.

A fresh session should read HUNT_APR2026 for context, then read BOOK_SHAPE for direction.

---

## Pointer updates needed (not yet done)

- Add to `CLAUDE.md` Key Documents list when this doc is accepted
- ~~Link from `PLAN.md` next-steps section~~ — moot; PLAN.md archived 2026-05-07 (predated this reframe).
