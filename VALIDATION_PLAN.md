# Validation Plan — April 2026

**Status:** Not run. This is the handoff doc for the next session.

**Context for a fresh session:** Read `CLAUDE.md` for system state, `BREAKTHROUGH.md` for the latest strategic framing (Mode 2 filter thesis was tested and killed 2026-04-17), then this doc for what we do next.

---

## The diagnosis

The quantitative trading system has a load-bearing gap: **the statistical validation framework was built but never used.**

Concrete evidence from 2026-04-18 review:
- `backtesting/validation.py` (326 lines: walk-forward, Monte Carlo, regime tests) was added in commit `175c234` and has never been called since. `git log -S "walk_forward_analysis"` and `git log -S "full_validation"` both return only the initial commit.
- PLAN.md line 197 is explicit: *"No Live Money Without Statistical Validation"* — with a pre-committed reject threshold at line 647: *"Walk-forward median OOS Sharpe < 0.50 → reject."*
- 4 accounts nevertheless went to live paper trading with only full-sample backtest numbers.
- `mode2/crypto_autoresearch.py` (commit `b04edd6`) then did the opposite of what validation would do: swept ~40 parameter configurations on the full 2018-2026 sample and picked the winning Sharpe (1.56 → 2.01). That number was then written into `CLAUDE.md` and `BREAKTHROUGH.md` as if it were a ground-truth measurement.

**Every Sharpe / CAGR / MaxDD currently in CLAUDE.md is an in-sample tuned number.** We do not know how any of these strategies perform out-of-sample. Account 4 (crypto) is the most suspect because it's the most-optimized and has the shortest usable history.

This is a real problem, not a cosmetic one. The bridge plan in `/Users/george/Desktop/Projects/FIREMaster` depends on the trading system hitting something like its claimed Sharpe when real money goes in. If the 2.01 crypto Sharpe is actually 1.2 OOS, the bridge math changes.

---

## Scope

**All 4 accounts get validated, in this order:**

1. **Account 4 (crypto)** — most suspect. Most recent tuning (2026-04-15), most parameter knobs, shortest data history (2018 onwards), one completed crypto cycle plus one ongoing one.
2. **Account 1 (stock momentum + SPY filter)** — simplest, cleanest. Should pass easily if the factor is real.
3. **Account 2 (trend + low-vol blend)** — two strategies blended with a vol-scaling overlay. More moving parts.
4. **Account 3 (reversal + momentum blend)** — weekly cadence, the only non-monthly equity account.

Each account gets the full test battery. Accept whatever the numbers say, even if painful.

---

## The tests

### Test 1 — Clean out-of-sample holdout (headline number)

The single most important test. For each account:
- **Train period:** earliest data through 2022-12-31. Use this to pick parameters *exactly the way the existing tuning script does* (re-run `crypto_autoresearch.py` on train-only; for equity, re-run whatever parameter selection was used).
- **Test period:** 2023-01-01 through today. Measure OOS Sharpe, CAGR, MaxDD with the locked-in parameters. No further tuning.
- **Report:** OOS Sharpe, OOS CAGR, OOS MaxDD, ratio of OOS Sharpe to in-sample Sharpe.

This answers the question directly: does the tuned strategy work on data it didn't see?

### Test 2 — Walk-forward across rolling windows

Uses the existing `backtesting.validation.walk_forward_analysis` function that already exists and has never been called. For each account:
- Windows: 3-year train, 1-year test, roll forward 6 months.
- For each window: refit parameters on train, measure Sharpe on test.
- **Report:** median OOS Sharpe, min OOS Sharpe, # of windows with OOS Sharpe ≥ 0.5.

Tests parameter stability across time, not just one train/test split.

### Test 3 — Parameter stability split test (catches autoresearch overfitting)

Specifically for crypto (the most-optimized account):
- Re-run `mode2/crypto_autoresearch.py` on 2018-2021 only. Record top-5 configs by Sharpe.
- Re-run on 2022-2026 only. Record top-5 configs by Sharpe.
- **Compare:** do the best parameters agree? If 2018-2021's "best SMA-150 / top-2 / 21d / 15% vol" is 2022-2026's rank 17, the autoresearch is fitting noise.

If best-config agreement is weak, the entire "optimized" number is invalid regardless of what Test 1 shows.

### Test 4 — Monte Carlo bootstrap

For each account, using the existing returns series:
- Block bootstrap: resample 20-day blocks with replacement, 1000 iterations.
- Compute Sharpe, MaxDD for each resample.
- **Report:** 5th percentile Sharpe, 95th percentile MaxDD, fraction of resamples with Sharpe > 0.5.

Gives a confidence interval on the claimed Sharpe. If the 5th percentile is below 0.5, the headline Sharpe is inside the noise band.

---

## Decision thresholds

Pre-commit to these before running. No moving goalposts.

| Outcome | OOS Sharpe (Test 1) | OOS/IS ratio | Action |
|---|---|---|---|
| **Passes** | ≥ 1.0 AND ≥ 70% of in-sample | | Strategy validated. Update CLAUDE.md with OOS numbers. Keep live paper. |
| **Marginal** | 0.5–1.0 OR 50–70% of in-sample | | Pause further optimization on this account. Continue live paper for 3 months, re-measure. Do NOT ship to real money. |
| **Fails** | < 0.5 OR < 50% of in-sample | | Pause live paper on this account. Re-select parameters conservatively (prefer simpler defaults over tuned ones). Document the gap. |

Additional guardrails:
- If Test 3 shows parameter instability (best configs disagree across halves), treat as fail even if Test 1 passes — the tuning process is noise-mining and the Test 1 pass is luck.
- If Test 4's 5th percentile Sharpe is < 0.3, treat as fail.
- Account 4 (crypto) — if it fails, this is material. Paper trading can continue for learning, but the bridge plan assumptions need to update.

---

## The enforcement gate

So this never happens again.

**Build:** `data/risk_state/validation_state.json` — per-account validation record:

```json
{
  "account_1": {"last_run": "2026-04-19", "oos_sharpe": 1.24, "status": "pass", "expires": "2026-07-19"},
  "account_4": {"last_run": null, "status": "unvalidated"}
}
```

**Wire:** `POST /api/orders/rebalance/execute` checks validation state for the target account and returns 403 if:
- No validation record exists, OR
- `status != "pass"`, OR
- `expires` is in the past (enforces quarterly re-validation).

**Override:** Environment variable `FIRE_VALIDATION_OVERRIDE=1` with a warning banner on the dashboard. Intentional friction — you have to know you're bypassing it.

**Test:** add integration test `tests/test_validation_gate.py` that asserts rebalance is blocked for an unvalidated account.

---

## Concrete next steps for the next session

```bash
# 1. Create a validation runner script (this is the piece that's missing)
touch scripts/run_validation.py   # Runs all 4 tests for a specified account, writes to validation_state.json

# 2. Run on crypto first (the most suspect)
uv run python3 scripts/run_validation.py --account 4

# Review results. If fails, DO NOT re-optimize to rescue the number.
# Report honestly, update CLAUDE.md with OOS Sharpe (not in-sample).

# 3. Run on remaining 3 accounts
uv run python3 scripts/run_validation.py --account 1
uv run python3 scripts/run_validation.py --account 2
uv run python3 scripts/run_validation.py --account 3

# 4. Build the enforcement gate
# Modify api/routes/orders.py to check validation_state.json
# Add tests/test_validation_gate.py
# Add dashboard banner for unvalidated accounts

# 5. Update CLAUDE.md
# Replace every Sharpe/CAGR/MaxDD with OOS numbers.
# Mark "in-sample optimized" where we've kept the number because OOS wasn't measurable (e.g. too little data).

# 6. Update PLAN.md
# Line 402: change "[x] Build validation framework" to reflect that validation is RUN, not just built.
# Add a standing rule: every parameter change must be accompanied by a validation run.
```

Suggested file layout for the new script:

```
scripts/run_validation.py           # CLI runner, delegates to account-specific functions
backtesting/account_adapters.py     # Per-account glue: returns (strategy_fn, prices, start_date) tuples
backtesting/bootstrap.py            # Block bootstrap for Test 4 (not in validation.py yet)
data/validation_reports/            # Per-account markdown reports (one per run)
```

---

## The meta-point

The BREAKTHROUGH.md kill signal on the Mode 2 filter thesis (2026-04-17) gave us a clean answer to the wrong question. We asked "can Claude add alpha on top of Mode 1?" without first asking "is the Mode 1 alpha even real?"

The walk-forward gap is the bigger issue. Mode 2 being dead costs nothing — it was never live. Mode 1 is live across 4 accounts with numbers that might be 30-50% inflated by in-sample tuning. Finding out is a 2-day job that should have been done 6 weeks ago.

Rule going forward: **numbers in CLAUDE.md are OOS or they don't exist.** "In-sample optimized, OOS pending" is a valid state. "Sharpe 2.01" without a train/test split behind it is not.

Running the test is the breakthrough. Accepting whatever comes out is the discipline.
