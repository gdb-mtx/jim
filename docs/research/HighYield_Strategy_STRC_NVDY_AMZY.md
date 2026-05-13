# Yield-Harvesting Flywheel — Scoping Doc (2026-05-13)

**Goal:** Build a yield-harvesting strategy for Account 5 that generates income exceeding a target withdrawal rate during the bridge-to-59.5 years, with principal preservation. Paper-trade first; real capital only after 6+ months of live evidence.

**Why this approach:** The existing Mode 1 book (A1+A2+A4) targets capital appreciation via factor timing — momentum, trend, mean-reversion. All three accounts depend on perfect execution of daily/monthly signal rotation. A4's first 3 weeks of live trading show +4.61% signal-only but **-7.29% live** (12pp execution drag). Beautiful backtests do not guarantee live results. A yield strategy that generates distributions mechanically — hold positions, collect income, reinvest — has structural execution simplicity that factor-timing strategies lack. The edge is in instrument selection and allocation, not in execution speed.

**Critical framing:** This is NOT a Mode 1 factor strategy. Success criteria are **withdrawal coverage ratio**, **total return with DRIP**, and **drawdown in stress** — not the CAGR >= 15% / Calmar >= 1.0 gates. Different objective function, different evaluation framework.

**Current regime caveat (2026-05-13):** All three instruments are novel (STRC ~10 months old, NVDY ~3 years, AMZY ~2.8 years). History is thin. STRC is 100% Bitcoin-derivative credit risk — launched during a BTC bull market, untested in a prolonged bear. YieldMax ETFs structurally erode NAV by design. "Testing" this strategy is fundamentally forward-looking — there is no meaningful backtest horizon in the A1-A4 sense (16 years, multiple regimes).

**Origin:** George's independent research into STRC, iterated with Gemini across multiple sessions (2026-05-04 onward). Strategy evolved from STRC/SATA+MSTY to STRC/NVDY/AMZY. Bridge-plan context (funding sources, SEPP 72(t) deployment, property sales) is in FIREMaster (`STRATEGY_CAPSULE.md`, `BRIDGE_STRATEGY_REVIEW.md`).

---

## 1. Honest Thesis

**The bridge math:** George needs reliable monthly income for ~76 months (age 53 to 59.5). If capital deployed at a blended yield that exceeds the withdrawal rate, principal either holds flat or grows. The strategy works if:

1. The instruments actually pay what they advertise (total return, not headline yield)
2. NAV erosion on the YieldMax sleeve doesn't destroy principal faster than yield replaces it
3. No credit event wipes STRC

**Why it might work:**

- STRC's variable-rate mechanism adjusts dividends to anchor price near $100 par — the issuer has a structural incentive to maintain the yield (STRC was 5x oversubscribed at IPO; it's a capital-raising engine for their BTC acquisition strategy)
- YieldMax weekly distributions provide cash flow velocity — income arrives 52x/year, compounding faster than monthly or quarterly alternatives
- The 80/10/10 mode keeps 80% in the most stable instrument (par-anchored STRC) with only 20% in the structurally-eroding YieldMax sleeve
- DRIP reinvestment compounds in bridge years when George may not need to withdraw all yield — excess yield buys more shares

**Why it might not work:**

- **STRC credit risk (the big one):** STRC is unsecured perpetual preferred equity. Dividends are funded by BTC appreciation and new capital raises. Bitcoin generates no cash flow. In a prolonged BTC bear (2022-style, 18 months), Strategy Inc. could suspend dividends without triggering default. No maturity date, no covenant protection, no seniority in bankruptcy.
- **YieldMax NAV erosion is structural, not cyclical.** The covered-call mechanism systematically sells upside volatility. AMZY's price-only CAGR is -4%/yr — the ETF is literally returning your capital as "distributions." The question is whether total return with DRIP is positive despite this erosion.
- **Correlated tail risk.** STRC (BTC-derivative), NVDY (NVDA-derivative), AMZY (AMZN-derivative) are all tech/risk-on instruments. In a 2022-style coordinated selloff, all three underperform simultaneously. "Diversification" across three instruments is cosmetic — the underlying factor exposure is "long tech/crypto risk appetite."
- **History is too short to distinguish a genuine yield premium from a bull-market artifact.** 10 months of STRC and 3 years of NVDY is one macro regime.

---

## 2. Instrument Analysis

Real numbers, not headline yields.

### STRC — Strategy Inc. Variable Rate Series A Perpetual Preferred Stock

| Field | Value |
|---|---|
| **Type** | Perpetual preferred stock (NOT an ETF, NOT a bond) |
| **Issuer** | Strategy Inc. (formerly MicroStrategy, NASDAQ: MSTR) |
| **Launched** | July 2025 (~10 months ago) |
| **Price** | ~$100 (par-anchored via variable rate mechanism) |
| **52-week range** | $88.00 - $100.42 |
| **Stated yield** | 11.5%/yr variable rate (started at 9.0%, raised 7 consecutive months) |
| **Payout** | Monthly cash. Semi-monthly shift under shareholder vote (June 2026). |
| **Total return with DRIP** | ~11.5% annualized (price roughly flat + distributions) |
| **Max observed drawdown** | ~12% from par (Nov 2025, $88 low, recovered in ~20 days) |
| **Distribution composition** | Classified as ROC (lowers cost basis; basis hits $0 in ~105 months at current rate) |
| **Credit structure** | Unsecured preferred equity. Dividends NOT contractually guaranteed — can be suspended. |

**Mechanism:** Issuer adjusts dividend rate monthly in ~0.25% increments to keep price near $100 par. If price dips, rate rises to attract buyers. If price rises, rate falls. Cumulative: missed payments remain owed. Strategy Inc. raised $2.5B from STRC and deployed nearly all of it into Bitcoin.

**Key risk:** Single-issuer credit event. If BTC enters a prolonged bear and Strategy Inc. faces liquidity pressure, dividends could be suspended and price could fall well below par.

### NVDY — YieldMax NVDA Option Income Strategy ETF

| Field | Value |
|---|---|
| **Type** | Actively managed ETF (synthetic covered call on NVDA) |
| **Launched** | May 2023 (~3 years ago) |
| **Price** | ~$13-14 |
| **Headline distribution yield** | ~43-71% (varies by measurement period) |
| **Total return with DRIP since inception** | **+96%** (~30% annualized) |
| **Price-only performance** | Significant NAV erosion (~35-48% from launch) |
| **Max drawdown** | ~34% |
| **Expense ratio** | 0.99% |
| **Recent distribution composition** | 0-92% ROC (varies wildly week to week) |

**Mechanism:** NVDY does NOT own NVDA shares. It holds Treasuries as collateral and uses options to create synthetic long exposure, then sells call options 0-15% above current price to generate premium income. The premium is distributed weekly. Upside is structurally capped at the short call strike.

**Key risk:** In a sustained NVDA bull market, NVDY dramatically underperforms NVDA on total return (~26% capture ratio). The "yield" is compensation for surrendered upside. In a bear market, the synthetic long loses money while option premium provides a partial buffer — but this has not been tested through a real recession for NVDY specifically.

### AMZY — YieldMax AMZN Option Income Strategy ETF

| Field | Value |
|---|---|
| **Type** | Actively managed ETF (synthetic covered call on AMZN) |
| **Launched** | July 2023 (~2.8 years ago) |
| **Price** | ~$11-12 |
| **Headline distribution yield** | ~50-54% |
| **Total return with DRIP since inception** | **~27% annualized** |
| **Price-only CAGR** | **-4%/yr** (NAV erosion) |
| **Max drawdown** | ~24% |
| **Expense ratio** | 0.99% |
| **Recent distribution composition** | **97.72% ROC** (May 6, 2026) |

**Mechanism:** Identical to NVDY but on AMZN. Synthetic covered call, weekly distributions, capped upside.

**Key risk:** Nearly all recent distributions are ROC. The ETF is returning your capital and calling it yield. Total return with DRIP is meaningfully positive (~27%/yr) because AMZN has been strong — but if AMZN stalls or declines, the math inverts quickly.

### Blended Yield Estimates

| Mode | STRC | NVDY | AMZY | Blended headline yield | Estimated total return with DRIP |
|---|---|---|---|---|---|
| Safe Bridge (80/10/10) | 80% | 10% | 10% | ~18.5% | ~15-17% (estimate, needs verification) |
| Aggressive Flywheel (50/25/25) | 50% | 25% | 25% | ~28.9% | ~20-23% (estimate, needs verification) |
| STRC-only (100%) | 100% | — | — | 11.5% | ~11.5% |

**Note:** "Estimated total return with DRIP" is back-of-envelope from per-instrument numbers. Day 1 of the build verifies these from actual data. The blended numbers assume static allocation — the flywheel sweep (directing YieldMax dividends toward STRC) would change the effective allocation over time.

---

## 3. Data Availability & Backtest Feasibility

### Available data

| Ticker | Source | History | Quality |
|---|---|---|---|
| STRC | yfinance | ~10 months (Jul 2025-present) | Price only; distributions need manual supplement |
| NVDY | yfinance | ~3 years (May 2023-present) | Price + `.dividends` attribute; verify DRIP accuracy |
| AMZY | yfinance | ~2.8 years (Jul 2023-present) | Same as NVDY |

All downloadable via `data/pipeline.py` → `download_and_cache()`.

### What FIRE's data pipeline currently lacks

FIRE has **zero dividend/distribution data infrastructure**. Every existing strategy operates on price-only adjusted returns. To evaluate this strategy, we need:

1. **Distribution history** — ex-dates, payable dates, amount per share, ROC percentage. yfinance's `.dividends` attribute may have this but needs verification against known distribution schedules from YieldMax and Strategy Inc.
2. **Total return with DRIP calculation** — not just adjusted close. Must verify whether yfinance `auto_adjust=True` properly handles weekly YieldMax distributions (it may not).
3. **Shadow ledger for paper-trade period** — Alpaca paper trading does NOT credit dividends. Virtual dividend tracking is prerequisite for any live measurement.

### Backtest feasibility: LOW

This is honest: 10 months of STRC is not enough for statistical inference. Even NVDY's 3 years covers one macro regime (post-2023 tech bull).

**What can be tested (due diligence, not backtesting):**
- Total return with DRIP over available history (2-3 years)
- Drawdown behavior during Feb 2026 BTC flash crash and Apr 2026 tech volatility
- Correlation to SPY, BTC, NVDA, AMZN, and the A1+A2 equity core
- Distribution consistency and ROC percentage trends
- Withdrawal simulation at various deployment sizes

**What cannot be tested:**
- Multi-regime performance (no 2022-style prolonged bear in the data)
- STRC behavior during a BTC bear >3 months
- YieldMax ETF behavior during a real recession
- Parameter stability (insufficient history for train/test split)

**Synthetic approximation (optional, deeply hypothetical):** Could construct a synthetic NVDY proxy using NVDA price history + CBOE implied vol + a mechanical covered-call writing strategy (analogous to the CBOE BuyWrite Index, BXM). Useful for order-of-magnitude intuition but NOT for parameter calibration. Would require options data not in the current pipeline.

---

## 4. Candidate Designs

### Mode A — Safe Bridge (80/10/10)

**Allocation:** 80% STRC, 10% NVDY, 10% AMZY

**Thesis:** This is really a STRC income position with a small high-yield satellite. The YieldMax sleeve adds marginal yield for DRIP compounding, but at 10% each, their NAV erosion has limited portfolio impact. The strategy is a bet on STRC par stability + 11.5% coupon, with a yield kicker.

**Expected behavior:** Low volatility (STRC is par-anchored), steady monthly income, modest total return. Drawdowns driven primarily by STRC credit events (rare but severe if they happen).

**Why this first:** Simpler, lower risk, most honest about what the strategy actually is. If STRC's par-anchor holds, this mode delivers ~15-17% total return with DRIP at low drawdown. The YieldMax sleeve is the optional upside, not the core.

### Mode B — Aggressive Flywheel (50/25/25)

**Allocation:** 50% STRC, 25% NVDY, 25% AMZY

**Thesis:** Higher income, higher DRIP compounding, but 50% of capital is in structurally-eroding NAV instruments. The "flywheel" mechanism (sweep YieldMax dividends into STRC) is supposed to prevent NAV erosion from eating principal — the high-yield sleeve feeds the stable anchor.

**Expected behavior:** Higher volatility, drawdowns driven by NVDA/AMZN selloffs, NAV erosion in flat markets partially offset by DRIP reinvestment. In a tech correction, 25% NVDY + 25% AMZY take 25-34% drawdowns simultaneously.

**Risk this introduces:** The flywheel sweep can't run fast enough to compensate for a sharp decline. Weekly sweeps help in slow erosion but not in a crash.

### Mode C — STRC-Only (100%)

**Allocation:** 100% STRC

**This is the null hypothesis.** Adding NVDY/AMZY only makes sense if their total return with DRIP exceeds STRC's 11.5% after accounting for NAV erosion and added drawdown risk. If STRC-only delivers comparable risk-adjusted income, the complexity of the YieldMax sleeve is wasted.

### Trend filter overlay (optional, all modes)

Existing FIRE infrastructure in `strategies/portfolio_config.py`:
- **SPY 200d MA filter** → apply to NVDY/AMZY sleeve. When SPY < 200d, reduce YieldMax to cash.
- **BTC 125d SMA filter** → apply to STRC. When BTC < 125d SMA, reduce STRC to cash.

The original Gemini spec proposed BTC 200d EMA for STRC and SPY 50d EMA for NVDY/AMZY. The 50d is much tighter than anything in FIRE (all existing filters use 125-200d). Default to existing infrastructure unless there's specific evidence for shorter periods.

**Filter caveat:** With only 3 years of NVDY data, the trend filter may activate 0-2 times. Too few events to draw conclusions, but worth tracking in the paper-trade.

---

## 5. Success Criteria

**These gates replace the Mode 1 validation gates for this strategy.** This is an income-floor strategy, not a factor-alpha strategy.

| Metric | Target | Rationale |
|---|---|---|
| **Withdrawal coverage ratio** | >= 1.5x | Monthly yield exceeds target withdrawal by 50% buffer |
| **Total return with DRIP (annualized)** | > 0% | Principal does not shrink with DRIP reinvestment |
| **Max drawdown (portfolio level)** | >= -20% | Wider tolerance than Mode 1 (-10%) but must not destroy principal |
| **Yield sustainability (trailing 6mo)** | Within 25% of initial | Distributions don't collapse over time |
| **Correlation to A1+A2 equity core** | < 0.6 | Some diversification benefit (lower bar than Mode 1's 0.4 — tech/crypto correlation is acknowledged) |
| **STRC credit event response** | Pre-committed exit plan | If STRC suspends dividend OR price < $80 for 10 consecutive days → full exit |

### Kill conditions (stop paper-trading and abandon)

1. **Total return with DRIP is negative** over first 6 months (principal shrinking despite income)
2. **STRC trades below $85** for more than 20 consecutive trading days (par-anchor thesis broken)
3. **YieldMax distributions cut by more than 50%** from trailing 12-week average (yield thesis broken)
4. **Blended portfolio drawdown exceeds -25%** (risk tolerance exceeded)

---

## 6. Implementation Plan

### What exists in FIRE (reusable)

| Component | Location | How it fits |
|---|---|---|
| Price data download + caching | `data/pipeline.py` → `download_and_cache()` | Pull STRC/NVDY/AMZY price history |
| SPY 200d trend filter | `strategies/portfolio_config.py` → `compute_spy_trend_filter()` | Apply to YieldMax sleeve |
| BTC 125d trend filter | `strategies/portfolio_config.py` → `compute_btc_trend_filter()` | Apply to STRC sleeve |
| Account 5 slot | `backtesting/account_adapters.py` → `_build_account_5()` | Available; A3 retired, slot preserved |
| Rebalance framework | `execution/rebalance.py` | Multi-account, handles Alpaca orders |
| Transaction cost model | `backtesting/costs.py` → `STRATEGY_COST_BPS` | Add `"yield_flywheel": 5.0` |
| Portfolio config dict | `strategies/portfolio_config.py` → `PORTFOLIOS` | Add `"yield_flywheel"` entry |

### What needs to be built (new)

| Component | Effort | Description |
|---|---|---|
| **Shadow ledger / dividend data** | ~2-3 days | `data/dividends.py` — fetch distribution history, cache as parquet, track virtual dividend credits for paper-trade period. This is the critical new infrastructure. |
| **Yield-aware strategy class** | ~1 day | `strategies/yield_flywheel.py` — mostly static allocation with drift correction, not daily signal generation. Flywheel sweep logic at the ledger layer. |
| **ROC basis tracker** | ~0.5 day | Part of shadow ledger. Track cumulative ROC per position, flag when basis approaches $0. Informational for tax planning. |
| **Withdrawal simulation overlay** | ~0.5 day | New utility: given $X deployed, $Y/month withdrawn, track principal trajectory over time. Core evaluation tool. |
| **Account 5 adapter** | ~0.5 day | `_build_account_5()` in account_adapters.py. `periods_per_year=252`, `walk_forward_supported=False` (insufficient history). |

### Build sequence with kill gates

**Day 1: Data pipeline + instrument due diligence**

1. Add STRC/NVDY/AMZY to `data/pipeline.py` download. Verify yfinance adjusted close incorporates distributions (compare to known total return with DRIP from ETF provider sites).
2. Build `data/dividends.py` — fetch distribution history from yfinance `.dividends` + manual supplement from YieldMax/Strategy Inc. websites. Cache as parquet.
3. Calculate actual total return with DRIP for all three instruments over full history. Compare to published numbers.
4. Calculate blended total return for Mode A (80/10/10), Mode B (50/25/25), Mode C (STRC-only).

**KILL GATE (Day 1):** If total return with DRIP for NVDY or AMZY is actually negative (headline yield is illusory despite DRIP), stop. The thesis requires positive total return.

**Day 2: Allocation model + withdrawal simulation**

1. Build `strategies/yield_flywheel.py` with static allocation weights and optional trend filter overlay.
2. Build withdrawal simulation: at $10K deployed, target $X/month withdrawn, track principal trajectory across all three modes.
3. Compare Mode A vs Mode B vs Mode C on withdrawal coverage ratio.
4. Calculate correlation to A1+A2 equity core returns.

**KILL GATE (Day 2):** If total return with DRIP minus target withdrawal rate is negative under Mode A (the conservative case), the math doesn't work at any scale. Document and move on.

**Day 3: Shadow ledger + paper trade setup (only if Day 2 passes)**

1. Build shadow ledger module for virtual dividend tracking on Alpaca paper positions.
2. Build account adapter `_build_account_5()`.
3. Initialize $10K virtual balance in Account 5.
4. Place initial Mode A allocation on Alpaca paper (verify STRC is tradeable on Alpaca — if not, IBKR paper needed, separate infrastructure project).
5. Set up weekly dividend crediting and DRIP logic.

**Day 4 onward: Paper trade monitoring (6-month minimum)**

- Weekly: record distributions, DRIP reinvestment, portfolio NAV, withdrawal coverage ratio.
- Monthly: compare actual distributions to expected, check for yield compression.
- Quarterly: full review against kill conditions.
- Track the flywheel logic: is sweeping YieldMax dividends into STRC actually better than simple DRIP?

---

## 7. Gotchas (must-read before implementation)

**1. STRC is not a bond.** The original Gemini capsule called it a "Bedrock" and framed it as stable income. It is unsecured perpetual preferred equity with no maturity date, no covenant protection, no seniority in bankruptcy. "Variable rate" means the issuer CAN adjust dividends but has no contractual OBLIGATION to maintain any specific yield. Compare to an actual bond: a bond has a maturity date, a fixed coupon, and bankruptcy priority. STRC has none of these.

**2. Headline yields are not total returns.** NVDY's ~43% "yield" and AMZY's ~50% "yield" include massive ROC (92% and 97.72% respectively in recent weeks). The ETF is returning your capital. AMZY's price-only CAGR is -4%/yr. The only meaningful number is total return with DRIP, which factors in both distributions received and NAV erosion. Every calculation in this doc must use total return with DRIP.

**3. Correlated tail risk.** STRC (BTC-derivative), NVDY (NVDA-derivative), AMZY (AMZN-derivative) are all long tech/crypto risk appetite. In a 2022-style coordinated selloff (SPY -25%, BTC -65%, NVDA -66%), all three would underperform simultaneously. The "diversification" across three instruments does not provide crisis protection.

**4. ROC tax treatment requires CPA verification.** Current distributions are classified as ROC, which reduces cost basis rather than creating taxable income. This is favorable for the bridge years. But classification can change. If reclassified as ordinary income, after-tax yield drops substantially. George's CPA (already engaged per FIREMaster notes) should verify before real capital is deployed.

**5. Covered-call structure caps upside systematically.** In a strong NVDA bull market, NVDY dramatically underperforms NVDA on total return (~26% capture ratio since inception). This is not free yield — it's a trade: income now in exchange for growth later. In the bridge context this trade may be acceptable (income is the goal), but it means the strategy cannot benefit from a tech supercycle.

**6. 10 months of STRC history tells you nothing about credit events.** STRC launched during a BTC bull market. Zero data exists on STRC behavior during a prolonged (6+ month) BTC bear. The Nov 2025 dip ($88, recovered in 20 days) and Feb 2026 flash crash were brief V-shaped recoveries. A 2022-style 18-month grind would be a fundamentally different test that this data cannot inform.

**7. EGGQ is not a benchmark.** 5 months old, $78M AUM, insufficient for any comparison. If benchmarking is needed, compare to: (a) STRC-only (the null hypothesis), (b) SCHD (established high-dividend equity ETF), (c) 60/40 SPY/AGG as the baseline allocation.

**8. The flywheel sweep logic operates outside the standard `generate_signals` framework.** FIRE's backtest infrastructure assumes strategies produce daily weight signals. A dividend sweep (collect NVDY/AMZY distributions → buy STRC) is an allocation-layer operation that requires the shadow ledger. Don't try to encode it in `generate_signals()` — it needs its own module operating on the virtual balance.

**9. The Gemini doc's "Calmar > 3.0" framing was wrong.** Targeting Calmar > 3.0 using trend filters to "cap the denominator" is Mode 1 thinking applied to a non-Mode-1 strategy. A yield strategy's success metric is withdrawal coverage ratio and principal preservation. Trend filters may reduce drawdowns (worth tracking), but the strategy should be evaluated on income metrics first, not risk-adjusted return metrics.

**10. STRC may require IBKR for live trading.** STRC is a preferred stock, not a common equity or ETF. Alpaca may or may not support it (needs verification on Day 3). NVDY/AMZY are standard ETFs and should be available. If STRC needs IBKR, that's a separate broker integration — significant infrastructure work beyond the scope of the paper-trade.

---

## 8. Open Questions the Paper-Trade Needs to Answer

1. **Does yfinance adjusted close actually capture NVDY/AMZY weekly distributions?** If not, every total-return calculation from yfinance data is wrong. Must be verified Day 1 by comparing yfinance total return to published figures from YieldMax.

2. **What is the actual total return with DRIP for each instrument over its full history?** Calculated from first principles (price data + distribution data), not from marketing materials.

3. **Is the flywheel (sweep YieldMax dividends to STRC) actually superior to simple DRIP?** If NVDY total return with DRIP > STRC total return, reinvesting NVDY distributions back into NVDY compounds faster. The flywheel only wins if STRC is more capital-efficient per unit of risk. Test both in the shadow ledger.

4. **Does the trend filter overlay add value on a 2-3 year horizon?** With only 3 years of NVDY data, the SPY filter may activate 0-2 times. Too few events for statistical significance, but worth tracking directionally.

5. **What does correlation to the A1+A2 equity core look like?** If the yield strategy is highly correlated to the existing book (likely: all are long risk-on assets), it adds income but no diversification — and drawdowns compound in stress.

6. **Can Alpaca paper-trade STRC?** If not, the paper-trade setup requires IBKR paper trading, which is a separate infrastructure project that changes the Day 3 build plan.

7. **What does the withdrawal coverage ratio look like under different deployment sizes?** $10K, $50K, $100K, $500K — at what scale does the yield actually fund the target monthly withdrawal with the 1.5x buffer?

8. **How do NVDY/AMZY distributions behave during drawdowns?** Do they maintain distribution levels when NAV is falling, or do distributions compress with price? This is load-bearing for the income-floor thesis — if distributions drop when you need income most, the strategy fails precisely when it matters.

---

## Relationship to Other Research

**vs. Rate-Vol (RATE_VOL_SCOPE.md):** Different category entirely. Rate-vol is a capital-appreciation play via factor timing on Treasuries (same family as A1/A2/A4). This is income generation via carry/yield. They don't compete for the same slot. If anything, they're complementary — rate-vol fires during policy shocks that might stress the yield portfolio.

**vs. BOOK_SHAPE.md gaps:** Partially addresses Gap 2 (non-price edge) — the variable-rate mechanism, dividend calendar, and ROC tracking are non-price information. Does NOT address Gap 1 (crisis alpha) or Gap 3 (regime adaptivity). In a crisis, this portfolio is fragile (all three instruments are long risk-on).

**vs. Mode 1 validation framework:** Explicitly uses different success criteria. Does not enter the CAGR-first scorecard pipeline. Paper-trade evaluation per the kill conditions and success criteria table in Section 5 above.

**Bridge-plan context:** Full life-picture analysis (funding sources, SEPP 72(t) deployment, property sale proceeds) is in FIREMaster — see `STRATEGY_CAPSULE.md` and `BRIDGE_STRATEGY_REVIEW.md`. This doc scopes the FIRE-side implementation only.
