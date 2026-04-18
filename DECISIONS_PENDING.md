# Pending Decisions — Handoff (2026-04-18 → next session)

**Status:** Two significant findings from the 2026-04-18 session that change how the system should be configured. George wants to reconsider both with a **clean session** before committing to either direction. Do not advocate — present the evidence, challenge the reasoning, and let the user decide.

**Context for a fresh session:** Read `CLAUDE.md` for current state, then this doc. The two decisions are independent; can be resolved in either order.

---

## Decision 1 — What to do about Account 3 (Reversal + Momentum)

### The finding

Pulled live snapshots for all 4 accounts (29 days, 2026-03-10 → 2026-04-18) and computed pairwise correlations. Compared to backtest at full-sample (1470 days) and OOS-only (825 days) periods.

**A1-A3 daily-return correlation:**
- Live 29-day: **0.842**
- OOS backtest (2023+): **0.876**
- Full-sample backtest (2020-2026): **0.884**

The backtest has always predicted A1-A3 correlation near 0.88. The prior CLAUDE.md claim of "0.56-0.66 equity pairs" was wrong. **There was no "divergence" from backtest — the diversification thesis was always optimistic.**

Other pairs (OOS backtest):
- A1-A2: 0.38 (genuinely diversified)
- A2-A3: 0.54 (moderate)
- A4 vs equity: 0.10-0.19 (genuinely diversified)

### Why A1-A3 are so correlated

A3 = 60% ShortTermReversal + 40% StockMomentum, both on the S&P 500 universe. The 40% StockMomentum leg is literally the same strategy as A1. Between weekly reversal rebalances, A3's daily variance is dominated by its SM leg, which tracks A1 perfectly.

### Portfolio implications (from live data + OOS backtest)

Tested alternative blend weights on OOS returns (2023-01-03 → 2026-04-17):

| Blend | CAGR | MaxDD | Calmar |
|---|---|---|---|
| 1/3 A1 + 1/3 A2 + 1/3 A3 (current) | +18.0% | -8.5% | **2.12** |
| 50% A1 + 50% A2 (drop A3) | +19.7% | -9.3% | 2.11 |
| 40% A1 + 40% A2 + 20% A3 | +18.7% | -8.8% | 2.12 |
| 50% A1 + 50% A3 | +17.8% | -8.7% | 2.04 |
| 50% A2 + 50% A3 | +16.3% | -8.5% | 1.92 |
| 100% A1 | +21.0% | -11.1% | 1.89 |
| 100% A2 | +17.9% | -11.6% | 1.55 |
| 100% A3 | +14.5% | -7.2% | 2.03 |

**A3 is costing ~1.7% CAGR for zero Calmar benefit.** The "diversification" attributed to A3 in the 3-account core was mostly A2 doing the work.

### A3's own grade under the CAGR-first framework

MARGINAL. CAGR 14.5% is 0.5pp below the 15% PASS floor. Calmar 2.03 is actually best-in-system standalone (shallowest drawdown). But standalone Calmar doesn't matter if the account isn't earning its portfolio weight.

### The three options

**Option A: Retire A3.** Move its $100K to expanding A2, expanding A4, or holding as cash for the future Account 5 (rate vol). Simplest. Loses nothing in Calmar, gains in CAGR.

**Option B: Redesign A3 as pure Short-Term Reversal (0% SM blend).** The 60/40 split was chosen to smooth pure-reversal's volatility — but that choice killed the diversification by importing A1's signal. Pure reversal would have lower standalone Sharpe but lower correlation to A1 (probably 0.3-0.5 range). Backtest this before deciding.

**Option C: Reduce A3 weight to 20%.** 40/40/20 blend has Calmar 2.12 (same as 1/3 each) with CAGR 18.7%. Minor improvement.

### Questions a fresh session should ask

- Is the backtest correlation of 0.88 being computed correctly? Re-verify by running the correlation against the strategies from their raw returns, not from `run_portfolio` output.
- Does the live correlation hold up as the sample grows? 29 days is thin. At what sample size would we be confident this isn't a short-window artifact? (Answer: the backtest 3-year OOS shows the same number, so it's not a short-window artifact — but reconfirm.)
- If we do Option B (redesign A3), what does pure ShortTermReversal look like standalone? Backtest it. What's its actual correlation to A1 with 0% SM blend?
- Is there a better satellite candidate for that $100K than any A3 variant? Rate vol (Account 5 in `RATE_VOL_SCOPE.md`) could absorb this capital.

### What the current code does

- CLAUDE.md has the corrected correlation numbers (commit `cbd7422`).
- No code change to A3 — still runs 60/40 STR/SM blend at 1/3 weight.
- Decision needs to happen before any reweighting is executed.

---

## Decision 2 — Keep or revert SMA-125/top2 for Account 4

### The change

Built `scripts/crypto_robust_opt.py` that scores crypto configurations by `min(Calmar_half_A, Calmar_half_B)` — explicitly optimizing for regime robustness rather than full-sample peak. Expanded the filter-period grid from the original `{150, 200}` to `{100, 125, 150, 175, 200}`.

**Winner:** SMA-125/lb21/top2. Rank 1 by min-Calmar.

### The numbers

**Standalone OOS (2023-01 → 2026-03, crypto calendar):**

| Metric | Old (200d/top3) | **New (125d/top2)** | Δ |
|---|---|---|---|
| CAGR | +32.7% | **+47.1%** | +14.4pp |
| MaxDD | -23.5% | -11.4% | +12.1pp (half) |
| Calmar | 1.39 | **4.15** | +2.76 |
| UPI | 4.27 | 9.02 | +4.75 |
| Sortino | 1.62 | 2.25 | +0.63 |
| Bootstrap CAGR p5 | +15.9% | +24.2% | +8.3pp |
| Test 3 half-A Calmar | 3.90 | 2.89 | -1.01 |
| Test 3 half-B Calmar | 1.02 | **3.10** | +2.08 |
| OOS/IS CAGR ratio | 97% | 89% | -8pp |

**Portfolio impact** (combined book with crypto at 25% weight):
- Old: CAGR +21.9%, MaxDD -7.4%, Calmar 2.98
- New: **CAGR +25.0%, MaxDD -7.0%, Calmar 3.57**

### The code change

Commit `1baad0d`. Changed `strategies/crypto_momentum.py` defaults:
```python
# Before
lookback_days=21, top_n=3, btc_ma_period=200
# After
lookback_days=21, top_n=2, btc_ma_period=125
```

Also updated `scripts/filter_check.py` (monitor MA 200 → 125), `strategies/portfolio.py` `compute_btc_trend_filter` (default 200 → 125), `dashboard/src/types.ts` (`btc_ma200` → `btc_ma125`). Expanded Test 3 sweep grid in `scripts/run_validation.py` to include the 25-unit steps.

To revert: reset the four default values back to `top_n=3, btc_ma_period=200`. The crypto_robust_opt script stays regardless; it's diagnostic, not load-bearing.

### The core argument FOR the change

1. The old config (200/top3) was explicitly labeled "conservative default — the pre-autoresearch null values" in the docstring. It was chosen to avoid autoresearch overfitting, not because it was optimal.
2. The new config is selected by an objective that's aligned with the project thesis (CAGR-first, regime-robust). Not a full-sample Sharpe maximization.
3. SMA-{125, 150, 175}/top2 all rank in the top 3 by min-Calmar (2.89, 2.19, 2.03) — a plateau on the parameter surface, not a single-point lucky hit.
4. The OOS numbers are transformatively better, not marginally better. CAGR +14pp, MaxDD halved, Calmar 3x.

### The core argument AGAINST the change

1. **The grid expansion itself is a form of search-space fitting.** We didn't have SMA-125 in the original grid. When the CAGR-first framework needed a better answer, we expanded the grid and found a better answer. There's a circularity to that — "we couldn't find a good config, so we looked harder, and we found one." A truly out-of-sample test would hold the grid fixed.
2. **OOS/IS CAGR ratio dropped from 97% → 89%.** Still passes the 70% floor, but the old config had more consistency between train and test. The new config's train CAGR is +53% vs test +47% — more of a drop-off.
3. **top_n=2 is more concentrated than top_n=3.** Higher single-coin idiosyncratic risk. If a top-2 coin suffers a protocol failure (exchange hack, depeg, regulatory shutdown), losses are larger than with top-3 diversification.
4. **Half-A Calmar dropped from 3.90 to 2.89.** We traded some upside in the bull regime for more consistency in the choppy regime. If the next regime looks more like 2020-22 than 2023-26, the old config would have been better.
5. **This is the second time we've changed crypto defaults in a week.** First was 150/top2 → 200/top3 (reverting tuning). Now 200/top3 → 125/top2 (new tuning). Paper-trading with frequent parameter changes is a red flag — what are we actually validating?

### The sanity-check test

Candidate argument against (1): the robust-opt is selecting for regime robustness, not optimum. Even if SMA-125 is specific to this grid, SMA-{100, 125, 150} all score well. The grid expansion was motivated by the finding that SMA-100 was half-B's top and SMA-150+ was half-A's top — 125 was added as the obvious midpoint to test.

A fresh session should:
- Look at the `data/mode2/crypto_robust_opt.parquet` file and examine the full ranking, not just rank 1. Does the parameter surface look smooth or spiky?
- Compare SMA-125/top2 against SMA-150/top2 (rank 2). Is the gap between rank 1 and rank 2 meaningful, or within the noise of a 2×3-year sample?
- Test SMA-125/top3 and SMA-150/top3 — is top_n=2 actually better than top_n=3 when you control for filter period?
- Consider: what's the Bayesian prior on "the right filter period for a crypto momentum strategy"? Industry convention clusters around 150-200. 125 is unusual. Is there a mechanism reason 125 should work, or is it just a local peak in a noisy grid?

### Questions a fresh session should ask

- Is the grid-expansion-driven discovery of SMA-125 real, or an artifact? Would we find an equally-good config by expanding in some other dimension (lookback period, vol target)?
- If we held this config for 24 months forward and it underperformed the 200/top3 config, would we know whether to revert? What would the signal be?
- Should Account 4's allocation weight be explicitly decided now? The 25% number has been a placeholder — with Calmar 4.15 standalone, the portfolio math suggests 30-40% might be justified. But concentration risk in one strategy grows with weight.
- Is the right response to the robust-opt result: (a) ship SMA-125/top2, (b) stick with SMA-200/top3 and treat robust-opt as diagnostic only, (c) ship SMA-150/top2 as a compromise that matches industry convention but still benefits from the robust-opt insight?

### What the current code does

SMA-125/top2 is the production config. Gate status: PASS. If we don't actively revert, this is what trades when A4 next rebalances (which requires BTC > 125d SMA — currently BTC is below, so A4 is in cash anyway and no trades will happen immediately).

**This gives us time to decide.** The gate allows paper trading, but no real money flows until BTC flips bullish on the 125d filter. Could reasonably defer the decision weeks without operational risk.

---

## Decision-making rules the fresh session should apply

1. **Don't re-derive what's already measured.** The numbers above are the result of running `crypto_robust_opt.py`, the full validation runner, and direct correlation analysis. Accept them as facts and focus on interpretation.
2. **Don't advocate. Present the case cleanly and let George decide.**
3. **If either decision reverses today's change**, be clear about why — specifically which argument from the "against" section won.
4. **If either decision keeps today's change**, articulate what the user will look at in 3 months to re-check.
5. **Pre-commit to thresholds before running any new tests.** If a fresh session wants to test "what if we add SMA-110 to the grid", pre-commit to whether that result should change the decision before seeing the number.

---

## Reference commits

- `cbd7422` — Correlation finding + CLAUDE.md correction (Decision 1)
- `1baad0d` — Crypto robust-opt + SMA-125/top2 promotion (Decision 2)
- `c278896` — Scorecard metrics module
- `d23bd80` — CAGR-first validation runner

## Reference files to read

- `CLAUDE.md` — current system state (post-changes)
- `VALIDATION_PLAN.md` — v2 framework and thresholds
- `scripts/crypto_robust_opt.py` — the search script
- `data/mode2/crypto_robust_opt.parquet` — full 144-config ranking
- `data/validation_reports/account_4_20260418_115408.md` — new A4 scorecard
- `RATE_VOL_SCOPE.md` — Account 5 candidate (independent of these decisions)
