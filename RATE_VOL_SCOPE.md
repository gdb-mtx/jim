# Rate-Vol Account — Scoping Doc (2026-04-18)

**Goal:** Build a new Account 5 candidate that exploits rate volatility dislocations using the Nagel liquidity-provision mechanism. Target: OOS CAGR + Calmar that would materially improve the combined portfolio beyond the current 3-account + crypto blend.

**Why this asset class:** high natural vol, no "going to zero" terminal risk, genuinely less crowded than equity vol. Treasury ETFs have clear mean-reversion on the 5-10 day horizon when rate vol is elevated, especially during Fed pivots and policy surprises.

**Current regime caveat (2026-04-18):** MOVE closed at 65.70 — near multi-year *lows*, not highs. The 2022-23 hiking-cycle spike (MOVE > 150 sustained) is behind us; the last 6 months have been the quietest rate environment since 2021. **A reversal strategy conditional on elevated MOVE will sit in cash most of the time in the current regime.** That's fine for backtest (2010-2026 covers enough regimes) but materially affects when live signal could be measured — probably only on the next Fed shock or policy-uncertainty spike. Don't be surprised by zero activity in the first 3-6 months of live paper.

---

## Data (all available via yfinance)

- **MOVE index** (`^MOVE`): 2010-2026, ~4014 days. Daily close, free. The "VIX of bonds."
- **TLT** (20+ year Treasury ETF): 2010-2026, ~4097 days. Primary trading vehicle.
- **IEF** (7-10 year): secondary vehicle if we want multi-duration dispersion
- **SHY** (1-3 year): cash proxy / cross-sectional short side
- **TBT** (2× inverse 20yr): avoid — leveraged ETF decay; use cash exit instead

**Note:** MOVE is not currently cached. Add to `data/sp500.py` or new `data/rates.py` helper alongside the VIX cache pattern.

---

## Three candidate designs, ranked by risk/reward

### Candidate A — MOVE-conditional TLT short-term reversal

**Thesis:** Same mechanism as Account 3 reversal on equities, applied to TLT. When MOVE spikes (policy uncertainty or pivot), TLT overshoots on both sides of the mean. Buy dips aggressively when MOVE > threshold; otherwise stay flat.

**Signal:** 5-day TLT return < -X% AND MOVE > Y → long TLT, hold 5-10 days or until MOVE normalizes.

**Parameter axes for testing:**
- TLT lookback: 3, 5, 7, 10 days
- TLT drop threshold: **z-score of trailing-60d-returns, not absolute %** (see gotcha #2 below)
  - Test z ≤ -1.0, -1.5, -2.0
- MOVE threshold: **percentile of trailing-252d MOVE, not absolute level** (see gotcha #1)
  - Test 70th, 80th, 90th percentile
- Hold period: 5, 10, 15 days
- MOVE exit: price recovers to prior peak OR MOVE falls below 50th percentile OR max hold period reached

**Expected Calmar band:** 0.8-1.5 full-cycle. Lower than Account 3's 2.03 because this is single-instrument timing (no cross-sectional dispersion to exploit — just "when to be long TLT"). Don't anchor expectations on the Account 3 reversal analogy's Calmar; the mechanism is the same but the vehicle is narrower.

**Why this first:** Cleanest direct analog of a working strategy we already validate cleanly (Account 3). Replaces the equity universe with TLT, keeps the same VIX-method mechanism intact. If the Nagel mechanism works on equities, the same arithmetic should work on bonds — the question is magnitude.

**Risk:** The mechanism might be too dependent on the 2022-23 hiking cycle and fail in a Fed-on-hold regime. Walk-forward and regime testing will reveal this.

### Candidate B — MOVE-conditional TLT trend-follow (Faber-style)

**Thesis:** TLT trends well in sustained policy regimes. Use 50/200 SMA crossover as the directional signal, and MOVE as an *amplifier*: size up when vol is elevated (more room for the trend to run), size down when calm (mean-reverting regime).

**Signal:** Long TLT when price > 200d MA. Size: proportional to MOVE percentile (high MOVE = 1.5x exposure, calm = 0.5x).

**Expected Sharpe band:** 0.8-1.3. Bond trends are cleaner than stock trends but lower amplitude; adding MOVE-scaling gives a small lift.

**Why not first:** Simpler but lower expected Sharpe. Also more correlated to Account 2's Multi-Asset Trend (which already holds TLT) — would dilute rather than diversify.

### Candidate C — Cross-curve rate reversal (SHY/IEF/TLT)

**Thesis:** When rate vol spikes, the yield curve develops short-term dislocations between durations. Rank SHY, IEF, TLT by 5-day return, buy worst performer, short best — pure cross-sectional mean reversion on the curve.

**Signal:** Daily rank by trailing return, long-short with MOVE filter.

**Expected Sharpe:** Unknown — no direct academic reference. Could be 1.5-2.5 if it works, or complete noise.

**Why not first:** Requires shorting or reverse ETFs. Against our "no shorting" rule. Could be rebuilt as long-only (just buy the worst performer, skip the short leg), but loses half the edge.

---

## Concrete first build (Candidate A, 3-4 days total)

### Day 1: data pipeline + baseline
1. Add `download_move_index()` to `data/sp500.py` or new `data/rates.py` with parquet caching matching the VIX pattern (staleness check, yfinance download, cache hit).
2. Add `RateVolReversal` strategy class to `strategies/mean_reversion.py` or new file `strategies/rate_vol.py`. Follow `ShortTermReversal`'s structure exactly. Takes TLT price series + MOVE series.
3. Backtest with initial hardcoded params (5d lookback, -3% threshold, MOVE > 120, 5d hold). Generate returns 2010-2026.

### Day 2: parameter sweep + validation
1. Build account adapter in `backtesting/account_adapters.py` (`_build_account_5`).
2. Add `PORTFOLIOS["rate_vol"]` to `strategies/portfolio.py` with the weight/filter config.
3. Run full `scripts/run_validation.py --account 5`. Check scorecard.
4. If CAGR < 10%, stop here — the factor isn't there. Document and move on.

### Day 3: robust optimization (only if day 2 passes)
1. Build `scripts/rate_vol_robust_opt.py` following the crypto version's pattern: sweep parameter grid, rank by `min(Calmar_half_A, Calmar_half_B)`, promote the robust winner.
2. Validation gate applies: this is Account 5, gets its own validation record.

### Day 4: portfolio integration
1. If passes PASS gates: update `CLAUDE.md` with a 5-account section.
2. Measure marginal contribution to combined portfolio at 10/20/25/30% weights.
3. Decide target allocation (unlikely to be 25% — rate vol is a narrower trade than crypto momentum, probably 10-15%).

---

## Pre-committed pass/fail thresholds (same as existing framework)

- **Pass:** OOS CAGR ≥ 15% AND OOS MaxDD ≥ -40% AND OOS Calmar ≥ 1.0 AND OOS/IS CAGR ratio ≥ 70%
- **Marginal:** OOS CAGR ≥ 10% AND OOS Calmar ≥ 0.5
- **Fail:** below Marginal
- **Bonus criterion for satellite consideration:** correlation to 3-account core ≤ 0.4. Rate vol should have near-zero correlation to equity factors — if it comes in above 0.4, the diversification thesis fails regardless of standalone numbers.

---

## What would make this extraordinary

The combined portfolio today with Account 4 at 25% weight hits:
**CAGR +25.0%, MaxDD -7.0%, Calmar 3.57.**

Adding Account 5 at 15% weight (scaling back equity weights proportionally), if Account 5 delivers OOS CAGR 18% / Calmar 1.8 with 0.1 correlation to the core, the combined would lift to roughly:
- CAGR +26-27%
- MaxDD -6.5%
- **Calmar ~4.0**

If Account 5 delivers 25% CAGR (optimistic case): combined CAGR 28%+, Calmar 4.5+.

That's not "2.5 Sharpe unicorn" territory, but it's a genuinely diversified 4-stream book compounding at 28%+/year with shallow drawdowns. That's the bridge-plan math working.

---

## Strategy-specific gotchas (must-read before implementation)

Generic "follow the Account 3 pattern" gets ~80% of this right. These are the ~20% where rate-vol diverges and where a naive port of the equity reversal template will produce misleading numbers.

**1. MOVE threshold must be percentile-based, not absolute.**
MOVE is a point-in-time index with regime-dependent range. 2015-2020: MOVE typically 50-90. 2022-23: MOVE 110-180. 2026-04: MOVE back at 65. An absolute threshold like "MOVE > 120" activates in one regime and is silent in another — the strategy is effectively only trained on 2022-23 and that's a confounded backtest. Use a rolling percentile threshold (e.g., MOVE > 80th percentile of trailing 252d).

**2. TLT return threshold must be z-scored, not absolute.**
Same issue. TLT annualized vol was ~13% in 2015-2020 and ~22% in 2022-23. A -3% daily drop was a tail event in the first regime and routine in the second. Using absolute `-3%` means the strategy mostly triggers in high-vol regimes only. Use z-score of trailing-60d returns instead.

**3. MOVE must be lagged 1 day in the backtest.**
MOVE is published end-of-day. At time t's open, you only have MOVE.shift(1). Backtest must use `move_aligned = move.shift(1).reindex(tlt.index).ffill()` before filtering. Easy to get this wrong by using same-day MOVE — inflates backtest Sharpe by ~0.2-0.4.

**4. Verify TLT is distribution-adjusted.**
TLT pays ~4%/yr in distributions. yfinance with `auto_adjust=True` should handle this but verify — if distributions aren't adjusted in, the strategy's TLT returns will look 4%/yr worse than reality.

**5. Single-instrument, not cross-sectional.**
Account 3 reversal ranks 450 stocks and holds the bottom decile — variance of the strategy is low because it's a diversified basket. Rate-vol is just timed long-TLT. Each trade is idiosyncratic to a single event. Expected Calmar band (0.8-1.5) reflects this; don't anchor on Account 3's 2.03.

**6. Diversification thesis is correlation-of-returns, not correlation-of-vols.**
MOVE and VIX both spike in crises, so if we measured "correlation of MOVE to VIX" it would be high, suggesting bond and equity vol are correlated. But what matters for portfolio fit is correlation of TLT-strategy returns to equity-strategy returns — and those can be near-zero even when the underlying vol regimes co-move. Verify directly against A1/A2/A3 return streams after day-1 backtest.

**7. Bond market structure differs from equity reversal mechanism.**
Nagel's liquidity-provision story is retail forced sellers hitting margin. Bond market is ~95% institutional. The mechanism analog: basis-trade unwinds, foreign reserve manager rebalances, ETF outflow waterfalls. All exist but fire less often and on different triggers. Expect fewer trades per year than Account 3 (maybe 5-15 vs Account 3's 40+), and a more concentrated return distribution.

**8. LQD/HYG as fallback universe.**
If TLT-only is too narrow (too few trades, too much idiosyncratic single-series noise), LQD (investment-grade corporate) and HYG (high-yield) have rate vol + credit vol, more trades, and a related but distinct premium. Not to test first — keep scope focused — but worth knowing exists if the TLT-only version doesn't clear gates.

---

## Open questions that remain (require the backtest to answer)

1. **Does the Nagel mechanism really work on bonds?** 2022 Treasury meltdown showed forced unwinds happen (basis trades, FX reserve managers, levered RV funds). But walk-forward across 2010-2026 is the honest test — if the reversal premium is only visible in 2022-23, the strategy is really a bet on a specific Fed cycle repeating.

2. **Is 2022-23 a one-off or a durable regime signal?** Related to #1. Specifically: with percentile-based MOVE thresholds (gotcha #1), does the strategy still fire meaningfully in 2010-2020? If it fires 2× more in 2022-23 than other regimes but *still profitable* in calmer regimes, that's fine. If it's profitable only in 2022-23, that's a kill.

3. **What's the activity rate across regimes?** Count the number of trigger days per year across 2010-2026. If the strategy trades <5 times/year in "calm" regimes, it's essentially unobservable live — can't distinguish luck from skill on a 12-24 month live record.
