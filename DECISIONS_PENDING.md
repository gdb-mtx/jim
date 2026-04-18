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

## Decision 2 — Account 4 portfolio weight (25% vs 40%)

### Framing (user directive 2026-04-18)

> "For me the question about account4 was more about 25% vs. 40% instead of questioning the results. We will rereview the results but they were so positive that a 25% vs. 40% of portfolio makes more sense than reverting what wasn't as good unless we find a mistake."

So the primary decision is **weight allocation**, not keep/revert. The default assumption is that SMA-125/top2 stays in production unless the validation pass turns up a concrete error in the methodology or math. **The real question: how much of the combined book should sit in Account 4?**

### What the robust-opt change actually did (brief recap)

Built `scripts/crypto_robust_opt.py` that scores crypto configs by `min(Calmar_half_A, Calmar_half_B)` — optimizing for regime robustness rather than full-sample Sharpe peak. Expanded filter-period grid from `{150, 200}` to `{100, 125, 150, 175, 200}`. Winner SMA-125/top2 (rank 1 by min-Calmar 2.89) was promoted to production.

**Standalone OOS scorecard (2023-01 → 2026-03):**

| Metric | Old (200d/top3) | **New (125d/top2)** |
|---|---|---|
| CAGR | +32.7% | **+47.1%** |
| MaxDD | -23.5% | **-11.4%** |
| Calmar | 1.39 | **4.15** |
| UPI | 4.27 | 9.02 |
| Sortino | 1.62 | 2.25 |
| Bootstrap CAGR p5 | +15.9% | +24.2% |
| OOS/IS CAGR ratio | 97% | 89% |

Test 3 production Calmar: 2.89 (half A, 2020-22) / 3.10 (half B, 2023-26) — regime-robust. All validation gates pass.

**The validation pass (steps 1-5 below) should confirm this is real. If no error is found, the focus shifts entirely to the weight question.**

### Where "25%" came from and why it's a placeholder

25% was inherited from the original 4-account architecture: "four accounts at $100K each, one of them is crypto." That's a capital-split convention, not a portfolio-theoretic optimum. The validation runner's `portfolio_fit` test defaults to 25% for the same reason — matching the capital split.

None of that is a reason 25% is actually the right weight given the strategy's current OOS scorecard. With Account 4 OOS Calmar 4.15 and ~0.16 correlation to the core, the portfolio math favors a higher weight.

### The numbers across weights

Combined portfolio OOS (2023-01-03 → 2026-03-10, core is 3-account equal-weight blend, crypto is SMA-125/top2):

| Crypto weight | Combined CAGR | Combined MaxDD | Combined Calmar |
|---|---|---|---|
| 10% | +20.8% | -7.3% | 2.84 |
| 15% | +22.2% | -7.2% | 3.08 |
| 20% | +23.6% | -7.1% | 3.32 |
| **25%** | **+25.0%** | **-7.0%** | **3.57** |
| 30% | +26.4% | -6.9% | 3.83 |
| 35% | +27.8% | -7.0% | 3.98 |
| **40%** | **+29.2%** | **-7.1%** | **4.10** |
| 45% | +30.6% | -7.3% | 4.22 |
| 50% | +31.9% | -7.4% | 4.34 |

Observations:
- **MaxDD is essentially flat across weights** — the crypto drawdowns land on different calendar days than the equity drawdowns most of the time, so increasing crypto weight doesn't materially worsen combined peak-to-trough pain in this sample.
- **CAGR scales roughly linearly.** +1.4pp CAGR per 5% crypto weight.
- **Calmar peaks around 45-50%** but continues climbing through 40%.
- **25% → 40% adds +4.2pp CAGR (+$2.1K/yr on $50K) with effectively identical MaxDD.**

### The core argument FOR 40%

1. **The OOS data says so.** Calmar peaks higher, CAGR scales up, MaxDD doesn't worsen. On the measurable metrics, 40% is strictly dominant over 25% on this sample.
2. **Account 4 is the highest-CAGR strategy in the system by 2×.** 47% vs 21% for the best equity account. Under-weighting the best strategy is a behavioral bias (home-bias to equities), not a portfolio-theoretic conclusion.
3. **Bridge-plan math.** The user's target is $50K → whatever compounding at 28%/yr over 3-5 years vs 25%/yr matters materially. 29.2% CAGR over 5 years = $50K → $182K. 25% CAGR = $50K → $152K. Difference is $30K, not rounding.
4. **The correlation is genuinely low** (0.16-0.19 to the core). Not a disguised equity bet.

### The core argument FOR 25% (status quo)

1. **Historical MaxDD on one sample is not the same as forward MaxDD.** The shallow combined MaxDD is partly luck of calendar alignment between equity and crypto drawdowns. A future episode where both peak together (e.g., synchronized liquidity crisis) would be worse at 40% than 25%.
2. **Single-strategy concentration risk.** At 40% weight, one strategy can take down 40% of the portfolio in a true tail event. Protocol failure, coin-specific catastrophe, or a sustained crypto winter the BTC filter fails to catch fast enough — all are plausible scenarios. At 25%, same event loses 25%. At 40%, loses 40%. Risk is proportional to weight, reward is also proportional to weight — so in pure expected-value terms this is neutral. But the asymmetry of "survives to compound another day" matters.
3. **We have 29 days of live data, not 3 years.** The OOS backtest is solid, but the live record for SMA-125/top2 is literally zero days (BTC has been below its 125d MA the entire 29-day live window, so A4 has been in cash). Sizing up before we have any live evidence is aggressive.
4. **Crypto's historical correlation to equities has been low but not stable.** In 2022 Fed-driven bear markets, BTC-SPY correlation spiked to 0.5+. If we enter a period where that regime returns, the 0.16 correlation assumption understates correlated drawdown risk.
5. **This is paper trading.** There's no reason to swing to 40% now. Ship 25%, see how SMA-125/top2 performs live for 6-12 months, reconsider up-weighting once the live record agrees with the backtest.

### The compromise: 30% or 35%

Not explored in detail here but reasonable middle positions:
- 30%: CAGR +26.4%, Calmar 3.83 — captures most of the CAGR lift, stays below the single-strategy "majority of book" threshold
- 35%: CAGR +27.8%, Calmar 3.98 — further along the curve

### Preliminary validation the fresh session must do first

Before executing any weight decision, verify the robust-opt result. The thesis is sensible but the machinery deserves one clean-eyes check:

1. **Inspect `data/mode2/crypto_robust_opt.parquet`.** Look at the full ranking. Does the min-Calmar surface show a smooth plateau around SMA-{125, 150, 175}/top2, or is SMA-125 a spiky local max? A plateau means robust; a spike means grid-fitting. We claim plateau — verify.
2. **Check OOS/IS CAGR ratio.** 89% looks fine, but compare to what the old 200/top3 config showed on the same halves (not what the validation runner reported, which used a slightly different train window). Recompute both on identical date ranges.
3. **Audit the robust-opt script.** Any bugs in the min-Calmar computation? In the train/test split for the final OOS holdout check? Re-read `scripts/crypto_robust_opt.py` line-by-line.
4. **Sanity-check the portfolio-weight table above.** Re-run `marginal_portfolio_contribution` at 25%, 30%, 35%, 40% independently. Make sure the union-calendar alignment (fixed earlier this session) is behaving correctly — it was buggy initially.
5. **Specifically: is 40% Calmar 4.10 real or an artifact of the alignment?** MaxDD nearly flat across weights is suspiciously clean. Verify by running the combined portfolio at different weights with a careful look at *when* the drawdowns happen in each.

**If steps 1-5 find no errors, proceed to the weight decision. If they find an error, fix it first, then re-assess.**

### The code change (for reference, not for reversion)

Commit `1baad0d`. Changed `strategies/crypto_momentum.py` defaults:
```python
# Before
lookback_days=21, top_n=3, btc_ma_period=200
# After
lookback_days=21, top_n=2, btc_ma_period=125
```

Also: `scripts/filter_check.py` (monitor MA 200 → 125), `strategies/portfolio.py` `compute_btc_trend_filter` (default 200 → 125), `dashboard/src/types.ts` (`btc_ma200` → `btc_ma125`). Expanded Test 3 sweep grid in `scripts/run_validation.py`.

**This stays unless step 1-5 find an error.** User was explicit: not a revert question.

### Questions a fresh session should ask

- Does the validation find any error in the robust-opt? (Step 1-5 above.) If yes — fix first, then revisit. If no — weight question stands.
- What's the user's actual risk tolerance for a single-strategy drawdown? The OOS data says 40% weight has combined MaxDD -7.1%, but stress-test: what if crypto alone drew down -30% in the next 12 months while equities were flat? At 40% weight that's -12% combined drawdown from the crypto leg alone. At 25%, -7.5%.
- Is the live gate status the blocker, or the user's psychological tolerance? (The first is mechanical; the second is the real decision variable.)
- Should we explicitly test 30% and 35% as compromise positions, or is this a binary 25/40 decision in the user's mind?

### How the weight change would actually happen

Account sizing is not a code-level change — it's a capital allocation decision. Currently the 4-account architecture is "$100K each" (25% capital split by default). To shift to 40% A4, we would:

1. Rebalance capital across Alpaca paper accounts (move $60K from equity accounts to A4, or equivalent).
2. Update CLAUDE.md to reflect new weights.
3. Update `portfolio_fit` default weight in the validation runner if we want forward validation to use the new weight as baseline.
4. The strategies themselves don't change — only the capital base each account trades from.

For real money later, this becomes a starting-capital decision at account setup.

### What the current code does

SMA-125/top2 is the production config. Gate status: PASS. Account 4 trades at whatever the user allocates to account 4 — currently $100K paper. The weight question is operational, not code. A4 is presently in cash (BTC below its 125d MA) — buys time to decide without operational pressure.

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
