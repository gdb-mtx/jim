# AUDIT_FABLE — Full-System Review & Path Forward

**Date:** 2026-06-09
**Scope:** All code, all docs, live paper performance (snapshots, rebalance logs, signal tracker, validation state), every research vector in `docs/research/` and the April 2026 hunt archive, plus a first-principles survey of out-of-distribution strategy space.
**Method:** Four parallel research agents (live performance, book/code, research pipeline, OOD survey) + direct verification of every load-bearing external claim against the Alpaca API and current sources.

---

## 1. Executive verdict

The system is **better built than it is invested**. The discipline layer — validation gates, kill discipline, sim/live parity work, ops monitoring — is genuinely above-peer for a solo operator. The alpha layer is three textbook academic price factors (Jegadeesh-Titman momentum, Faber trend + low-vol, 21d crypto momentum) with literature-default parameters, all in one factor family: long price persistence on liquid US assets. Walk-forward refit (Test 6) confirms there is no tuning alpha left in them. That is *why* the book is middle-of-the-road — it is at the efficient frontier **for the current constraint set**, exactly as HUNT_APR2026 concluded.

The breakthrough therefore cannot come from another momentum variant (12 vectors tested and killed prove this). It comes from one of three moves, in this order of conviction:

1. **New data families** — EDGAR events (insider clusters, buybacks, spinoffs, index deletions), crypto funding rates, NAV discounts. Non-price edges decay slowly because they're not published-factor harvesting.
2. **A wider instrument set that was wrongly assumed locked** — VIX ETPs, options L1–3, and CFTC-regulated crypto perps are all reachable *today* without leaving Alpaca or breaking US rules (verified 2026-06-09, see §4).
3. **Honest leverage** — the cap=1.5 vol-scaling sprint and the Gayed leveraged-trend test, if the real ask is "40% CAGR" rather than "uncorrelated streams."

But none of that matters until the two live fires in §2 are out: **the A4 daily cron is dead again (no fires since 06-06), and A4's execution drag reached +17.9pp** — the live implementation has not been trading the strategy the backtest validated.

---

## 2. State of the live book (as of 2026-06-09)

### Performance vs promise

| Account | Live window | Return | Annualized | Backtest promise | Verdict |
|---|---|---|---|---|---|
| A1 Momentum | since 03-06 (95d) | **+5.4%** | +22.5% | +27.2% CAGR | **Tracking.** DD (-3.4%) well inside envelope. The one account delivering. |
| A2 Trend+LowVol | since 03-09 (92d) | **-1.9%** | -7.3% | +11.0% CAGR | Underperforming ~18pp annualized; absolute damage small. MARGINAL strategy doing marginal things. |
| A4 Crypto | since 04-22 (48d) | **-23.1%** | -86% | +38.6% CAGR | **Broken vs promise.** Decomposition below. |
| Combined | since 04-21 reset | **-7.1%** | — | +26.5% CAGR, -6.2% MaxDD | Live combined DD (-7.6%) already exceeds the *entire 3-year backtest MaxDD* after ~3 months. Entirely attributable to A4. |

### A4 decomposition — the central live finding

Signal-only return over the same window: **-5.2%** (regime — BTC rolled over; the backtest would also be down). Live: **-23.1%**. **Execution drag: +17.9pp**, roughly 3.5× the late-April figure, and still accruing (+3.4pp in the 19 days before 06-01). The drag is lumpy, not uniform:

- **-6.85pp on 2026-05-08 alone**, coinciding with a `liquidate_account` event (23:24 UTC, 4 orders, 1 failed). Needs forensics — if that liquidation was a deliberate manual action, a chunk of "drag" is actually an operator event, which changes the diagnosis.
- +2.75pp on 05-06, a day the scheduled job fired **three times** (00:52, 01:17, 06:05 UTC) — anomalous, also needs forensics.
- ~+2.2pp on each of 04-23, 04-30, 05-28, 05-29.

STRATEGIES.md's claim that live↔signal "converged post-May-8" is **not supported by the data** — `--since 2026-05-20` still shows +3.41pp/19d. A4 has been 100% cash since 06-01 (BTC 14% below its 125d SMA), which froze the bleeding by luck of regime, not by fix.

Also concerning: A4's Test-2 walk-forward windows decay monotonically, 59% CAGR (oldest) → **9.6% CAGR, Calmar 0.87 (newest window, 2024-12→2025-12)**. The crypto momentum edge itself may be fading, independent of execution.

### Ops

- **The A4 daily cron has silently stopped — last fire 2026-06-06 02:05 UTC, three consecutive missed days.** This is scheduler failure mode #5 (APScheduler → launchd/BTM → cron/FDA → cron/Desktop-provenance → now laptop sleep + apparent timezone shift to UTC-6 moving the effective fire time, since cron fires at laptop-local 20:05). Harmless *only* while A4 is in cash; the moment BTC re-crosses its SMA, rotation resumes with no scheduler. The 4h filter check is alive but also shows ~19h sleep gaps. **[RESOLVED 2026-06-09:** system TZ confirmed America/Denver; replaced the fixed `5 20 * * *` entry with an hourly :10 trigger + `--if-due` UTC date-check in the script — runs once per UTC day at the first awake hour, TZ-immune, sleep-tolerant, retries failed runs hourly. Catch-up run executed same day (`no_trades`, A4 in cash). See AUTOMATION.md. Fly.io remains the durable fix.**]**
- A1/A2 manual 21-day cadence honored; next due 06-22.
- Validations current: A1 PASS, A2 MARGINAL, A4 PASS (expires 08-15). Cosmetic bug: "Win rate 0.0%" in all reports.
- Filter state correct (SPY on, BTC off). No halts; A4's -23% breached the -10% banner tier only, as designed.

**The laptop is the bug.** Five scheduler failure modes in three months is not five bugs — it's one architectural fact. DEPLOYMENT_PLAN's Fly.io migration stops being "Phase 5 hardening" and becomes a precondition for trusting any daily-cadence strategy.

---

## 3. Diagnosis — why middle-of-the-road, precisely

In rank order of contribution:

1. **The signals.** All three live strategies are fully-harvested published price factors in one family. The RenTech K=4 experiment proved the point: a fresh-looking 5-signal composite cleared every OOS gate and still landed at 0.84–0.87 correlation to A1/A2. Within the price-momentum family, "new strategy" = "same factor, new costume." McLean-Pontiff decay applies to everything live.
2. **The constraint set as previously understood.** No shorting/futures/options meant carry, vol-premium, and crisis-alpha families were inexpressible. §4 shows this understanding is now partly stale.
3. **The one-directional risk overlay.** Vol-scaling hard-caps at 1.0 (`execution/rebalance.py:358`) — the overlay can only de-risk, never extend. The deferred cap=1.5 sprint (~+2pp book CAGR, 3–5 days, deterministic) is free money still on the table, and Alpaca paper equity accounts have Reg-T margin.
4. **Not the universe, not the weighting.** The 2026-05-29 cap-weight diagnostic settled this: A1 equal-weight beats SPY risk-adjusted (Calmar 2.83 vs 1.27). The felt "SPY gap" was live noise + bugs.
5. **Not (mostly) the execution layer** — except on A4, where it currently dominates everything else (§2).

The three BOOK_SHAPE gaps (crisis alpha, non-price edge, regime adaptivity) remain the correct map. All three are still unfilled. Every recommendation in §5 fills at least one.

---

## 4. Facts verified 2026-06-09 that change the calculus

These were checked directly, not taken from the agents' claims:

1. **SVXY, VIXY, UVXY, SVIX, VXX are tradeable on Alpaca** (confirmed via `get_asset` against the live paper API: all `tradable: True, status: active`). BOOK_SHAPE's framing that the VIX-carry sleeve and a long-vol crisis leg require IBKR/futures is **wrong**. Gap 1 and the Tier-1 VIX vector are Alpaca-reachable today.
2. **Alpaca options Level 1–3 are live, and paper accounts automatically get Level 3** (multi-leg). The "no options infrastructure" constraint is self-imposed, not broker-imposed.
3. **CFTC-regulated crypto perpetual futures are open to US retail** — Coinbase Financial Markets nano BTC/ETH perps since July 2025 (10x, ~0.02% fees); Kraken likewise. Delta-neutral funding/basis carry is now US-legal without offshore games.
4. **DBMF, STRC, NVDY, AMZY all tradeable on Alpaca** — the crisis-conditional A2 swap and the yield-flywheel track need no broker work either.
5. Also confirmed tradeable: SSO/UPRO/TQQQ (relevant only to the §6 leverage question).

Consequence: **the urgency of IBKR migration drops, but its eventual breadth grows.** Re-score it as a bundle (futures CTA + odd-lot tenders + SPAC redemptions + shorting + box-spread financing at $150K+), not on CTA alone. Not a 2026-Q2/Q3 priority.

---

## 5. The path forward

### Phase 0 — out the fires (this week, before any research)

1. **A4 cron is dead.** Either resurrect with a timezone-proof mechanism *and* accept the laptop's sleep behavior as a standing risk, or — the real fix — **pull DEPLOYMENT_PLAN forward and put the daily rebalance on Fly.io now**, paper keys only. Five silent failure modes is the system telling you something.
2. **A4 execution-drag forensics** before A4 ever re-enters (BTC re-crossing its SMA is the deadline, and you don't control when that happens). Explain the 05-08 liquidate_account -6.85pp day and the 05-06 triple-fire. Decide: is drag (a) ops events misattributed as drag, (b) entry-timing/whipsaw structure, or (c) genuine slippage? Each has a different fix. Until explained, **A4 re-entry should be gated** — add a manual-confirm or reduced-weight first re-entry.
3. **Close out the Mode 2 C recommendation** — the 40-day hold expired; the tracker still says `status="open"` with null outcomes. Ten minutes. The track's only trade deserves an outcome row.
4. Fix the "Win rate 0.0%" reporting bug when convenient (cosmetic, but it erodes trust in the reports).

### Phase 1 — the breakthrough builds (next 4–8 weeks, ranked)

**1. A5-Events: one pooled event-driven sleeve, not four thin strategies.** Insider buying clusters (3+ insiders, open-market, non-10b5-1, $200M–$5B caps — Lakonishok-Lee +6–9%/6mo, slow decay) + the shelved **mid-cap buyback drift GO** (the only clean GO verdict of the April hunt, shelved on fatigue, with a pre-designed 1-day kill test) + **index-deletion reversion** (the surviving half of reconstitution — forced selling of deletes, ~5pp/yr excess; additions are dead) + spinoff drift. Each stream alone failed the April hunt's "too thin" test; **pooled on one shared EDGAR harness they become a continuously-deployed 30–80 position/yr book.** This is how a $50K account is *supposed* to consume thin edges — it's the structural retail advantage. Realistic pooled sleeve: 12–20% CAGR, Calmar 1.2–2.2, near-zero calm-regime correlation to A1/A4. Direct Gap-2 fill. Shared harness ~1 week; each stream 2–4 days after. **Start with the buyback 1-day kill test — it's already designed.** Slot: the retired A3 account.

**2. VIX term-structure regime-switched vol sleeve — now unblocked.** The signal (VIX9D/VIX3M + futures basis) was already Tier-1-scoped; §4.1 removes the broker excuse. Contango → harvest carry (SVXY, hard-capped); backwardation → long vol (VIXY) = **the book's first true crisis-alpha leg** (Gap 1) from the same signal that improves regime adaptivity (Gap 3). ~1 week. Non-negotiable sizing rule: the short-vol side must be sized for a -50% overnight gap (XIV died -90% intraday in Feb 2018); cap the sleeve at 10–15% of book, ever.
3. **Crypto funding-rate overlay on A4 (3 days, Coinglass free API).** Extreme positive perp funding = crowded leverage = cut A4 exposure. Cheapest information buy available on the book's weakest account, and the entry ramp to the bigger prize: **delta-neutral basis carry** (long spot Alpaca / short CFM nano perp), the only price-direction-independent return stream on the menu (8–20% CAGR in carry regimes, Calmar 2–4 when on). The carry build is 3–4 weeks and all liquidation-risk engineering — do it only after the overlay proves the data pipeline.
4. **Price-based macro composite (~1 week, deterministic).** WALCL/DXY/M2/credit/VIX-TS → book-level exposure scalar. Fills Gap 3, is the pre-committed prerequisite for any ML work, and overlaps features with #2. Bundle them.

### Phase 2 — conditional / decision-gated

- **cap=1.5 vol-scaling sprint** (3–5 days, ~+2pp book CAGR): highest-confidence ROI-per-hour in the backlog. Do it the week something else is blocked on data.
- **A2's fate:** leave it alone until the 2026-Q4 review. It's doing its job (0.32 correlation ballast); low_ivol replacement already tested and killed (Calmar 3.13→2.09). If live Calmar <1.0 at review, the DBMF swap trigger exists.
- **A4 upgrade clock:** the 33%→40% pre-commitment is **off the table** until drag is explained and a clean ≥6-month window exists. Walk-forward decay (§2) argues for *demotion* consideration, not promotion, if the newest-window pattern persists through Q3.
- **Norgate Data (~$30/mo):** buy it when (not if) any micro-cap or point-in-time work starts — it closes C3 (survivorship, the known pre-real-money blocker) as a side effect. Micro-cap quality-momentum itself: bench until the event sleeve ships; widest error bars in the survey.
- **Yield flywheel (STRC/NVDY/AMZY):** STRC confirmed tradeable on Alpaca (§4.4), so the build is unblocked, but it's a *bridge-income* decision, not a Mode-1 breakthrough — it belongs to the FIREMaster conversation. Don't let it queue-jump the event sleeve.
- **Mode 2:** the honest in-house conclusion stands — large-cap PEAD is 1–3%, Claude-as-forecaster killed twice. The salvageable remnant is the LLM-as-**event-classifier** architecture (materiality-classifying 8-Ks / DoD contract awards for the event sleeve) — a different machine than the killed return-forecasters, and the existing kill-fast methodology applies. One-week falsification experiment, only after A5-Events' harness exists.

### What NOT to do (the dead list — do not re-litigate)

Crypto cross-sectional reversal; MOVE×TLT rate-vol; index **addition** front-running; RenTech-style ensembles (dilution or 0.84+ correlation); low_ivol as A2 swap; LLM-as-stock-picker (killed twice — "don't be the third casualty"); leveraged-ETF decay shorting (borrow fees eat it, needs shorting anyway); overnight anomaly, dividend capture, seasonality (dead net of costs); cross-exchange crypto arb (KYC walls); free-tier alt-data (paid funds arbed the investable subset); mega-cap PEAD standalone; cap-weight A1 tilt (tested 05-29, worsens Calmar); 0DTE/dispersion (fails solo-operator test); AI FOMC overlay (skip, period, until the macro composite proves insufficient).

---

## 6. The question only George can answer

"Breakthrough" is doing double duty in the project's vocabulary, and the two meanings point at different builds:

- **Breakthrough = 40%+ CAGR.** The honest, cheap, ugly answer is **leveraged-trend (Gayed)**: point the existing SPY-200d filter at SSO/UPRO. 2–3 days to test, documented 25–45% CAGR with -25 to -45% drawdowns, Calmar ~1.0–1.5. It is not alpha — it's amplified, filter-gated beta that raises CAGR and crash-beta together. It would blow through the current book's -6.2% drawdown identity.
- **Breakthrough = return streams the current book doesn't have.** That's §5 Phase 1: events, vol-regime, carry. Realistic outcome is a book at 25–32% CAGR with *materially higher* crisis resilience and a Calmar that survives the next 2022 — not a 40% headline.

The audit's recommendation is the second path, with the leveraged-trend test run anyway as a 2-day experiment — not to deploy, but to put a real number on what the first path costs in drawdown, so the choice is made with data instead of vibes.

**Recommended 8-week sequence:** Phase 0 fires (week 1) → buyback 1-day kill test + EDGAR harness (weeks 1–3) → VIX sleeve + macro composite bundle (weeks 3–5) → funding overlay (week 5) → second event stream + leveraged-trend diagnostic (weeks 6–8). End state: A3's slot re-occupied by A5-Events, a vol sleeve with a long-vol crisis leg, A4 either fixed or demoted, and the daily cadence running somewhere that doesn't sleep.

---

*Sources for §4 external claims: [Alpaca options levels](https://docs.alpaca.markets/us/docs/options-trading-overview) ([support: tiers](https://alpaca.markets/support/what-option-levels-or-tiers-do-you-provide), [L3 announcement](https://alpaca.markets/blog/level-3-options-trading-now-available-with-alpacas-trading-api/)); [Coinbase CFTC perps launch](https://cryptobriefing.com/us-perpetual-futures-cftc-launch/) ([coverage](https://cryptonews.com/news/coinbase-launches-cftc-regulated-perpetual-futures-for-us-retail-traders/)). VIX ETP / DBMF / STRC tradability verified directly against the Alpaca paper API (`get_asset`), 2026-06-09.*
