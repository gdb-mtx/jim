# Month-2 Audit — Findings & Fix Plan

**Date opened:** 2026-04-20
**Context:** Mid-session we discovered (a) data caches had no staleness check → 41 days frozen, (b) `download_sp500_prices` silently wrote a 91/451 truncated cache after its batch-download recovery path swallowed errors. Spawned three adversarial reviewers to see what else we'd missed. This doc consolidates their findings, ranks them, and is the pick-up point for the next session.

**TL;DR —** the foundation is sound (signal lagging, vol-scaling shifts, bootstrap resampling, gates, circuit-breaker persistence are all correct). The bugs cluster where pieces are **composed**: calendar handling, cross-process concurrency, cache atomicity, MA warmup. These are the fast-iteration-with-AI failure mode.

**Status 2026-04-20:** Tier 1 C1 + C2 fixed; C1 empirically non-material (<0.3pp CAGR), C2 does not flip the SMA-125/top2 production config. C3 disclosure in place. **Tier 2 S1-S4 all fixed 2026-04-20** — cross-process lock unified, parquet writes atomic, snapshot RMW locked, yfinance retry helper shared across every live-path downloader. Real-money-graduation blocker lifted. **Tier 3 D1-D4 all fixed 2026-04-20** — ET trading-date helper (`data/trading_dates.py`), backfill/snapshot TZ-stable, SP500 ticker list on 7-day TTL (discovered the cached list was 998h old → refresh pulled 451→503 tickers, confirming 52 silently-dropped delistings), SPY fetch failures now render "—" instead of misleading 0%. Tier 4 remains open.

**Follow-up 2026-04-20 (beyond audit scope):** While validating the D3 refresh, noticed the 80%-since-2010 coverage gate was locking every post-2013 S&P addition out of the live universe. Changed to trailing-500d window ≥80% (`data/sp500.py`), exposing a latent bug in `strategies/stock_momentum.py` where `n_stocks = prices.shape[1]` included NaN columns → selection cutoff exceeded the actual max rank → zero picks on partial-history slices. Switched to NaN-safe descending-rank + `<= top_n`. Net effect: live universe 451 → 501 tickers; A1 OOS CAGR 20.9% → 27.3%, Calmar 1.89 → 2.77 (VRT, LITE now eligible); A2 essentially unchanged (16.9% vs 17.4%); combined 3-acct 28.3% → 30.3% CAGR, Calmar 3.75 → 4.31. A1/A2 both still PASS validation gate.

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

### ✅ C1. `run_combined_portfolio` weekend-zero bias — FIXED 2026-04-20 (non-material)
**File:** `strategies/portfolio.py:399-401`
**Finding:** On crypto weekends A1 and A2 have no observation; `fillna(0.0)` then `df.mean(axis=1)` treats them as zero returns, so realized weights drift from advertised 33/33/33 toward ~23/23/54 over a year. Crypto's contribution is overstated.
**Impact (predicted):** Every "3-acct + A4 at W%" row biased high; "drop-A3 + 33% A4: Calmar 3.79 / CAGR 28.5%" decision on biased numbers.
**Fix applied:** `run_combined_portfolio` migrated to equity trading calendar with A4 compounded Fri→Mon (ppy=252). `marginal_portfolio_contribution` follows the same convention. Callers in `api/routes/strategies.py`, `api/routes/backtests.py`, `scripts/run_validation.py` updated to ppy=252.
**Empirical result:** predicted bias **did not materialize**. Old vs new: CAGR +28.09%/-7.56%/3.71 → +28.33%/-7.56%/3.75 (Δ ≤ 0.3pp CAGR, ≤ 0.05 Calmar). Total cumulative return preserved within 0.15pp (126.15% → 126.30%). `mean(axis=1)` with fillna(0) implicitly rebalances daily to 1/3 and the weekend-compound math is near-algebraically equivalent for small daily returns. Code migrated anyway for cleaner semantics. Corrected weight-sweep still dominates 25% (33% Calmar 3.76 vs 25% Calmar 3.50), with 40% at 3.94 — ladder direction intact.

### ✅ C2. BTC MA warmup bias — FIXED 2026-04-20
**Files:** `strategies/crypto_momentum.py:89`, `mode2/crypto_autoresearch.py:92/96/100/101`, `api/routes/portfolio.py:350`
**Finding:** `rolling(125, min_periods=1)` on BTC price produces an expanding-mean during the first 125 days of each half. Robust-opt's 144-config ranking was partly driven by which configs benefit most from this artifact.
**Fix applied:** all 5 call sites changed to strict `min_periods=<period>`. `_get_btc_trend_scalar` and `run_config` refactored to compute MA on full BTC history **before** reindexing to strategy/slice dates — so half-split harnesses (robust-opt, validation) now use pre-slice BTC for warmup.
**Result:** SMA-125/top2 **still wins** min-Calmar ranking. Half A Calmar 2.89 unchanged (audit's "flattered" prediction did not materialize — the prod runtime always had full BTC history). Half B shifted 3.10 → 2.94 under strict warmup. A4 validation still PASS: CAGR +45.2%, MaxDD -11.4%, Calmar 3.98, ratio 85%; bootstrap p5 CAGR +24.8%. No production config change required.

### 🟠 C3. S&P 500 survivorship bias (known, re-emphasized)
**File:** `data/sp500.py:41-55`, `strategies/stock_momentum.py:123`
**Finding:** We pull the current Wikipedia constituent list and backtest 2010+ using that snapshot. "Top 15 of 451" in 2010 is picking from a forward-biased universe. Expected CAGR overstatement **~1-2pp** on A1 and the SM leg of A3.
**Fix:** Either acknowledge explicitly (add disclaimer to all A1 CAGR claims) or source point-in-time constituents (e.g., Kenneth French / CRSP). The latter is a week+ of work.

---

## Tier 2 — Safety / concurrency

### ✅ S1. Cross-process lock race — FIXED 2026-04-20
**Files:** `api/locks.py`, `api/routes/orders.py:125-146`, `api/main.py:36-108`, `scripts/filter_check.py:141` (unchanged)
**Finding:** The API rebalance endpoint took only `asyncio.Lock` (in-process). `filter_check.py` (cron) took only `file_rebalance_lock` (cross-process via fcntl). APScheduler's daily A4 job took only the asyncio lock. These three locks didn't observe each other — two processes could simultaneously enter `compute_rebalance` / `execute_rebalance` for the same account, double-submitting orders.
**Fix applied:** new `dual_rebalance_lock(account)` async context manager in `api/locks.py` takes the async lock in-process, then acquires the file lock inside `asyncio.to_thread`. Both the API execute endpoint and the APScheduler A4 job use it. Contention raises `RebalanceLockedError` (subclass of OSError) → 409 from the API, "skipped" log from the scheduler. `filter_check.py` unchanged — its existing `file_rebalance_lock` call now serializes against the server paths.
**Verified:** bidirectional end-to-end — (A) external process holds file lock → API endpoint returns `409 {"detail":"rebalance already in progress (another process) for account 4"}`; (B) in-process holds file lock → `filter_check.rebalance_account(4)` returns `status="locked"` and logs `"locked by another process — skipping"`; (C) happy path confirmed via dashboard A4 rebalance execute — "Portfolio already at target, no trades needed."

### ✅ S2. Parquet writes are not atomic — FIXED 2026-04-20
**Files:** `data/pipeline.py` (helper), `data/sp500.py`, `data/crypto.py:100,140`, `data/snapshots.py:66,146`
**Finding:** `df.to_parquet(path)` truncates then streams. A crash, Ctrl-C, or OOM mid-write left a zero/partial file — same shape as the 91/451 corruption, via a different path.
**Fix applied:** new `write_parquet_atomic(df, path)` in `data/pipeline.py` writes to `path + .tmp` then `os.replace`. Applied to 7 live-path sites: ETF cache, SP500, crypto universe, BTC, VIX, snapshot save, snapshot backfill. Research-only scripts (`mode2/`, `scripts/crypto_robust_opt.py`) not migrated — no live-path exposure.
**Verified:** smoke test confirmed target file preserved when `.tmp` exists but swap never happened.

### ✅ S3. `save_snapshot` read-modify-write race — FIXED 2026-04-20
**File:** `data/snapshots.py:42-71, 106-144`
**Finding:** `save_snapshot` loaded parquet, appended one row, rewrote. Filter-monitor + manual rebalance + dashboard `/snapshot` could race on the same account → silently lost rows.
**Fix applied:** new `file_snapshot_lock(account, timeout=10)` in `api/locks.py` (blocking fcntl with timeout — snapshot writers are legitimate, just need serialization). `save_snapshot` and `backfill_from_alpaca` acquire it internally, so all callers are safe by default. Both functions also now use `write_parquet_atomic`.
**Verified:** 5 concurrent threads writing different dates for the same account — all 5 rows persisted.

### ✅ S4. `download_prices` has no retry — FIXED 2026-04-20
**Files:** `data/pipeline.py` (helper), `data/sp500.py`, `data/crypto.py`
**Finding:** Single-shot yfinance call with no retry, used in the live rebalance path at `execution/rebalance.py:116,162`. Same rate-limit/partial-batch hiccup that caused the 91/451 SP500 corruption could return partial data during a live rebalance → wrong target weights → wrong orders.
**Fix applied:** new `download_with_retry(symbols, start, ..., max_retries=3, min_coverage_ratio=0.5)` in `data/pipeline.py`. 3× exponential backoff (2s/4s/8s), ≥coverage-ratio guard, raises on persistent failure. `download_prices`, `download_sp500_prices` (batch body), `download_crypto_prices`, `download_btc_prices`, and `download_vix` all now go through it. Single retry path for every live-path yfinance call.
**Verified:** monkey-patched transient failure → recovered on attempt 2; monkey-patched persistent failure → raised after 2 attempts (no partial data returned).

---

## Tier 3 — Data / correctness

### ✅ D1. `backfill_from_alpaca` uses naive local timezone — FIXED 2026-04-20
**Files:** `data/snapshots.py:135`, `data/trading_dates.py` (new)
**Finding:** `datetime.fromtimestamp(ts)` interprets Unix seconds in machine-local time; Alpaca sends UTC midnight → mis-dates backfilled snapshot rows by 1 day in ET.
**Fix applied:** new `data/trading_dates.py` with `utc_ts_to_et_date(ts)` (UTC→ET conversion via `zoneinfo`). `backfill_from_alpaca` uses it. Deterministic across server timezones; `TZ=UTC uv run` verified.
**Verified:** existing snapshots on ET Mac were correctly dated (latent bug, only manifested on UTC servers). New helper bucket-tests confirm round-trip UTC-midnight → correct ET trading day.

### ✅ D2. `take_snapshot` / `_patch_today` use `date.today()` (local) — FIXED 2026-04-20
**Files:** `data/snapshots.py:83`, `api/routes/portfolio.py:165-167`, `data/trading_dates.py` (new)
**Finding:** `date.today()` returns machine-local date. On a UTC server after 8 PM ET, it flips to tomorrow — phantom rows + missed days. Also disagrees with D1-mis-dated backfill rows by a day.
**Fix applied:** both call sites now use `today_et()` from `data/trading_dates.py`. `TZ=UTC` shell returns correct ET date.

### ✅ D3. `get_sp500_tickers()` never refreshes — FIXED 2026-04-20
**File:** `data/sp500.py:24-55`
**Finding:** Wikipedia list pulled once and cached forever; S&P 500 changes ~4x/year. Delisted tickers silently drop through the 80% coverage filter.
**Fix applied:** 7-day TTL via `stat().st_mtime` (matches the existing `download_sp500_prices` / `download_crypto_prices` pattern). Atomic `.tmp` + `replace` on cache write. On Wikipedia fetch failure, falls back to stale cached JSON with a warning log rather than breaking the download pipeline.
**Verified:** stale cache on disk was 998.3h old (41 days) — refresh pulled **451 → 503 tickers**, confirming 52 delisted/added names were silently stale. Fallback verified by monkey-patching `requests.get` to raise.

### ✅ D4. Silent 0% on yfinance SPY failure — FIXED 2026-04-20
**File:** `data/snapshots.py:207-236` (`get_spy_benchmark`), `236-340` (`get_performance_summary`), `dashboard/src/types.ts:86-92`, `dashboard/src/components/EquityHistoryChart.tsx:439-461`
**Finding:** Bare `except Exception: return []` / `spy = pd.Series(...)` masked fetch failures. UI rendered "0.00% SPY, +X% alpha" → looked like beating the market when we'd actually failed to fetch SPY.
**Fix applied:** module logger warns on fetch failure. `spy_return_pct` / `alpha_pct` become `None` (null) when SPY is unavailable (distinct from "new account with <2 rows" which still returns 0.0). `PerformanceEntry` types updated to `number | null`; the table renders "—" in neutral gray for null cells. `return_pct` remains real regardless of SPY state.
**Verified:** monkey-patched yfinance → backend logs warning, all rows have `spy_return_pct=None, alpha_pct=None`, `return_pct` intact. Happy path unchanged (real numbers, real colors).

---

## Tier 4 — Reporting / audit hygiene

| ID | File | Finding | Severity |
|---|---|---|---|
| R1 | `backtesting/account_adapters.py:100`, `scripts/run_validation.py:160` | ~~A2's walk-forward is unsupported~~ — larger issue: the validation's Test 2 was labeled `walk_forward_refit` but never refit parameters. None of A1/A2/A3/A4 did true walk-forward optimization. Fixed 2026-04-20: label renamed to `rolling_oos_fixed_params`, adapter docstrings corrected, new `walk_forward_refit_analysis` + standalone refit scripts added. Refit run on A1 + A2 confirmed literature defaults are within noise of refit winners — no parameter changes, but the documentation now matches reality. | ~~Medium~~ Resolved |
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

**Session 2 — Concurrency safety (Tier 2):** ✅ COMPLETE 2026-04-20
4. ✅ S1: `dual_rebalance_lock` in `api/locks.py`; API endpoint + APScheduler use it; `filter_check.py` unchanged. A/B/C verified.
5. ✅ S2 + S3: `write_parquet_atomic` helper + `file_snapshot_lock` (blocking, internal to `save_snapshot`/`backfill_from_alpaca`).
6. ✅ S4: `download_with_retry` helper; shared across `download_prices`, SP500 batch loop, crypto, BTC, VIX.

**Session 3 — Clock / data correctness (Tier 3):** ✅ COMPLETE 2026-04-20
7. ✅ D1 + D2: `data/trading_dates.py` helper (`today_et`, `utc_ts_to_et_date`); `backfill_from_alpaca`, `take_snapshot`, `_patch_today` all use it. TZ-stable.
8. ✅ D3: 7-day TTL + stale-cache fallback in `get_sp500_tickers`. Refresh pulled 451→503 tickers.
9. ✅ D4: logger + nullable `spy_return_pct` / `alpha_pct`; dashboard renders "—" for unavailable SPY data.

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

**Post-C1/C2 fix status (2026-04-20):**

- **C1 weekend-zero** — FIXED, non-material. Combined 3-acct @ 1/3: +28.3% / -7.6% / 3.75 (was +28.5% / -7.5% / 3.79, Δ within 0.3pp).
- **C2 BTC MA warmup** — FIXED. SMA-125/top2 still wins min-Calmar ranking (half A 2.89 unchanged, half B 3.10→2.94). No production config change.
- **C3 S&P 500 survivorship** — acknowledged; A1 OOS CAGR 20.9% is ~1-2pp overstated. Point-in-time constituents sourcing deferred to pre-real-money track.
- **Live 29-day A1-A3 correlation 0.84** was a real number, but A2-A4/A1-A4 live correlations over the Mar 10 → Apr 17 window reflect stale-data artifacts for the equity side — don't cite them as independent validations.

The **retired/kept/weight decisions themselves** (A3 retired, A4 at 33%) stood on the Tier 1 predictions; post-fix numbers **confirm** they remain the right calls (corrected weight-sweep: 33% → Calmar 3.76, 25% → 3.50, 40% → 3.94). Ladder to 40% direction intact.

---

## References

- `MEMORY.md` (auto-memory) — session-level feedback patterns
- `CLAUDE.md` — current system state (updated 2026-04-20 with audit caveats)
- `DECISIONS_RESOLVED.md` — A3 retirement + A4 @ 33% weight decisions + full context
- Git log 2026-04-18 → 2026-04-20 — the month-2 changes that introduced most of the Tier 2 bugs
