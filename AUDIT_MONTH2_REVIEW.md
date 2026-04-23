# Month-2 Audit Review — Critical Assessment & Forward Issues

**Date:** 2026-04-21
**Scope:** Adversarial review of the Month-2 audit arc (C1–C7, S1–S5, D1–D4, R1–R16). Independent reads of the code behind every closed Tier-1 and Tier-2 item, with an explicit mandate to surface bugs the audit didn't catch.
**Method:** Two parallel adversarial agents + direct verification of their claims against source. Findings below include corrections where agent claims didn't hold up — this review is only useful if it's honest about its own signal-to-noise.

**Post-review status (2026-04-21 Pass 1a, commit `d1b753b`):** N2 (SPY+BTC NaN guards) and N5 (plausibility ERROR log) resolved, with 2 regression tests added (suite: 90 → 92). N1 verified against source and **reclassified as miscast** — sim and live both use `sqrt(252)`, so the parity-break the review feared doesn't exist (see §3 N1 update). Pre-2026-05-04 rebalance scope is closed.

**2026-04-22:** T4 closed — `require_validated(broker.account)` is now step 0 of `compute_rebalance` (defense-in-depth alongside the three call-site guards), with 2 new tests pinning the retired-account block + override-not-bypassable semantics. Two stale `test_plausibility` assertions updated to the current "escapes band" error format. Suite now 113 passing.

T1, N4, N3, O1–O4 remain.

---

## TL;DR

The Month-2 audit arc is the strongest work in the project's history. 22 of the 27 enumerated findings are closed, including all Tier-1 (except C3 survivorship) and all Tier-2/Tier-3. The fixes are real — not papered over. The combined headline (3-acct @ 1/3: CAGR 26.5%, MaxDD -6.2%, Calmar 4.28) is now produced by code the live book actually runs.

**But the fix velocity has created its own risk:** ~15 substantial changes landed in 2 days, ~150 lines deleted from risk_manager.py, three new modules (`vol_scaling.py`, `plausibility.py`, `costs.py`, `drawdown_halt.py`), and the test suite grew from ~40 to 90 cases. **Test coverage still has integration-level holes, observability in the rebalance journal is thinner than it should be, and four real latent issues slipped past the audit.** None are real-money blockers *today* but they should be in Month-3 scope before the live-tracking clock (reset 2026-04-20) matures into a graduation decision.

**What's excellent:** C4 (live vol-scaling with 1e-6 parity verification), C5 (replace-with-alert + empirical 16-year halt sweep), C6 (the honest 3.4pp A4 drag — audit initially underestimated by ~10×), S5 (full plausibility layer vs. the initial one-liner). These are senior-quality fixes.

**What's competent but lower-signal:** C7 option C (removed cap entirely). Defensible but the belt-and-suspenders argument for option B is non-trivial. R4/R5 (journal persistence + halt-reset audit trail) were correct and cheap.

**What's outstanding (5 new findings):** see §3.

---

## 1. State of the Project

### Strategies
- **A1 (Stock Momentum + SPY Filter):** PASS. OOS CAGR 27.2%, Calmar 2.76. Clean sim/live parity (no vol-scaling, C3 survivorship noted).
- **A2 (Trend + Low-Vol):** MARGINAL (was PASS pre-C4). OOS CAGR 11.0%, Calmar 1.51. Paper-allowed. The PASS→MARGINAL transition is the honest one — backtest was leveraging the low-vol leg up to 1.5× in calm regimes that live couldn't realize.
- **A3 (Reversal + Momentum):** RETIRED. Slot preserved.
- **A4 (Crypto Momentum Rotation):** PASS. OOS CAGR 40.4%, Calmar 3.18. Post-C6 drag came in 3.4pp higher than gross — the audit initially estimated 0.5-1pp, and the empirical measurement is a load-bearing correction.
- **Combined (A1+A2+A4 @ 1/3):** CAGR 26.5%, MaxDD -6.2%, Calmar 4.28. Forward-looking haircut to 2.5-3.5 correctly cited in CLAUDE.md.

### Infrastructure
- 4 Alpaca paper accounts. A3 liquidated, kept as validation-gate-blocked slot.
- Daily 4:30 PM ET filter monitor via launchd + macOS notifications.
- Daily 00:05 UTC A4 APScheduler job.
- Monthly manual rebalance on A1 & A2 (next: 2026-05-04).
- Cross-process concurrency: `dual_rebalance_lock` unifies async + file locks across API, APScheduler, and filter_check cron.
- Cache atomicity: `write_parquet_atomic` across all live-path writers.
- S5 plausibility: 5 tickers defended with write-time bands + read-time Alpaca cross-validation + dashboard banner.

### Test Suite
90 passing tests across ~20 files. Good coverage of: vol-scaling math, plausibility bands, drawdown latch, cost turnover, locks, risk-state shape. Integration-test gaps detailed in §4.

---

## 2. Assessment of Recent Fixes

### Excellent
- **C4 (live vol-scaling, 2026-04-21).** The 1e-6 parity walk across A2's 32-row snapshot history is exactly the right verification — it catches wiring bugs bit-exactly, not just "within noise." The decision to go option B (Kelly-on-leverage in live) over option A (strip from backtest) was the sophisticated call, not the easy one. Cap=1.0 enforcement at the wire site (regardless of config) is good defensive coding.
- **C5 (drawdown redesign, 2026-04-21 session 6).** The 16-year IS+OOS halt sweep (`tests/test_drawdown_halt.py` + the prose sweep in AUDIT_MONTH2) is the best kind of empirical verification. Demonstrated -15% never fired, -35% never fires, -10% fires ~3×/16y/strategy. Replaces a plausible-sounding hysteric halt with an empirically-calibrated alert + deep kill-switch. The afternoon simplification pass (~150 lines deleted) is the discipline of stripping work that turned out not to carry weight — rare and correct.
- **C6 (transaction costs, 2026-04-21).** The headline number is the audit correcting *itself*: the initial estimate was 0.5-1pp A4 drag; empirical measurement came in at 3.4pp because daily turnover is ~8% (~20× annualized one-way), not ~2×. Discovery and disclosure of this was honest. Per-strategy costs in the adapter's `strategy_fn` / `refit_factory` closes a parity gap in Test 2/6 too.
- **S5 full layer (2026-04-21 afternoon).** Started as a 3-line `max() < 1000` check on BTC; grew into a real defensive layer with per-ticker bands, dashboard surfacing, and 17 unit tests. That scope-growth was correct — the initial finding was a canary for a wider failure-mode class.

### Competent
- **C7 option C (cap removed entirely).** Defensible — strategy `top_n` already controls concentration. But option B (per-strategy caps) would have been equally defensive and explicit. The C choice relies on the strategy-weight invariant check as the only remaining guardrail; if a future strategy has a bug producing runaway weights, we rely on `sum > 1.0 + 1e-6` catching it *before* it hits the broker. That works for current strategies; it's a tighter belt with no suspenders for future ones.
- **R4 (try/finally for journal persistence).** Correct, but the current implementation (3 call sites wrapping `execute_rebalance`) creates drift risk — if a 4th call site is added, the try/finally must be duplicated. A context-manager refactor (`with journaled_execute(...):`) would make the protocol load-bearing at the type level.
- **R2 (retired = unconditional block).** Correct, but there's no automated test that exercises the `status="retired"` path end-to-end through `compute_rebalance` on the live-path broker. `tests/test_validation_gate.py` covers the gate function itself but not the rebalance call site.

### Notes
- The PLAN.md reference in CLAUDE.md still mentions `Pre-trade risk checks — circuit breakers, position limits (max 20% per position), portfolio halt at -15% drawdown` (PLAN.md:496 per the audit doc). CLAUDE.md has been updated to reflect the post-C5/C7 reality; PLAN.md has not. Low priority but worth a grep-and-sync pass.

---

## 3. NEW Findings (not in AUDIT_MONTH2)

Verified against source, not just reported by agents. Findings the adversarial review surfaced that didn't survive verification are called out in §5.

### 🟢 N1. `ppy=252` hardcoded in `compute_live_vol_scalar` for A4 crypto — RECLASSIFIED (miscast, not a parity bug)
**File:** `execution/vol_scaling.py:75`

```python
realized_vol = math.sqrt(latest_var) * math.sqrt(252)
```

**Original concern:** A4 crypto trades 365 days/year; if backtest used `sqrt(365)` and live used `sqrt(252)`, live would under-report vol by ~17% → scalar inflated by ~17% → A4 live exposure systematically above backtest.

**Verification (2026-04-21, post-review):** both sides use `sqrt(252)`:
- Backtest: [`strategies/portfolio.py:299`](strategies/portfolio.py#L299) — `realized_vol = np.sqrt(ewma_var) * np.sqrt(252)`
- Live: [`execution/vol_scaling.py:75`](execution/vol_scaling.py#L75) — `realized_vol = math.sqrt(latest_var) * math.sqrt(252)`

**Sim/live parity at 1e-6 holds.** The C4 verification claim is intact.

**Subtler residual nuance (not a bug, a labeling artifact):** because A4 equity snapshots accumulate on the crypto 7-day calendar, realized daily returns have ~365 obs/year; annualizing by `sqrt(252)` under-reports vol by ~17% on both sides consistently. Net effect: the `vol_target=0.15` label corresponds to a realized ~0.18 target. The scalar is clipped at `cap=1.0` anyway (crypto realized vol is typically 40-80%, so `raw_scalar ≈ 0.3` — well below the cap), so this labeling artifact is absorbed by the clip in practice.

**Action:** docstring clarification in `execution/vol_scaling.py` (Month-3, non-urgent). No code change, no parity correction needed.

**Urgency:** none. The original gating concern ("becomes load-bearing when BTC crosses 125d MA") was predicated on a parity break that doesn't exist.

### ✅ N2. SPY/BTC filter scalar NaN propagation on cold-start / short history — CLOSED (2026-04-21, commit `d1b753b`)
**File:** `execution/rebalance.py:218-220, 230-232`

**Resolution:** `pd.isna(scalar)` guard + `RuntimeError` added at both SPY (rebalance.py:222) and BTC (rebalance.py:236) filter sites in `_get_portfolio_signals`. Two regression tests added: `test_spy_filter_nan_raises_rather_than_liquidating` (live `sm_filtered` path) and `test_btc_filter_nan_raises_rather_than_liquidating` (defensive — uses monkeypatch to enable `btc_filter=True` on `crypto_momentum_filtered` since no portfolio currently enables it at that level).

**Original finding (retained for context):**

```python
spy_filter = compute_spy_trend_filter(start=lookback_start, live_price=live_spy)
scalar = spy_filter.iloc[-1]  # Latest filter value (1.0 or 0.5)
combined_weights = {sym: w * scalar for sym, w in combined_weights.items()}
```

If `spy_filter.iloc[-1]` is NaN (data gap, insufficient history for 200d MA warmup, fresh cache with bad read), `scalar = NaN` multiplies every weight → all weights NaN → downstream `abs(w) > 1e-6` filter strips them → `combined_weights = {}` → `compute_rebalance` generates an empty target book → **full liquidation**.

This is not a theoretical path. On a cloud deploy cold-start, the 200d SPY history must be freshly downloaded; a transient partial fetch + `compute_spy_trend_filter` with MA warmup not yet valid could produce NaN. S4 retries the download but doesn't guard the derived scalar.

**Fix:** guard at line 219 / 231:
```python
scalar = spy_filter.iloc[-1]
if pd.isna(scalar):
    raise RuntimeError("SPY filter scalar is NaN; refusing to rebalance")
```

Loud failure beats silent liquidation. Same pattern at the BTC filter site.

**Urgency:** bites on cloud deploy, doesn't bite on the current macOS setup (caches already warm).

### 🟠 N3. `compute_drawdown` snapshot load is unprotected against mid-write state
**File:** `execution/risk_manager.py:79`

```python
equity_history = load_snapshots(account)
```

Called during `/api/portfolio/risk` polls (every 30s) and at `compute_rebalance` entry. Meanwhile, `save_snapshot` and `backfill_from_alpaca` take `file_snapshot_lock` internally. The reader doesn't take the lock.

**Upon verification this is actually *not* a correctness bug for the max()-based peak derivation** — a concurrent append can't corrupt `eq.max()` semantics (worst case, the reader misses a new row and computes peak slightly stale). The (corrected) agent claim that this inflates the peak was wrong; a newly-appended row can only add a valid equity point, and `peak = max(snapshot_peak, current_equity)` is robust either way.

**But it IS a parquet-read-during-rename bug on atomic-write timing.** `write_parquet_atomic` does `open(tmp).write() → os.replace(tmp, final)`. pyarrow's `read_parquet` on `final` during the rename can raise on some filesystems (NFS especially, and occasionally APFS under load). The reader handles this with a try/except (`log.warning("load_snapshots failed")` + fallback `equity_history=None` → `snapshot_peak=0.0` → peak=current_equity → dd=0.0), so **a catastrophic drawdown in progress could silently compute dd=0.0 during the exact millisecond when the halt check runs.**

**Fix:** take a shared read lock on `file_snapshot_lock` in `compute_drawdown`, or cache the snapshot load at rebalance entry and pass `equity_history=` explicitly.

**Urgency:** astronomically unlikely on macOS local disk; becomes non-trivial on Fly.io with network-mounted volumes.

### 🟡 N4. Rebalance journal does not persist pre-filter/pre-scalar signal weights
**File:** `execution/rebalance_log.py` + `execution/rebalance.py:285-306`

Current journal records `portfolio_value`, `spy_filter_scalar`, `btc_filter_scalar`, `vol_scalar`, `orders`, `execute_error` (post-R4/R16). **Missing:** raw strategy signals before filter and scalar application.

If a future incident produces unexpected orders ("why did A1 buy TSLA on 2026-06-17 but not AMZN?"), reconstruction requires re-running `generate_signals` against the price cache as it existed on that date — which we can't do reliably because the cache has since been overwritten. The rebalance journal is the only contemporaneous record, and it doesn't carry enough state.

**Fix:** extend `log_rebalance` with `raw_signal_weights: dict[str, float]` and `post_filter_weights: dict[str, float]`. ~15 lines. Enables one-parquet-read post-mortems.

**Urgency:** low until the first incident; then immediately becomes the most-wanted piece of data.

### ✅ N5. Plausibility state write silently swallows `os.replace` failures — CLOSED (2026-04-21, commit `d1b753b`)
**File:** `data/plausibility.py:302-314`

**Resolution:** `log.error(f"Failed to persist plausibility state to {STATE_PATH}: {e}")` added before re-raise in `_write_state`. Matches the shape of [`risk_manager._save_state`](execution/risk_manager.py#L161) for consistency.

**Original finding (retained for context):**

```python
try:
    os.replace(tmp_path, STATE_PATH)
except OSError:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise
```

The `raise` re-raises correctly, but callers (`_record_failure`, `_record_success`, `_record_divergence`) are themselves called from exception-suppressing paths (write-time plausibility assertion failure logs + continues). Net effect: if `os.replace` fails (disk full, permission change, network volume hiccup on cloud), the plausibility-failure event is silently lost from state, and the dashboard banner doesn't fire.

**Fix:** log the exception at ERROR before re-raising:
```python
except OSError as e:
    log.error(f"Failed to persist plausibility state: {e}")
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise
```

Cheap, correct, and gives visibility into a silent-failure path. Same pattern in `_save_state` at `risk_manager.py:162` — already has warning log, pattern match this.

**Urgency:** low on macOS; meaningful on cloud.

---

## 4. Test Coverage Gaps

### 🟠 T1. No end-to-end integration test for `compute_rebalance → execute → snapshot → journal`
**Files:** `tests/test_rebalance.py` (unit tests against mock broker); `tests/test_rebalance_log.py` (journal unit tests).

All 11 rebalance tests mock at the broker boundary. There's no test that walks the full pipeline: preview → execute → post-trade snapshot → journal entry → post-conditions. This is the chain where R4 (journal persistence across execute raises) lives, and it's only tested by verifying `log_rebalance` is called — not by verifying a real-shaped journal entry survives an execute-level exception.

**Fix:** `test_full_rebalance_chain_journal_persists_through_execute_failure()`. ~40 lines.

### 🟠 T2. Vol-scaling parity not covered by the test suite
**File:** `tests/test_vol_scaling.py:69-98`

The existing parity test uses synthetic equity series. The real 1e-6 parity verification that proves the C4 fix works was a **manual script walking A2's snapshot history day by day** — referenced in the AUDIT_MONTH2 writeup but not committed as a test.

**Fix:** add `test_vol_scalar_matches_backtest_on_a2_snapshot_history()` that reads `data/processed/snapshots_acct2.parquet` and runs the parity walk programmatically. If the test file is environment-specific (depends on real data), gate it on fixture presence and skip in CI-without-data.

### 🟡 T3. A4 C6 drag empirical value not pinned by a test
**File:** `tests/test_costs.py`

The 3.4pp A4 drag is the headline number from the C6 fix — it's in CLAUDE.md and load-bearing for combined Calmar 4.28. There's no test that runs A4's full backtest through the cost model and asserts `gross_cagr - net_cagr ≈ 3.4pp ± 0.5pp`. If a future edit changes the 20 bps crypto rate, only the next validation run catches it.

**Fix:** `test_a4_crypto_cost_drag_matches_audited_3_4pp()`. Slow (runs full A4 backtest), should be marked `@pytest.mark.slow` and excluded from quick-loop.

### ✅ T4. Retired-account block not tested through `compute_rebalance` itself — CLOSED (2026-04-22)

**Resolution:** `require_validated(broker.account)` added as step 0 of `compute_rebalance` in [execution/rebalance.py](execution/rebalance.py) — makes the gate a code-level invariant that future call sites inherit for free, rather than a call-site contract that can be silently skipped. Three existing call-sites (API route, APScheduler, filter_check) retained for early-rejection + layer-specific error translation (403, Ops telemetry, per-account-loop continue). Two new tests in [tests/test_rebalance.py](tests/test_rebalance.py):
- `test_rebalance_against_retired_account_is_blocked` — calls `compute_rebalance` with `broker.account=3`, asserts `ValidationGateError` with "RETIRED" in message.
- `test_rebalance_retired_block_not_bypassable_by_override` — confirms R2 semantics (global + per-account override env vars can't bypass retired status) hold at the `compute_rebalance` layer too.

Eight existing rebalance tests patched with `@patch("execution.rebalance.require_validated")` — mechanical, no behavior change.

**Original finding (retained for context):**

**Files:** `tests/test_validation_gate.py` covers `require_validated(3)` raising; `tests/test_rebalance.py` does not exercise A3-equivalent account.

The rebalance gate is enforced at the broker construction / API-route layer, not inside `compute_rebalance`. A future refactor could bypass the gate without tripping existing tests.

**Fix:** `test_rebalance_against_retired_account_is_blocked()` — construct `AlpacaBroker(account=3)`, call `compute_rebalance`, assert raise.

---

## 5. Operational & Deployment Concerns

### 🟠 O1. `scripts/com.fire.filter-check.plist` hardcodes macOS paths
**Finding:** `/Users/george/.local/bin/uv`, `/Users/george/Desktop/Projects/FIRE`. DEPLOYMENT_PLAN.md scopes Fly.io migration but this plist is macOS-only. The filter_check semantics (4:30 PM ET daily, auto-rebalance on filter flip) need a cloud equivalent, and the migration will require:
1. SystemD unit or Fly cron equivalent
2. `osascript` notifications replaced with Pushover/Slack/email
3. Log collection via a real log aggregator (not `data/filter_check.log`)

None of this is prepared. Deferred is fine — but when the Fly.io migration starts, this is a 1-2 day of work, not 1 hour.

### 🟠 O2. Launchd has no dead-man's-switch
If the filter-check cron fails to run (launchd crash, disk full, env corrupt), the next attempt is 24h later with no alert. On 2026-04-20 the plausibility bug manifested specifically because of a stale-data window — had the filter-check crashed during that window too, no alert would have fired.

**Fix:** a 1-line wrapper: `if mtime(data/filter_check.log) < now - 25h: osascript notify`. Run as a separate hourly launchd entry. ~5 lines of code.

### 🟡 O3. Config drift: `scalar_cap` appears in 4+ places
- `execution/rebalance.py:297` hardcodes `"scalar_cap": 1.0` at the wire site
- `strategies/portfolio.py:apply_vol_scaling` default is 1.0 (post-C4)
- `PORTFOLIOS["trend_lowvol"].vol_scaling_params.scalar_cap` is 1.0
- `PORTFOLIOS["crypto_momentum_filtered"].vol_scaling_params.scalar_cap` is 1.0
- `mode2/` research scripts reportedly use `scalar_cap=2.0` for leverage research (per agent review — not independently verified)

If a future config loads `scalar_cap=1.5` from mode2 research, the wire-site hardcode at `rebalance.py:297` silently overrides it. That's correct defensive behavior for the paper era but hides the fact that the backtest and the PORTFOLIOS config are no longer the source of truth for live behavior.

**Recommendation:** add a startup invariant assertion: *"for every strategy with `vol_scaling=True`, the PORTFOLIOS config's scalar_cap matches `VOL_SCALING_WIRE_CAP` (currently 1.0)"*. Drift at config-load-time is a warning log. Becomes a gate before real money.

### 🟡 O4. No automated "am I actually trading" heartbeat
The system has many ways to silently stop trading: validation gate blocks, catastrophe halt latches, filter check crashes, APScheduler job crashes, launchd not firing. **Each individual failure path logs; there's no consolidated "something I expected to happen today did not happen" alert.**

**Fix:** weekly/daily digest that checks: (a) did filter_check run within 25h, (b) did A4 rebalance in the last 24h (or log "no-op because cash"), (c) does every active account have a validation-state that hasn't expired, (d) has any account latched `halted=True` without manual acknowledgment. Dashboard banner + push notification.

---

## 6. Findings That Didn't Survive Verification

These were surfaced by the adversarial review but don't hold up under direct code inspection:

1. **"Backfill overwrites today's live snapshot with Alpaca EOD."** False. `data/snapshots.py:141` — `if dt in df.index: continue` explicitly skips dates that already have a row. The order of writes matters but there's no silent overwrite.

2. **"Peak=0 path inverts drawdown on recovery from liquidation."** False. `risk_manager.py:92` — `dd = (current_equity - peak) / peak if peak > 0 else 0.0`. Peak=0 short-circuits to dd=0.0 cleanly; `peak = max(0, current_equity)` handles the ramp-from-liquidation case.

3. **"Snapshot read race inflates peak mid-trade."** False as stated. `max()` over append-only snapshots is robust to a concurrent append (see N3 for the actual, narrower issue).

4. **"8-decimal crypto rounding causes 0.5-1% annual slippage."** Arithmetically wrong. 8 decimals is satoshi precision (~$0.0009 per BTC at current prices). Compounds to pennies per year, not percentage points.

These spurious claims are called out to keep the signal-to-noise of this review honest. Adversarial review produces plausible-sounding bugs; verification is load-bearing.

---

## 7. Recommendations (Ranked)

### Before the 2026-05-04 A1+A2 rebalance
- ✅ **N2:** NaN filter guards — closed 2026-04-21 (commit `d1b753b`), 2 regression tests.
- ✅ **N5:** plausibility ERROR log — closed 2026-04-21 (commit `d1b753b`). *(Pulled forward from Month-3 since it shipped in the same commit as N2.)*

### Before BTC crosses the 125d MA (A4 activation)
- ~~**N1:** verify ppy=252 vs ppy=365 parity~~ — **no action needed.** Verification (§3 N1) confirmed both sides use `sqrt(252)`; parity holds. Docstring clarification only.

### Month 3
- ✅ **T4:** retired-account block tested through `compute_rebalance` — closed 2026-04-22. Moved the check into `compute_rebalance` itself (defense-in-depth rather than test-only) + 2 regression tests.
- **T1:** journal-persists-through-execute-failure integration test (~40 lines). Priority 21.
- **N4:** extend rebalance journal with pre-filter/pre-scalar weights. Enables post-mortems (~15 lines).
- **T2:** vol-scaling parity test against real A2 snapshots (gated on fixture presence, ~30 lines).
- **N1:** docstring clarification on A4 vol annualization (1 line).
- **O2:** launchd dead-man's-switch wrapper (~5 lines).
- ⛔ **T3 is explicitly SKIPPED** — pinning the 3.4pp A4 drag couples the test suite to market regime and realized turnover, both of which drift naturally; a test that fires on natural drift is a false-regression factory. Better as a dashboard metric than a test. (Decision rationale via `engineering:tech-debt` skill during Pass 1a planning.)

### Before real-money graduation
- **N3:** snapshot-read lock in `compute_drawdown` (matters on network-mounted volumes).
- **O1:** cloud-portable filter-check (Fly.io or equivalent). ~1-2 days.
- **O3:** config-drift invariant for `scalar_cap`.
- **O4:** consolidated "am I trading" heartbeat.
- **C3:** point-in-time S&P 500 constituents (the one remaining Tier-1 item; week-long project).

---

## 8. Verdict

The Month-2 audit arc is high-quality work. The failure-mode categories it uncovered (cache staleness → S-series, sim/live parity → C-series, TZ-handling → D-series, value-plausibility → S5) are collectively the right taxonomy for "fast-iteration-with-AI" failure modes. The discipline of re-running the full test suite + validation + combined headline after each fix is correct — this is what separates fast iteration from fast regression.

**The project is in a credibly better state than it was on 2026-04-19.** The combined Calmar 4.28 number is worth less than it was before C4 (because the backtest had been overstating it), but the number it reports now is real. The forward-looking 2.5-3.5 haircut in CLAUDE.md is honest. MARGINAL status on A2 is the correct classification for a strategy whose backtest was inflated by unrealizable leverage — naming it MARGINAL preserves the option to run it in paper while refusing to pretend it's PASS-grade.

The 5 new findings + 4 test gaps + 4 operational concerns in this review are a *much smaller set* than the 27-item audit that prompted it. That's not a ceiling claim ("we've found everything"); it's an observation that the yield from additional adversarial review is declining, which is what you'd expect when the foundation is being actively strengthened. **Continued investment should shift from "find more Tier-1 bugs" to "harden the test suite so regressions can't silently reintroduce closed bugs" and "build the operational hygiene that a cloud deploy will require."**

The hard work to get here is visible in the code. The next hard work is less dramatic: durable tests and durable observability so Month-3 can focus on research (new A4-class strategies, Mode 2) rather than rebuilding confidence in Month-2's foundations.
