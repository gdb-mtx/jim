# Rate-Vol Account — Scoping Doc (2026-04-18)

**Goal:** Build a new Account 5 candidate that exploits rate volatility dislocations using the Nagel liquidity-provision mechanism. Target: OOS CAGR + Calmar that would materially improve the combined portfolio beyond the current 3-account + crypto blend.

**Why this asset class:** high natural vol, no "going to zero" terminal risk, genuinely less crowded than equity vol, and MOVE is at multi-year highs during the current Fed policy regime. Treasury ETFs have clear mean-reversion on the 5-10 day horizon when rate vol is elevated, especially during Fed pivots and policy surprises.

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
- TLT drop threshold: -2%, -3%, -4%, -5%
- MOVE threshold: 100, 120, 140, 160
- Hold period: 5, 10, 15 days
- MOVE exit: max or normalize under 80

**Expected Sharpe band:** 1.2-2.0 full-cycle (bonds have had big regime shifts; 2022-23 was extraordinary for this mechanism, 2010-2020 was muted).

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

## Open questions to resolve during implementation

1. **Does the Nagel mechanism really work on bonds?** It works on equities because of retail forced sellers during margin calls. Bond market structure is different — most flow is institutional. But 2022's Treasury meltdown showed forced unwinds do happen (basis trades, foreign reserve managers, leveraged relative-value funds). Need to check whether the reversal premium is present or whether bonds just trend.

2. **Is 2022-23 a one-off or a durable regime signal?** If MOVE > 120 only happened in 2022-23, the strategy has near-zero activity in other regimes. Walk-forward across 2010-2026 should reveal this. If the strategy only works in 2022-23, it's essentially a bet on a specific Fed cycle repeating — not good.

3. **What's the right signal latency?** MOVE data is delayed 1 day on most feeds. Make sure the backtest uses MOVE lagged by 1 day for honest signal timing.
