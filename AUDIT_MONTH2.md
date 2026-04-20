# Month-2 Audit — Findings & Fix Plan

**Date opened:** 2026-04-20
**Context:** Mid-session we discovered (a) data caches had no staleness check → 41 days frozen, (b) `download_sp500_prices` silently wrote a 91/451 truncated cache after its batch-download recovery path swallowed errors. Spawned three adversarial reviewers to see what else we'd missed. This doc consolidates their findings, ranks them, and is the pick-up point for the next session.

**TL;DR —** the foundation is sound (signal lagging, vol-scaling shifts, bootstrap resampling, gates, circuit-breaker persistence are all correct). The bugs cluster where pieces are **composed**: calendar handling, cross-process concurrency, cache atomicity, MA warmup. These are the fast-iteration-with-AI failure mode.

---

## Already fixed today (don't redo)

- **BTC + crypto + SP500 + VIX caches now have TTL** (16h BTC/crypto/VIX, 24h SP500). Previously frozen since Mar 10 setup.
- **`download_sp500_prices` hardened** — batches retry 3× with exp backoff, raises on failure instead of writing a partial cache. Threshold is >=50% within-batch (can still trim; see L1 below).
- **`/filters` endpoint** uses 125d MA (was still computing 150d) and returns `ma_125` key.
- **`filter_state.json`** stale keys (btc_ma150, btc_ma200) removed.
- **Win rate / profit factor / Kelly** now exclude zero-return days; crypto's 31.6% → 54.4% true win rate, Kelly 0 → 0.21.
- **Data freshness pill** live on dashboard with 5-min refresh, hover shows per-cache age.
- **A3 retired** — liquidated 53 positions (cash $99,826.89), ACCOUNT_INFO status="retired", strategy=None, hidden from live views.
- **`combined_3account` dashboard strategy** now represents A1+A2+A4 @ 1/3 each on a union calendar (but see C1 below — the math is biased).
- **`active_accounts()` helper** centralizes retired-account filtering.

---

## Tier 1 — Changes reported numbers (fix before trusting headline metrics)

### 🔴 C1. `run_combined_portfolio` weekend-zero bias inflates the combined-book CAGR/Calmar
**File:** `strategies/portfolio.py:399-401`
**Finding:** On crypto weekends A1 and A2 have no observation; `fillna(0.0)` then `df.mean(axis=1)` treats them as zero returns, so realized weights drift from advertised 33/33/33 toward ~23/23/54 over a year. Crypto's contribution is overstated.
**Impact:** Every "3-acct + A4 at W%" row in DECISIONS_RESOLVED.md is biased high. The "drop-A3 + 33% A4: Calmar 3.79 / CAGR 28.5%" decision was made on biased numbers. Decision likely still directionally right, but margin of dominance over 25% is smaller than claimed.
**Fix:** forward-fill equity legs across crypto-only days before averaging (equity positions are held, not zero'd). Re-run the weight-sweep table afterward.

### 🔴 C2. Test-3 / robust-opt BTC MA warmup is biased — SMA-125 half-A Calmar 2.89 is flattered
**Files:** `strategies/crypto_momentum.py:89`, `scripts/crypto_robust_opt.py:112`, `scripts/run_validation.py:295`
**Finding:** `rolling(125, min_periods=1)` on BTC price produces an expanding-mean during the first 125 days of each half. In half A (2020-01 onward), this means the filter is effectively "on" through the COVID crash when a true 125d warmup would have flipped it off sooner. Robust-opt's 144-config ranking is partly driven by which configs benefit most from this artifact.
**Impact:** The "SMA-125/top2 wins min-Calmar" claim may not survive a clean recompute. Half-A production Calmar 2.89 is the primary gate for Test 3 — real value is unknown.
**Fix:** pass full BTC history to the filter (compute MA over full range) and slice returns afterward; change `min_periods=1` → `min_periods=125` for production; rerun robust-opt ranking.

### 🟠 C3. S&P 500 survivorship bias (known, re-emphasized)
**File:** `data/sp500.py:41-55`, `strategies/stock_momentum.py:123`
**Finding:** We pull the current Wikipedia constituent list and backtest 2010+ using that snapshot. "Top 15 of 451" in 2010 is picking from a forward-biased universe. Expected CAGR overstatement **~1-2pp** on A1 and the SM leg of A3.
**Fix:** Either acknowledge explicitly (add disclaimer to all A1 CAGR claims) or source point-in-time constituents (e.g., Kenneth French / CRSP). The latter is a week+ of work.

---

## Tier 2 — Safety / concurrency

### 🔴 S1. Cross-process lock race — duplicate orders are possible
**Files:** `api/locks.py:19-45`, `api/routes/orders.py:130-150`, `scripts/filter_check.py:141`, `api/main.py:46-51`
**Finding:** The API rebalance endpoint takes only `asyncio.Lock` (in-process). `filter_check.py` (cron) takes only `file_rebalance_lock` (cross-process via fcntl). APScheduler's daily A4 job takes only the asyncio lock. These three locks don't observe each other — two processes can simultaneously enter `compute_rebalance` / `execute_rebalance` for the same account, double-submitting orders.
**Impact:** On paper it's noise; on real money it's duplicate fills. This is the single most important concurrency fix.
**Fix:** API endpoint AND APScheduler must acquire both locks (asyncio first, then file lock inside `asyncio.to_thread`).

### 🟠 S2. Parquet writes are not atomic
**Files:** `data/sp500.py:161`, `data/crypto.py:100,140`, `data/pipeline.py:82`, `data/snapshots.py:63,141`
**Finding:** `df.to_parquet(path)` truncates then streams. A crash, Ctrl-C, or OOM mid-write leaves a zero/partial file. Next read either raises or silently returns wrong data (same shape as the 91-ticker corruption we just fixed, via a different path).
**Fix:** Write to `path.tmp`, `os.replace(path.tmp, path)`. The filter-state file already uses this pattern — copy it everywhere.

### 🟠 S3. `save_snapshot` read-modify-write has no lock
**File:** `data/snapshots.py:50-63`
**Finding:** Loads the whole parquet, appends one row, rewrites. Filter-monitor + manual rebalance + dashboard `/snapshot` can race on the same account. Two writers → silently lost rows.
**Fix:** lockfile around save, or switch to append-only JSONL.

### 🟠 S4. `download_prices` has no retry and is used in the live rebalance path
**Files:** `data/pipeline.py:15-41`, `execution/rebalance.py:116,162`
**Finding:** Single-shot yfinance call with no retry. The same rate-limit/partial-batch hiccup that caused the 91-ticker SP500 corruption can return partial data during a live rebalance → wrong target weights → wrong orders.
**Fix:** factor the retry helper out of `download_sp500_prices` and wrap `download_prices` with it.

---

## Tier 3 — Data / correctness

### 🟠 D1. `backfill_from_alpaca` uses naive local timezone
**File:** `data/snapshots.py:121`
**Finding:** `datetime.fromtimestamp(ts)` interprets Unix seconds in machine-local time; Alpaca sends UTC midnight → mis-dates backfilled snapshot rows by 1 day in ET. May be contributing to some correlation-matrix noise.
**Fix:** `datetime.fromtimestamp(ts, tz=timezone.utc).date()` or an explicit ET trading-date helper.

### 🟠 D2. `take_snapshot` uses `date.today()` (local)
**File:** `data/snapshots.py:73`
**Finding:** Runs fine on the current Mac at 4:30 PM ET. Would break if the server ever runs in UTC (cloud move) — after 8 PM ET `date.today()` flips to tomorrow, creating phantom rows and missing today. Also means backfilled rows (D1) can disagree with live rows by a day.
**Fix:** explicit ET trading-date helper.

### 🟠 D3. `get_sp500_tickers()` never refreshes
**File:** `data/sp500.py:32-55`
**Finding:** Wikipedia list is pulled once and cached forever; S&P 500 changes ~4x/year. Delisted tickers silently drop out of the 80% coverage filter, hiding the rot. Compounds C3 survivorship bias.
**Fix:** 7-day TTL on the ticker list with fallback to cached list if Wikipedia is unreachable.

### 🟡 D4. `get_performance_summary` / `get_spy_benchmark` silently return 0% on yfinance failure
**Files:** `data/snapshots.py:218-219, 253-254`
**Finding:** Bare `except Exception: return []` / `spy = pd.Series(dtype=float)`. UI shows 0% SPY, 0% alpha → "we're beating the market" when really we just failed to fetch SPY.
**Fix:** log + structured "unavailable" response the frontend renders as "—".

---

## Tier 4 — Reporting / audit hygiene

| ID | File | Finding | Severity |
|---|---|---|---|
| R1 | `backtesting/account_adapters.py:100` | A2's walk-forward is unsupported — its "PASS" rests on single holdout split, not true walk-forward | Medium |
| R2 | `execution/validation_gate.py:64` | `FIRE_VALIDATION_OVERRIDE=1` is global — could accidentally unblock retired A3. Should reject `retired` unconditionally. | Medium |
| R3 | `execution/rebalance.py:260` | Strategy-level circuit breakers (-10%/strategy) are dead code — never wired to the live path | Medium |
| R4 | `api/routes/orders.py:204-222` | Journal entries lost if execute raises mid-flight. Wrap in try/finally. | Low |
| R5 | `api/routes/portfolio.py:289-307` | `reset_circuit_breaker` has no audit trail entry | Low |
| R6 | `backtesting/metrics.py:447-452` | `marginal_portfolio_contribution` correlation uses native overlap; CAGR uses union+fillna — different samples | Medium |
| R7 | `backtesting/metrics.py:260` | Sterling ratio groups by `.index.year` → partial start-year inflates the mean | Low |
| R8 | `scripts/run_validation.py:71` | OOS/IS CAGR ratio threshold 70% gameable by moving TRAIN_END | Medium |
| R9 | `backtesting/bootstrap.py:21` | 20d block size may be too short for crypto regime autocorrelation; p5 CAGR overstated | Medium |
| R10 | `execution/alpaca_broker.py:35-38` | `is_non_tradeable` regex matches "CVR" anywhere in symbol — future small-cap expansion could break | Low |
| R11 | `execution/rebalance.py:422` | `check_price_staleness` silently skips symbols with unfetchable new price — should treat as drift | Medium |

---

## Verified clean (reviewers explicitly checked)

- Signal lagging in `strategies/base.py:45` — strategies shift signals by 1 day before multiplying with returns. No forward-looking trades.
- Momentum `shift(skip_recent)` vs `shift(lookback)` in `stock_momentum.py` and `momentum.py` — correct signs, no current-day leak.
- `apply_vol_scaling` uses `.shift(1).fillna(1.0)` — yesterday's vol sizes today's position. Correct.
- Bootstrap resampling preserves variance correctly (`backtesting/bootstrap.py:57-63`).
- `run_equity_core` uses inner-join on A1+A2 — no union-inflation (unlike `run_combined_portfolio`).
- `_require_active` correctly gates rebalance preview + execute.
- Circuit-breaker state persistence uses atomic rename — good.
- Fractional crypto rounding matches Alpaca 8-decimal minimum.
- Symbol conversion BTC-USD ↔ BTC/USD is consistent across all paths.
- Alpaca non-tradeable detection (delisted, all-prices-None fallback) is correct.

---

## Recommended next-session plan

**Session 1 — Kill the bias (Tier 1):**
1. Fix C1 (weekend-zero). Re-run the weight-sweep table in `/tmp/decisions_audit2.py`. Confirm drop-A3 + 33% A4 is still the right call with unbiased numbers.
2. Fix C2 (BTC MA warmup). Re-run `scripts/crypto_robust_opt.py` with proper 125d warmup + full BTC history passed to filter. Verify SMA-125/top2 is still the winner. If a different config wins by a material margin, update A4 production config.
3. Update CLAUDE.md headline table with the corrected combined numbers.

**Session 2 — Concurrency safety (Tier 2):**
4. S1: Make API `/rebalance/execute` and APScheduler A4 job acquire both asyncio + file locks. Required before any real-money graduation.
5. S2 + S3: Atomic parquet writes; snapshot write locking.
6. S4: Wrap `download_prices` with retry helper (share with `download_sp500_prices`).

**Session 3 — Clock / data correctness (Tier 3):**
7. D1 + D2: UTC-aware timestamp handling + explicit ET trading-date helper.
8. D3: SP500 tickers TTL.
9. D4: Surface yfinance failures to the UI rather than hiding them as 0%.

**Session 4 — Reporting hygiene (Tier 4):**
10. R1: Relabel A2 validation as "holdout only" until walk-forward is implemented.
11. R2: Per-account validation override + never-overridable "retired".
12. R3: Wire strategy-level breakers or delete the claim from docs.
13. R4: try/finally around execute + journal.
14. R6: Align correlation sample to blended CAGR sample in portfolio_fit.
15. R8, R9, R11: Medium-value fixes; pick up as time permits.

**Long-term (Tier 3+ / research):**
- C3 survivorship bias: evaluate point-in-time SP500 constituents (CRSP / Kenneth French data). Week-long project; only worth doing before real-money graduation.
- Add dashboard validation-status banner per account (already on the CLAUDE.md next-steps list).

---

## Known numeric caveats to carry forward

Until Tier 1 is fixed, assume the following headline numbers are directionally right but specifically off:

- **Combined "3-acct + A4 @ W%"** CAGR and Calmar in DECISIONS_RESOLVED.md and CLAUDE.md are inflated by C1 (weekend-zero).
- **A4 half-A production Calmar 2.89** (the Test 3 pass-gate) is flattered by C2 (warmup bias).
- **A1 OOS CAGR 20.9%** is ~1-2pp overstated by C3 (survivorship).
- **Live 29-day A1-A3 correlation 0.84** was a real number, but A2-A4/A1-A4 live correlations over the Mar 10 → Apr 17 window reflect stale-data artifacts for the equity side — don't cite them as independent validations.

The **retired/kept/weight decisions themselves** (A3 retired, A4 at 33%) stand on backtest evidence that the Tier 1 bugs don't reverse — just reduce the margin of dominance. No decision is currently expected to flip once the fixes land, but **re-verify** before acting on them.

---

## References

- `MEMORY.md` (auto-memory) — session-level feedback patterns
- `CLAUDE.md` — current system state (updated 2026-04-20 with audit caveats)
- `DECISIONS_RESOLVED.md` — A3 retirement + A4 @ 33% weight decisions + full context
- Git log 2026-04-18 → 2026-04-20 — the month-2 changes that introduced most of the Tier 2 bugs
