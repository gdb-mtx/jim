# Project history — resolved fixes and decision deltas

Archive of resolved-and-stable changes that used to live in CLAUDE.md as
"(fixed 2026-04-XX)" stamps and "was X pre-Y" parentheticals. Moved here
because every line in CLAUDE.md is loaded into every session — historical
provenance shouldn't pay that token cost forever.

Look here when:
- A code path mentions "post-CN fix" and you want to know what changed.
- A scorecard number differs from an older note and you want the delta.
- You're auditing a metric and need to know whether a known correction
  has been applied.

The authoritative ranked bug list with full per-item detail lives in
`AUDIT_MONTH2.md`. This file is the digest.

## April 2026 fix pack — Tier 1 (changed reported numbers)

**C1 — Combined-portfolio calendar / ppy convention** (fixed 2026-04-20).
`run_combined_portfolio` migrated from union calendar + fillna(0) + ppy=365
to equity trading calendar with A4 compounded Fri→Mon + ppy=252. Empirical
delta ≤ 0.3pp CAGR / 0.05 Calmar.

**C2 — BTC MA warmup bias** (fixed 2026-04-20). Strict `min_periods=period`
on BTC moving-average warmup. SMA-125/top2 remains the min-Calmar winner
(half A 2.89 / half B 2.94 with strict warmup; half B was 3.10 under the
old min_periods=1 convention).

**C3 — S&P 500 survivorship bias** (NOT fixed). A1 standalone CAGR is ~1-2pp
overstated. Acknowledged caveat; week+ of work to fix; only matters
pre-real-money.

**C4 — Vol-scaling overlay absent from live** (fixed 2026-04-21, option B).
Live vol-scaling wired via `execution/vol_scaling.compute_live_vol_scalar`;
backtest `scalar_cap=1.0` in both live and backtest for sim/live parity.
Effect: A2 dropped PASS → MARGINAL (cap 1.5 → 1.0; the old backtest was
leveraging the low-vol leg up to 1.5× in calm regimes that live could never
realize). A2 CAGR moved 16.9% → 11.0%. A4 remains PASS.

**C5 — Drawdown halt redesigned** (resolved 2026-04-21). Old -15% auto-halt
+ -10% strategy-level breaker were retired: the halt duplicated the
SPY/BTC filters + vol-scaling, systematically exited V-shape recoveries,
and never fired in 16y of IS+OOS data. Replaced with -10% dashboard alert
(banner only, not persisted) + -35% catastrophe halt (only persisted state).
Backtest parity layer: `backtesting/drawdown_halt.py simulate_drawdown_halt`
is a no-op at -35% across all current strategies.

**C6 — Zero fee/slippage in backtest** (fixed 2026-04-21). Per-strategy
transaction costs via `backtesting/costs.apply_transaction_costs`: 5 bps
round-trip equity (slippage only, Alpaca zero-commission), 20 bps round-trip
crypto (bid-ask spread). A4 cost drag came in at ~3.4pp (vs audit's
0.5-1pp estimate) because realized daily turnover on crypto rotation is
~8% / ~20× annualized one-way, not the audit's implied ~2×.

**C7 — `max_position_pct=20%` cap on A4** (fixed 2026-04-21, option C).
Cap removed entirely. Was wired in naming only — three legacy controls
(Fractional Kelly + 2% rule + 20% position cap) all removed.

### Combined OOS deltas across the C4+C6 fix wave

- Equity core (A1+A2 at 50/50): **22.3% CAGR / -7.7% MaxDD / Calmar 2.88 → 19.0% / -6.1% / 3.13** (post C4+C6).
- 3-account live book (A1+A2+A4 at 1/3): **30.3% / -7.0% / 4.31 → 26.5% / -6.2% / 4.28**.
- A4 standalone bootstrap CAGR p5/p50/p95: **+25.1% / +45.9% / +74.8%** (20-day blocks) → **+20.9% / +42.9% / +73.6%** (40-day blocks per R9, captures crypto's longer regime autocorrelation).

Net: cost-adjusted returns are honestly lower; vol-scaling in both sim and
live cut peak CAGR but improved MaxDD; combined Calmar essentially
unchanged (4.31 → 4.28).

## Tier 2 — Safety / concurrency (all fixed)

- **S1 (2026-04-20)**: cross-process lock race. All three rebalance entry
  points (API `/rebalance/execute`, APScheduler A4 job, `filter_check.py`)
  serialize via `dual_rebalance_lock` (async + file lock).
- **S2 (2026-04-20)**: parquet writes are now atomic via `write_parquet_atomic`
  (write to `.tmp`, `os.replace`).
- **S3 (2026-04-20)**: `save_snapshot` read-modify-write race fixed.
- **S4 (2026-04-20)**: `download_prices` retry loop with coverage gate.
- **S5 (2026-04-21)**: yfinance returning wrong data under right ticker
  → `data/plausibility.py` per-ticker bands + write-time assertions +
  read-time cache-vs-live cross-validation. State surfaced via
  `/api/portfolio/plausibility` + red banner in `FilterStatusBanner.tsx`.

## Tier 3 — Data / correctness (all fixed 2026-04-20)

- **D1**: `backfill_from_alpaca` was using naive local timezone; fixed to ET.
- **D2**: `take_snapshot` / `_patch_today` used `date.today()`; replaced
  with `today_et` helper.
- **D3**: `get_sp500_tickers()` never refreshed; now refreshes per cache TTL.
- **D4**: silent 0% on yfinance SPY failure; now raises.

## Tier 4 — Reporting / audit hygiene (partial)

Fixed: R1, R3, R11 (price-staleness flags unfetchable as drifted), R12, R16.
Open: R2, R4-R10, R13-R15. None block paper or real-money operation. See
`AUDIT_MONTH2.md` for per-item detail.

## 2026-04-22 — A4 first-entry cascading bugs (all resolved same session)

When BTC first crossed its 125d MA on 2026-04-22 and A4 entered positions
for the first time, four latent bugs surfaced in cascade. Took 5
preview/execute attempts before clean fills; ~$247 realized slippage.

1. **Concurrent yfinance cross-contamination**. Multiple `yf.download`
   calls during API startup shared a single response payload across
   threads; crypto cache ended up as `[XLE, ^VIX]`, VIX cache got IWM
   values, spy_filter got an extra EFA column. `CryptoMomentum` preview
   returned `{XLE: 0.5}` as a target. Fix: `threading.Lock` around
   `yf.download` in `data/pipeline.py`, returned-column verification
   (reject if returned ≠ requested), cache-read schema checks across
   `download_and_cache` / `download_crypto_prices` / `download_btc_prices`
   / `download_vix`, stricter plausibility bands. SPY floor lowered $50 → $40
   to admit the 2009-03-09 auto-adjusted low ($49.81).

2. **Alpaca rejects `time_in_force="day"` for crypto** — crypto requires
   `gtc` or `ioc`. `execution/rebalance.py` now picks `gtc` for crypto.

3. **Position symbol mismatch**. Alpaca's position API returns `BTCUSD`
   (no slash) but orders/quotes use `BTC/USD`. Rebalance diff treated them
   as different assets and wanted to sell all BTC + rebuy. Fix:
   `normalize_alpaca_position_symbol` in `data/crypto.py`, applied inside
   `get_position_map` + `get_positions`.

4. **Crypto price drift between preview and fill**. ETH moved +2% in
   seconds between preview ($2,396) and submit ($2,445);
   `qty × fill_price > available_cash` → 4 "insufficient balance" rejects.
   Fix: notional (dollar-amount) orders for crypto buys via
   `OrderRequest.notional`. `compute_rebalance` caps total crypto-buy
   notional to 99.9% of live cash and scales proportionally; sells still
   use `qty`. Equity orders unchanged.

Same-session dashboard polish: post-execute auto-refresh of
summary/positions, error/warning toasts 20s (info 10s), rebalance
result card persists with explicit "New Preview" reset button.

## 2026-04-27 — Empty-cache write+read protection

yfinance with no internet returned column-correct, row-empty DataFrames,
slipping past the existing coverage gate and overwriting four healthy
caches (etf_prices, spy_filter, vix, btc_prices) with header-only files.
Fix: `download_with_retry` raises on 0-row downloads (write-side guard,
single chokepoint); each of the five cache loaders treats `len(cached) == 0`
as invalid and falls through to re-download (read-side guard, inlined
consistently rather than abstracted into a shared helper).

## 2026-04-20 — Strategy-discovery framework

Walk-forward REFIT (Test 6, non-gating) added to validation pipeline.
Per-window grid search on adapter-defined `refit_param_grid`; PASS if
defaults within 10% of refit or better, REVIEW only if refit stably beats
defaults by >20%. A1 + A2 currently PASS — literature defaults are not
demonstrably suboptimal. Replaces the old practice of lifting 15-year-old
academic parameters wholesale.

## 2026-04-20 — Stock-universe coverage gate

Was previously "≥80% of all days since 2010," which locked out every
post-2013 IPO / recent S&P addition. Replaced with **trailing 500 trading
days ≥80% non-NaN** so recent adds (VRT, LITE) can enter once they have
~2y of history, without corrupting backtests (pre-IPO NaN rows propagate
to NaN ranks → excluded from selection for periods before the ticker
existed).

## 2026-04-23 — `strategies/portfolio.py` split

Per DEPLOYMENT_PLAN.md §Phase 0: split into `portfolio_config.py`
(LIVE surface — PORTFOLIOS dict + factory maps + filter computation,
zero imports from backtesting/ or mode2/) + `portfolio_backtest.py`
(RESEARCH surface — backtest runners + vol-scaling math). Original
`portfolio.py` is a re-export shim preserving import paths.
`api/research/backtests.py` and `api/research/strategies.py` moved out
of `api/routes/` for the same reason — they import from `backtesting/`
and won't ship to Fly.

## 2026-04-21 — Sharpe deemphasis

Prior framework gated on OOS Sharpe ≥ 1.0; this is the wrong objective
function for a 3-5 year wealth compounder (Sharpe penalizes upside vol
and normalizes absolute return magnitude). Sharpe still shown on reports
as informational context but not gated. Primary gates are CAGR + MaxDD
+ Calmar. See `VALIDATION_PLAN.md`.
