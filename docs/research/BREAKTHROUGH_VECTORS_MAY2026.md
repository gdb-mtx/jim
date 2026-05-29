# Breakthrough Vectors — Why We're Underperforming SPY, and Where to Look (2026-05-26)

**Origin:** Session 2026-05-26 between George and Claude (Opus 4.7). Sparked by George's read that strategies are middle-of-the-road, the book is underperforming SPY dramatically, and the academic factor space feels exhausted. This doc captures concrete avenues to push on — non-academic, structurally different from existing A1/A2/A4.

**Posture:** Active breakthrough hunt. Not maintenance. See README + CLAUDE.md operator-sentiment headers (2026-05-26 updates).

**Constraint:** Let A1/A2/A4 run to their 3-6 month proof points. Don't touch existing accounts. New work is **additive**, not replacement.

---

## ⚠ UPDATE 2026-05-29 — cap-weight test run; core premise partly overturned

The #1 "quick info-rich test" below (cap-weight rebuild of A1) was built and run
(`scripts/capweight_diagnostic.py`; results in `capweight_diagnostic_results.md`).
**The result contradicts this doc's title premise for A1.**

- **A1 is NOT underperforming SPY in backtest.** OOS (2023+): A1 equal-weight
  **+27.9% CAGR / -9.8% MaxDD / Calmar 2.83** vs SPY **+23.9% / -18.8% / 1.27** —
  beats SPY on raw return *and* crushes it risk-adjusted (half the drawdown). The
  equal-weight arm cross-checks the documented A1 27.2% CAGR, so it's faithful.
- **Cap-weight is NOT an improvement** — the hypothesis ("closes 30-50% of the SPY
  gap") is refuted because *there was no gap to close*. Cap-weight nudges CAGR up
  but worsens drawdown and Calmar. **Keep equal-weight; do not cap-tilt A1.**
- **So the "underperforming SPY" framing was a measurement artifact for A1** — it
  tracked the *live paper window* (1-2 months = noise, plus the infra/timezone/
  execution bugs fixed late May 2026), not the strategy. This is Tier 3 #6 ("is
  FIRE supposed to beat SPY?") answered with data: **A1 is a low-drawdown SPY-
  *alternative*; the right benchmark is risk-adjusted, not raw CAGR.**
- **Caveat + refocus:** survivorship inflates A1's *absolute* CAGR ~1-2pp (C3);
  SPY's number is clean; the drawdown/Calmar edge is robust (it comes from the SPY
  trend filter going defensive). This tested **A1 only** — the book's real soft
  spots are **A2 (MARGINAL, ~11% CAGR)** and **A4 (live execution drag)**. Point
  breakthrough energy there, not at a broad "beat SPY" goal A1 already meets.

The ranked avenues below still stand for A2/A4 and for net-new sleeves — but read
the "equal-weight gets crushed" diagnostic in the next section as *the hypothesis
we tested and refuted for A1*, not a standing conclusion.

---

## Diagnostic: Why we're underperforming SPY (specifically, in 2026)

### The single biggest unexamined assumption: equal-weight top-N

SPY is **market-cap weighted**. A1 is **equal-weighted top-15 momentum**.

In 2026, we're in extreme cap concentration — NVDA + a few others are ~25-30% of SPY by themselves. Even when A1 *holds* NVDA, it holds it at 6.7% (1/15), while SPY holds it at 6-7% standalone and the rest is in other big winners by cap-weight.

In a **dispersed regime** (2003-2007), equal-weight beats cap-weight handily. In a **concentration regime** (2020-2024, 2026 YTD), equal-weight gets crushed.

This is a 1990s-vintage academic convention. The literature standardized on equal-weight 30 years ago because it removed cap bias for testing factor premiums. But that's a *testing* convention, not an *investing* convention. It makes you systematically wrong about the concentration trade.

**Concrete first test (~2 days):**
- Rebuild A1's signal generation unchanged, but apply **cap-weight** OR **sqrt-cap-weight** within the top-15 selection.
- Hypothesis: closes 30-50% of the SPY gap immediately.
- Even cleaner: **concentration-adaptive weighting** — when top-5/total cap ratio > X, lean cap-weight; when dispersed, lean equal-weight. A real signal nobody publishes on because academics standardized on equal-weight.

> **✅ RESULT (2026-05-29):** Done. A1 equal-weight *already beats* SPY OOS
> (Calmar 2.83 vs 1.27, half the drawdown); cap-weight raised CAGR slightly but
> worsened drawdown + Calmar → **not an improvement; hypothesis refuted (no gap to
> close).** The "equal-weight gets crushed" claim above is false for A1's realized
> return profile. Keep equal-weight. Concentration-adaptive weighting is now low
> priority (no gap to adapt away). See top-of-doc update + `capweight_diagnostic_results.md`.

### Other contributing factors

1. **Public factor decay (McLean-Pontiff 2016)** — published factors decay 58% post-publication on average. Rigorous implementation of decayed public factors ≈ market returns minus costs.
2. **No proprietary signal/data edge** — chose discipline over private data. Coherent trade, but caps upside at "well-run small quant shop."
3. **Self-imposed constraints** — no shorting, no margin, no futures, no non-price signals yet. Each was chosen for a reason; together they make a small box to find alpha in.
4. **Sample size** — 2 months is statistically meaningless. A Sharpe-1.5 strategy has 30-40% chance of being down over any random 2-month window. Honest answer to "are these bad?" right now is *we don't know yet*.

The disappointment isn't a quality problem; it's an **expectations problem and a search-space problem**.

---

## Concrete breakthrough avenues — ranked

### Tier 1: Non-academic, free data, structurally different

#### 1. Crypto on-chain microstructure

The published crypto literature is mostly bad extrapolations of equity factors. The actual edge is in **flows and positioning**, not price momentum:

- **Funding rates** (Coinglass, free) — perp funding > 0.05%/8h = retail leveraged long; mean-reverting fade trade. Documented edge in BIS 2023, Aug-Hagstromer.
- **Exchange netflows** (CryptoQuant free tier, Glassnode) — BTC leaving exchanges = HODL signal; entering = selling pressure.
- **Stablecoin supply changes** — leading indicator for crypto inflows.
- **Liquidation cascades** — predictable mechanical levels, observable in advance via on-chain.
- **MSTR / IBIT premium-to-NAV** — basis trade on BTC exposure vehicles.

Could be its own account, or replace A4's price-momentum approach entirely. Same broker, same universe, **different signal**. Edge is mechanical/observable, not psychological.

**Build cost:** 1-2 weeks for the data pipeline. Pick 2-3 signals, not all 5.
**Why it might work:** Truly orthogonal to factor literature. Crypto microstructure is observable in a way equity microstructure isn't (level-1 vs on-chain).
**Why it might not:** Most on-chain signals have been picked up by sophisticated crypto funds already. Edge is shrinking; need to be in the right slice.

#### 2. VIX term-structure carry

Already scoped in `BOOK_SHAPE.md` Gap 3. **Cleanest one to build first.**

- VIX9D/VIX3M ratio: backwardation = sell short-vol exposure, contango = ride the carry.
- 20+ years of FRED data, **zero AI, deterministic**.
- Doesn't pick stocks — modifies *exposure* across accounts.
- Implementable in ~1 week.

Even if it just adds Calmar without adding CAGR, it's a real diversifier. Strong scoutreport candidate from 2026-04-23 (BOOK_SHAPE Tier 1).

**Build cost:** ~1 week.
**Why it might work:** VRP is one of the most-documented persistent edges. Term structure adds regime awareness.
**Why it might not:** It's mostly a short-vol factor, not alpha (Israelov caveat). Real edge is the *timing* of when to harvest vs when to step aside.

#### 3. CEF discount-to-NAV mean reversion

Closed-end funds trade at premiums/discounts to NAV that mean-revert (Pontiff 1997). Mechanism is **structural capital flight**, not price momentum — totally orthogonal to A1/A2/A4.

- Free data (CEF Connect, free tier).
- Hold 5-10 CEFs at 1-year-extreme discount → revert to median over 30-60 days.
- 5-8% annual edge in academic literature, lightly arbed in mid-cap CEF space (size = advantage).
- Long-only, Alpaca-tradeable, low turnover.

**Build cost:** ~1 week.
**Why it might work:** Genuinely structural mechanism (forced selling by retail), small-AUM advantage.
**Why it might not:** Many CEFs trade at perpetual discount; "mean reversion" depends on right identification.

### Tier 2: Event-driven, free SEC data, slow decay

#### 4. Insider buying clusters

Lakonishok-Lee (2001) + replications: when **3+ insiders** make open-market buys in same 30-day window, forward 6-month return averages **+6-8% excess**.

- **Not single-insider** — that's noise.
- **Cluster signal** is the edge.
- Free data: SEC EDGAR Form 4.
- Mid-frequency (~50-100 candidates/year).
- **Slow factor decay** — insiders have private info; that doesn't get arbed away.

**Build cost:** 1 week for data pipeline; 1 week for backtest.
**Why it might work:** Insiders know things you don't, and they back it with their own money. Hard to fake.
**Why it might not:** Many "clusters" are pre-planned, not signal-bearing. Need to filter for genuine conviction buys (non-10b5-1 plans, larger position sizes).

#### 5. Spinoff drift

Greenblatt thesis. Initial spinoffs are dumped indiscriminately by index funds (parent index rebalances OUT of the spinoff), creating short-term mispricing.

- ~20-30 US spinoffs/year.
- Hold 60-180 days post-spin, target 5-10% excess.
- Free data: SEC EDGAR (Form 10).
- Genuinely uncorrelated to everything else in the book.

**Build cost:** ~1 week.
**Why it might work:** Mechanical mispricing from forced selling. Greenblatt documented it; it's persisted.
**Why it might not:** Too thin for standalone — could layer with other event-driven (buybacks, 13D) into a single sleeve.

### Tier 3: Reframe the benchmark

#### 6. Is FIRE supposed to beat SPY at all?

If FIRE is meant to be a **complement** to SPY (different drawdown profile, different correlation in stress), then "underperforming SPY" is comparing apples to oranges.

If your real wealth allocation already has SPY exposure via other accounts (401k, taxable index funds), then FIRE's job isn't "beat SPY" — it's "add risk-adjusted return without correlating to SPY." Then the right benchmark is "60/40 portfolio" or "SPY + 5y treasury," not SPY alone.

If FIRE *is* supposed to beat SPY on standalone basis... then you need either:
- (a) **leverage** (Alpaca paper says no)
- (b) **concentration** (current book is diversified by design)
- (c) **signals SPY doesn't have** (the breakthrough question)

Worth deciding which one before benchmarking further.

#### 7. Concentration instead of diversification

Equal-weight 15 stocks = academic diversification. **Highest-conviction 3-5 stocks** with position sizing by signal strength = how actual outperformers run money (Buffett, Druckenmiller, Tepper).

This is a **philosophy shift**, not a strategy tweak. Worth considering whether 15 names is the right number for our book size and George's risk tolerance.

**Build cost:** ~3-5 days for backtest comparison.
**Why it might work:** Concentration captures the actual signal strength rather than diluting it across the top-15.
**Why it might not:** Drawdowns are 2-3x. Requires conviction in signal-strength ranking, not just rank ordering.

---

## What to NOT spend time on right now

- **More factor strategies** — Tier 1 saturated; April 2026 A5 hunt confirmed diminishing returns.
- **LLM-as-stock-filter** — two prior kills (Breakthrough #1, Mode 2 PEAD mega-cap). Don't be the third casualty on the same architecture.
- **ML regime overlay before price-based regime overlay** — Build the simpler one first (VIX term-structure / FRED composite). ML is the escalation, not the start.
- **Parameter optimization on existing strategies** — overfit risk, marginal upside.
- **Adding more universes** — depth > breadth.

---

## Top picks for "where do we actually start"

| Priority | Vector | Cost | Information value |
|---|---|---|---|
| **✅ DONE 2026-05-29** | Cap-weight rebuild of A1 | done | **Answered: A1 already beats SPY OOS (Calmar 2.83 vs 1.27); cap-weight not an improvement. The SPY "gap" was the live window, not the strategy. Keep equal-weight.** |
| **One real new direction** | VIX term-structure carry as A5 | ~1 week | Cleanest path, well-scoped, FRED data, zero AI |
| **Highest-EV long-term** | Crypto on-chain signals | 1-2 weeks | Only avenue with real edge outside public equity literature |

---

## Open questions for future session

- Should we treat A1 as fixed and just add an A5, or is the cap-weight question worth revisiting A1 itself? (Probably build A5 separately, leave A1 running to its 6-month proof point.)
- If crypto on-chain signals are an A5 candidate, does that replace A4 or sit alongside? (Likely sit alongside; A4 has SMA-125 filter + vol-scaling, on-chain is different signal.)
- Is the right next sprint **build one** of these or **deeply scope two-three before committing**? (Probably scope 2-3 to ~5-page docs each, then pick one; avoids prematurely committing to the first one that "felt good.")
- What's the bridge-math implication if we find one that adds 4-6pp book CAGR? Does that change the FIREMaster scenarios? (Yes — meaningful upside lever to bridge-math worst case.)

---

## How this relates to existing research docs

- **BOOK_SHAPE.md** — Gap 1 (crisis alpha), Gap 2 (non-price edge), Gap 3 (regime adaptivity). This doc maps concrete vectors to those gaps:
  - Crypto on-chain → Gap 2 (non-price edge in crypto)
  - VIX term-structure → Gap 3 (regime adaptivity)
  - CEF discount → Gap 2 (non-price, structural)
  - Insider clusters → Gap 2 (informational alpha)
  - Spinoff drift → Gap 2 (event-driven)
- **HighYield_Strategy_STRC_NVDY_AMZY.md** — different objective (bridge income), not on this list because not a CAGR/Calmar play. Still a live candidate but evaluated by its own criteria.
- **ML_REGIME_OVERLAY.md** — comes AFTER price-based regime overlay proves insufficient, not before.
- **RATE_VOL_SCOPE.md** — shelved (MOVE at multi-year lows).

---

## Key insight to preserve

> *"The disappointment isn't a quality problem; it's an expectations problem and a search-space problem. The breakthrough probably comes from leaving the box, not optimizing within it."*

The system was built with rigorous discipline around **public factor literature**. Public factor literature has 58% decay (McLean-Pontiff). Rigorous implementation of decayed factors = market returns minus costs. That's a structural ceiling. **The discipline produced an honest backtest, not a proprietary edge.**

Breakthroughs from this point need to be **structurally different**, not "another factor with a tweak."
