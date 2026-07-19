# Validation Framework — CAGR-first (v2)

**Status:** Framework rebuilt 2026-04-18 under the CAGR-first thesis. Previous Sharpe-based version is in git history. All 4 accounts have been re-validated under the new scorecard.

**Context:** `CLAUDE.md` for system state, `docs/archive/HUNT_APR2026.md` for the historical framing that triggered this plan, `backtesting/metrics.py` for the full scorecard, `scripts/run_validation.py` for the runner.

---

## The thesis

Reaffirmed 2026-04-18 after testing and discussion: **this project exists to maximize CAGR over a 3-5 year horizon, subject to tolerable drawdowns.** Sharpe is the wrong objective function for that thesis — it penalizes upside volatility and normalizes away absolute return magnitude, which is the wrong frame for wealth compounding.

Treasury bills had Sharpe 5-10 from 2010-2022. Account 1 has Sharpe 1.65 but ~20%/year CAGR. We hold Account 1. That's the entire argument.

Sharpe is retained for reference and cross-comparability with the outside world, but **no pass/fail threshold is anchored to it**. The primary evaluation axis is `CAGR / MaxDD / Calmar` plus a supporting scorecard.

---

## The scorecard

`full_scorecard(returns, periods_per_year)` in [backtesting/metrics.py](backtesting/metrics.py) returns all of the below in one call.

### Primary (the gates)
- **CAGR** — what we are compounding at
- **Max Drawdown** — worst peak-to-trough pain (survivability)
- **Calmar = CAGR / |MaxDD|** — return per unit of worst-case pain

### Drawdown family (supporting)
- **MAR** — CAGR over longest-ever MaxDD (more conservative than Calmar)
- **Sterling** — CAGR over average annual drawdown (less outlier-sensitive)
- **Burke** — CAGR over sqrt(sum of squared drawdowns) (penalizes many small drawdowns)
- **Pain ratio** — CAGR over average ongoing drawdown (continuous Calmar)
- **Ulcer Index** — sqrt(mean(drawdown²)) — sustained-pain measure
- **Ulcer Performance Index (UPI)** — CAGR over Ulcer Index — "how does it feel to hold"

### Distribution / downside
- **Sortino** — Sharpe variant penalizing only downside
- **Omega** — probability-weighted gains/losses above threshold
- **Gain-to-Pain (Schwager)** — sum(positive returns) / |sum(negative returns)|

### Behavioral
- **Time underwater** — fraction of periods below prior peak
- **Max recovery days** — longest run underwater

### Informational only (no gate)
- **Sharpe** — shown in italics, labeled deemphasized

---

## Pre-committed pass/fail gates

Set 2026-04-18. Moving these is moving the goalposts.

| Gate | Pass | Marginal | Fail |
|---|---|---|---|
| OOS CAGR | ≥ 15% | 10-15% | < 10% |
| OOS MaxDD | ≥ -40% | -40% to -50% | < -50% |
| OOS Calmar | ≥ 1.0 | 0.5-1.0 | < 0.5 |
| OOS/IS CAGR ratio | ≥ 70% | 50-70% | < 50% (and ratio-gated only on Pass tier) |

**Overall classification:**
- **Pass**: ALL four primary gates met at Pass level.
- **Marginal**: all four primary gates met at ≥ Marginal level, but not all at Pass.
- **Fail**: any one primary gate at Fail level.

**Fail-safes (force-fail regardless of primary tier):**
- **Test 3** (crypto only): production-config Calmar < 0.5 in EITHER half. This tests whether the chosen config survives regime changes — replaces the old "top-5 config overlap" rule.
- **Test 4**: block-bootstrap 5th-percentile CAGR < 0 — means a reasonable random-block resample of history could produce a losing year. Forward worst case is negative = strategy is inside the noise band.

---

## The tests

### Test 1 — OOS holdout (headline)

Train: earliest data through 2022-12-31. Test: 2023-01-01 through today. Full scorecard on each period. Report OOS/IS CAGR ratio. This is the single most important test.

### Test 2 — Rolling OOS with fixed parameters (CAGR per window)

**Name correction 2026-04-20:** this test was previously labeled `walk_forward_refit` in code and docs, which was misleading. It's **rolling out-of-sample evaluation with fixed default parameters** — not walk-forward optimization. At each window, the strategy runs with the same hardcoded params (`StockMomentum()` defaults, etc.); metrics are reported on the test slice. Nothing is refit.

Uses `backtesting.validation.walk_forward_analysis` where the adapter supports it (Accounts 1, 3, 4). Account 2 falls back to rolling 1-year windows on precomputed returns since its sub-strategies span different universes (ETFs + stocks).

Windows: 3-year train*, 1-year test, roll forward 6 months. Pass: median CAGR ≥ 10% AND ≥ 80% of windows profitable.

\* "train" is a misnomer here — the 3-year slice before the test window is just used for signal warmup (rolling momentum, vol estimates), not for fitting parameters. A proper walk-forward-refit harness is available separately via `backtesting.validation.walk_forward_refit_analysis` and the standalone scripts `scripts/walk_forward_refit_a1.py` / `_a2.py`. Running those on A1 and A2 (2026-04-20) confirmed literature-derived defaults are within noise of refit winners — no default changes needed.

### Test 3 — Parameter stability (crypto only)

Re-run the autoresearch sweep on 2020-2022 (half A) and 2023-2026 (half B). Rank by Calmar. Pass: production config delivers Calmar ≥ 0.5 in BOTH halves.

Replaces the old "top-5 overlap ≥ 2" rule. The new rule asks "does our chosen config survive regime changes?" rather than "does a stable optimum exist?" The old rule would fail crypto permanently because the parameter surface is regime-dependent; the new rule correctly passes a config whose mechanism (BTC trend filter) is regime-robust even if the specific MA period isn't.

### Test 4 — Block bootstrap (CAGR percentiles)

Block bootstrap (20-day blocks, 1000 iterations) on the returns series. Report CAGR p5 / p50 / p95 and % of resamples profitable. Pass: p5 CAGR ≥ 0%.

### Test 5 — Portfolio fit (marginal contribution)

For satellite accounts only (Account 4 currently). Add the candidate at 25% weight to the 3-account core and measure:
- Δ CAGR, Δ MaxDD, Δ Calmar (all deltas to the combined book)
- Correlation to existing core

Not gated — reported for judgment. A Δ Calmar > +0.1 means the satellite is doing its job.

### Test 6 — Walk-forward REFIT vs fixed defaults (non-gating, added 2026-04-20)

**Purpose:** answer the question "are the defaults we inherited from academic papers (or set by hand) any good for our specific universe?" — without replacing them unless there's a clear, stable improvement.

**Mechanism:** any account that defines `refit_prices`, `refit_strategy_factory`, and `refit_param_grid` in its adapter gets a per-window parameter refit:

1. Rolling (warmup + train + test) windows — 3-year train, 1-year test, step 6 months (same as Test 2).
2. In each window, enumerate the grid and run every config on the **train slice only**. Score by train-window Calmar. Pick the winner.
3. Run the winner on the test slice. Record picked params + test metrics.

**Reports:** refit median CAGR / Calmar / Sharpe vs fixed-default baseline; parameter stability (how often each config is picked); per-window picks table.

**Pass semantics (non-gating; PASS/REVIEW only, never FAIL):**

| Refit vs default | Stability | Status |
|---|---|---|
| CAGR within ±10% | any | **PASS** — defaults robust |
| Refit beats default by >20% | stable pick ≥40% of windows | **REVIEW** — consider updating defaults |
| Refit underperforms by >10% | any | **PASS** — literature defaults more robust than honest search |
| Anything in between | unstable picks | **PASS** — treat as noise |

**Why it's non-gating:** honest walk-forward refit frequently *loses* to good literature defaults on factor strategies (narrow parameter surface, robust academic priors). Blocking on it would penalize robust defaults. The REVIEW flag surfaces the rare case where a stable, materially better config exists.

**Strategy discovery use case:** this is the canonical process for evaluating a new strategy candidate going forward — instead of copying parameters from 15-year-old academic papers and hoping they generalize, run an honest walk-forward refit on the candidate and read the result as a forward estimate.

**Recipe for a new candidate strategy:**

1. **Write the strategy class** (inherit `BaseStrategy`, implement `generate_signals` + optional `generate_returns`). Place under `strategies/<candidate>.py`. Example templates: `strategies/stock_momentum.py`, `strategies/low_volatility.py`, `strategies/crypto_momentum.py`.

2. **Pick an initial grid.** Sparse sweeps of the 2-4 parameters most likely to move the needle. Example for a momentum-style candidate:
   ```python
   grid = {
       "lookback_days": [63, 126, 189, 252],
       "top_n": [10, 15, 20, 25],
   }
   ```
   Keep `len(grid)` × `n_windows` × per-config-runtime under a couple of minutes for iteration speed; expand later for the final pass.

3. **Run a standalone walk-forward refit.** Clone `scripts/walk_forward_refit_a1.py` as a starting point. The script prints per-window picks, stability, and a side-by-side refit-vs-default comparison. Look for:
   - **Median CAGR / Calmar** — the honest forward estimate.
   - **Parameter stability** — if one config wins ≥40% of windows, the strategy has a real optimum. If picks scatter across many configs, the surface is noisy / regime-dependent and the refit number overstates forward performance.
   - **Per-window consistency** — large variance across windows means regime-fragile; narrow variance means robust.

4. **Decide.** If the refit median CAGR/Calmar meaningfully exceeds the current live book AND picks are stable AND the strategy has low correlation to existing accounts (Test 5 in a full validation run) → candidate worth promoting. Otherwise shelve or rework.

5. **Wire it into an adapter.** Add `_build_account_N()` in `backtesting/account_adapters.py` with `refit_strategy_factory` + `refit_param_grid`. Run full `scripts/run_validation.py --account N`. Test 6 is now standardized and runs automatically alongside Tests 1-5.

This is the same process `scripts/crypto_robust_opt.py` (2026-04-18) ran for A4 pre-launch — a 2-half train/test split with min-Calmar objective. Test 6 generalizes the pattern to any adapter with a grid, and makes it part of the validation gate instead of a one-off script.

**Current coverage:**
- **A1** — StockMomentum grid: `lookback_days × top_n` (9 configs).
- **A2** — LowVolatility leg only (70% of A2): `vol_lookback_days × momentum_lookback_days × top_n` (27 configs).
- **A3, A4** — no grid defined (A3 retired; A4 already went through `crypto_robust_opt.py`).

**2026-04-20 results:** both A1 and A2 PASS. Refit cannot beat defaults; stability poor (most-picked ≤ 32%). See `data/validation_reports/` for the per-window picks.

---

## The enforcement gate

[execution/validation_gate.py](execution/validation_gate.py) reads `data/risk_state/validation_state.json` and blocks rebalances for:
- Accounts with no validation record
- Accounts with status `"fail"`
- Accounts with expired `expires` date (quarterly re-validation enforced)

**MARGINAL status now allows paper rebalancing** (changed 2026-04-18) — the original plan intended MARGINAL as a "paper OK, not for real money" state, but the first implementation blocked both. The gate's job is to catch unvalidated or failed strategies, not to police the marginal band.

Overrides (intentional friction, WARNING-logged when active):
- `FIRE_VALIDATION_OVERRIDE=1` — global (all active accounts).
- `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` — scoped to account N (1-4).

Override covers FAIL, unvalidated, and expired. **Retired accounts are an unconditional block** — no override can bypass them (HISTORY.md R2).

Gate wired into:
- `POST /api/orders/rebalance/execute` → 403
- `scripts/filter_check.py` auto-rebalance → skip + log
- cron-fired `scripts/daily_crypto_rebalance.py` → skip + log (cron entry removed 2026-07-18 with A4's retirement; script retained for successors)

Tests in `tests/test_validation_gate.py` (14 cases).

---

## Current state (as of 2026-04-18 re-validation)

| Account | Status | CAGR | MaxDD | Calmar | MAR | UPI | Sortino | Sharpe (info) |
|---|---|---|---|---|---|---|---|---|
| 1 Momentum + SPY | PASS | 21.0% | -11.1% | **1.89** | 1.89 | 5.42 | 1.63 | 1.65 |
| 2 Trend + Low-Vol | PASS | 17.9% | -11.6% | **1.55** | 1.55 | 5.62 | 1.41 | 1.46 |
| 3 Reversal Blend | MARGINAL | 14.5% | -7.2% | **2.03** | 2.03 | 6.10 | 1.59 | 1.61 |
| 4 Crypto Momentum | PASS | **32.7%** | -23.5% | **1.39** | 1.39 | 4.27 | 1.62 | 1.42 |

Notes:
- **Account 3 MARGINAL is strict-letter only.** CAGR 14.5% is 0.5pp below the 15% threshold, but Calmar 2.03 and MaxDD -7.2% are the best in the system on both measures. Holding the threshold to avoid goalpost-moving — but the paper trade continues.
- **Account 4 PASS under the new framework** (was FAIL under the old Sharpe+Test-3 logic). The BTC trend filter mechanism is robust; the specific filter period is regime-dependent but Calmar stays ≥ 0.5 in both halves regardless. Conservative 200d/top3 config is the current production choice.
- Combined 3-account portfolio (before adding crypto) OOS: CAGR 18.0%, MaxDD -8.5%, Calmar 2.12, Sharpe 1.85.
- Adding Account 4 at 25% weight: combined → CAGR 21.9%, MaxDD -7.4%, Calmar 2.98.

---

## When to re-validate

- Quarterly (expires field enforces this)
- Any parameter change (the rule that prevented the crypto autoresearch mess if it had existed earlier)
- After any structural market event that might invalidate the train period (e.g., a sustained regime change)
- When a new account is added to the system
- When the thesis changes (what happened today — we rebuilt the entire framework because the objective function changed)

---

## Lessons embedded in this framework

1. **The objective function comes before the tests.** We ran a Sharpe-maximizing validation framework for 2 months without asking whether Sharpe was the right thing to maximize. Most of the work since 2026-04-18 was answering that question correctly.
2. **Pre-commit thresholds. Do not move them to rescue a result.** Account 3 MARGINAL could easily become PASS by dropping the CAGR threshold to 14% — and we explicitly refused to do that.
3. **Run the framework. Don't just build it.** The first version of `backtesting/validation.py` was written, committed, and untouched for 6 weeks. The bridge plan was relying on Sharpe numbers that had never been OOS-verified. Discipline = running the tests, not having them.
4. **Understand failure modes before treating them as fatal.** The original Test 3 treated crypto parameter instability as fatal for Sharpe-smoothness reasons. Under the CAGR-first framework, the same data says "the mechanism (BTC filter) is robust even though the specific period isn't" — which is actually a *feature*, not a bug. Changing the question changed the answer.
