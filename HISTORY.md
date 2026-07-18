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

**C-numbering convention.** Items prefixed `C1`, `C2`, ... `C9`, `C10`,
etc. are this file's stable identifiers for Tier 1 issues — the ones
that changed reported numbers or are open caveats on them. Other docs
(`CLAUDE.md`, `HANDOFF_*.md`, commit messages) reference these labels
without re-explaining; the canonical per-item description lives below.
Numbering is chronological by discovery, not by topic. Gaps are real
(e.g. C8 was never assigned). Tier 2 items use `S` prefix (S1, S2, ...),
Tier 3 use `D`, Tier 4 use `R` — same convention, different sections.

Full per-item history (with all the discovery context, Slack-style status
threads, and follow-up sessions) lives in `docs/archive/AUDIT_MONTH2.md` —
time-capsule, kept for forensic reference. HISTORY.md is the digest.

## April 2026 fix pack — Tier 1 (changed reported numbers)

**C1 — Combined-portfolio calendar / ppy convention** (fixed 2026-04-20).
`run_combined_portfolio` migrated from union calendar + fillna(0) + ppy=365
to equity trading calendar with A4 compounded Fri→Mon + ppy=252. Empirical
delta ≤ 0.3pp CAGR / 0.05 Calmar.

**C2 — BTC MA warmup bias** (fixed 2026-04-20). BTC and SPY MA warmup is
strict (`min_periods=window`) at every live and research site. SMA-125/top2
remains the min-Calmar winner (half A 2.89 / half B 2.94 under strict warmup;
half B was 3.10 under the old min_periods=1 convention).

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

**C9 — Partial-bar signal contamination (crypto)** (fixed 2026-05-06). Surfaced
during the live↔backtest reconciliation triggered by a -7.3 pp gap on A4 over
14 days of paper trading. The strategy's `generate_signals` was reading
yfinance's "today" bar at fire time — but yfinance daily crypto bars are
dated by UTC-midnight start, and when queried mid-day the latest bar is
*partial* (its "close" is the current scratch price, not a settled day-close,
and it mutates with intraday price action). Because backtest historically
runs against already-closed bars, the live signal was systematically
different from what backtest computed for the same notional date. The same
strategy could rank coins differently at 06:05 UTC vs 23:55 UTC even with no
real change in market structure, just because the partial bar absorbed an
Asian-session move. Fix: drop the partial today-bar in `generate_signals`
before computing momentum, so `pct_change(lookback).iloc[-1]` uses
yesterday's settled close — backtest semantics. Combined with the new 8:05
PM EDT launchd schedule (= 00:05 UTC during EDT, see `AUTOMATION.md`), the
strategy now fires 5 minutes after a UTC bar closes using yesterday's just-
minted settled close as the latest data point. The lesson: "yfinance returns
a row, therefore it's a closed bar" was an unstated assumption never tested.
Should have caught this when the live↔backtest pairs first started
diverging in late April; instead it took a 14-day reconciliation to surface.

**C10 — yfinance settled-bar publishing delay** (resolved 2026-05-06).
Adjacent issue surfaced while diagnosing C9. yfinance does NOT publish a
settled crypto daily bar at exactly UTC midnight — there's a 1-12 hour delay
between bar close and the settled value being available in the API response.
At our 8:05 PM EDT (= 00:05 UTC) fire time, yesterday's settled bar was
typically NOT yet visible, so the strategy was forced to use two-days-ago's
close as "latest" — one extra day of staleness vs. backtest. Resolved
structurally by switching live signal computation off yfinance and onto
Alpaca's `/v1beta3/crypto/us/bars` endpoint (broker-native, produced from
Alpaca's own trade tape; yesterday's bar settles within seconds of UTC
midnight, not hours). New module `data/alpaca_crypto_bars.py`; live call
sites swapped in `execution/rebalance.py`, `strategies/portfolio_config.py`
(`compute_btc_trend_filter`), `scripts/filter_check.py`, and
`api/routes/portfolio.py` (`/api/portfolio/filters`). Backtest historical
data stays on yfinance via `data/crypto.download_crypto_prices` — Alpaca
crypto bars start 2021-01-01 (varies by coin) and don't reach the project's
2018 BTC / 2020 universe historical floor. The C9 drop-today-partial-bar
fix continues to apply because Alpaca's bars are dated by UTC-midnight
start the same way yfinance's are; same data shape, same fix. See
`docs/archive/HANDOFF_ALPACA_BARS.md` for the full migration brief.

**C11 — BNB excluded from live universe** (documented 2026-05-06,
co-resolved with C10). Surfaced during the Alpaca-bars migration: BNB is
not listed by Alpaca in any symbol form (404 across `BNB/USD`, `BNBUSD`,
`BNB`, `BNB/USDT`; absent from the full active-crypto-asset list).
Regulatory non-listing — SEC v. Binance (2023) alleged BNB's 2017 ICO was
an unregistered securities offering and the federal court allowed claims
based on Binance's post-ICO BNB sales to proceed; US-regulated brokers
avoid BNB to limit enforcement exposure. Pre-migration, BNB was in the
9-coin yfinance-fed universe, so the strategy ranked BNB as a candidate
even though Alpaca couldn't trade it — a latent bug where a BNB top-2
signal would have produced a rejected order. Never fired in practice
(`rebalance_log.jsonl` shows BNB never selected as top-2). Migration
naturally fixes this: `data/crypto.LIVE_CRYPTO_UNIVERSE` is the 8-coin
subset Alpaca lists, and `data/alpaca_crypto_bars.get_crypto_bars`
silently drops any symbol Alpaca returns no bars for. Backtest universe
unchanged at 9 coins — minor live↔backtest universe-shape gap on dates
where BNB was top-2 in backtest, accepted as "use what the broker can
trade." Sources: [Alpaca's supported crypto list](https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support),
[SEC v. Binance press release](https://www.sec.gov/newsroom/press-releases/2023-101).

### A4 live vs backtest divergence analysis (2026-05-17)

Post-mortem on the -$11K gap between A4 live ($87,847) and backtest
($98,869) over Apr 22 → May 16. Three root causes, all resolved:

**1. Late entry (Apr 22-24): ~$2K drag.**
BTC crossed the 125d SMA on Apr 22. Backtest entered at close. Live
account was being set up (first-entry cascading bugs, see below) —
five failed manual attempts before clean fills. First scheduled signal
didn't run until Apr 24 00:05 UTC. The initial BTC+ETH move was missed.

**2. Filter whipsaw (Apr 28-30): ~$2K drag.**
BTC oscillated within 1% of the 125d SMA for three days (Apr 28: -0.15%
below, Apr 29: -0.79%, Apr 30: +0.02% above). Backtest: one clean
cash→invested round-trip. Live: three round-trips — the 4-hourly filter
monitor triggered intraday flips (13:44, 05:44, 16:46, 21:28) each
incurring crypto spread + slippage. Architectural tradeoff: intraday
filter speed is valuable for real regime changes (Sharpe 1.27 daily vs
0.79 monthly) but whipsaws near the SMA threshold.

**3. C9 signal contamination (May 5-8): ~$7-8K drag (dominant).**
Partial-bar bug made live momentum ranks differ from settled-bar ranks.
Live picked BTC+XRP/BTC+LINK while backtest picked ADA+DOT/BNB+BTC.
Three rebalances in 6 hours on May 6 (00:52, 01:17, 06:05 UTC) with
different signals each time. Gap exploded from -$5K to -$16K in four
days. Resolved by C9+C10 fixes (drop partial bar, Alpaca bars for live).

**Structural residual: BNB exclusion (C11).**
Backtest picks from 9 coins, live from 8 (no BNB). BNB selected on
19.2% of OOS days. Impact in the Apr-May window: ~0.56pp ($563). Full
OOS impact is larger (Calmar 6.83 → 5.32 pre-cost/pre-vol-scaling, 9 vs
8 coin). The 8-coin backtest is the honest live-comparable reference.

**Post-fix convergence:** After C9/C10 resolved May 8 and the
liquidation+re-entry reset, live and backtest signals aligned (both
picked ADA+LINK May 9-10). Gap stabilized at ~$11K — the early damage
was permanent because the missed moves and whipsaw losses compounded.

### C12 — Reconciliation race condition (fixed 2026-05-16)

`save_expected_positions` read `broker.get_position_map()` immediately
after order submission — before fills settled. On May 15, DOT buy of
22,162 was still `pending_new`, saved as 10,475 (partial). May 16
reconciliation saw 108% drift → blocked rebalance (invisible on Events
Timeline because the failure returned before `log_rebalance()` was
called). Fix: save `result.target_positions` (intent, not transient
broker state) across all three callers (daily rebalance, filter monitor,
manual API). Reconciliation failures now logged to `rebalance_log.jsonl`
with `execute_error="position_reconciliation_failed"`.

### Combined OOS deltas across the C4+C6 fix wave

- Equity core (A1+A2 at 50/50): **22.3% CAGR / -7.7% MaxDD / Calmar 2.88 → 19.0% / -6.1% / 3.13** (post C4+C6).
- 3-account live book (A1+A2+A4 at 1/3): **30.3% / -7.0% / 4.31 → 26.5% / -6.2% / 4.28**.
- A4 standalone bootstrap CAGR p5/p50/p95: **+25.1% / +45.9% / +74.8%** (20-day blocks) → **+20.9% / +42.9% / +73.6%** (40-day blocks per R9) → **+19.4% / +43.3% / +74.8%** (8-coin live universe, 2026-05-17).

Net: cost-adjusted returns are honestly lower; vol-scaling in both sim and
live cut peak CAGR but improved MaxDD; combined Calmar essentially
unchanged (4.31 → 4.28).

## Tier 2 — Safety / concurrency (all fixed)

- **S1 (2026-04-20)**: cross-process lock race. All three rebalance entry
  points (API `/rebalance/execute`, the launchd-fired
  `scripts/daily_crypto_rebalance.py`, and `filter_check.py`) serialize via
  the same file lock (`dual_rebalance_lock` for the API; `file_rebalance_lock`
  directly in the cron paths).
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

Fixed:
- **R1** (2026-04-20). Validation Test 2 was labeled `walk_forward_refit`
  but never refit parameters. Renamed to `rolling_oos_fixed_params`; true
  walk-forward REFIT added as Test 6 + standalone explorers
  (`scripts/walk_forward_refit_a1.py`, `_a2.py`).
- **R2** (2026-04-21). `FIRE_VALIDATION_OVERRIDE=1` was global and could
  accidentally unblock retired A3. Retired status is now an unconditional
  block (no override bypasses it); per-account override
  `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` added; global override still works
  for fail/unvalidated/expired only.
- **R3** (2026-04-21, alongside C5). Strategy-level circuit breaker (-10%
  per strategy) was dead code — never wired into `compute_rebalance`.
  Deleted.
- **R4** (2026-04-21). Journal entries were lost if execute raised mid-
  flight. All three call sites (API, daily crypto cron, filter_check) now
  wrap `execute_rebalance` in try/finally; `log_rebalance` carries
  `execute_error`.
- **R5** (2026-04-21). `reset_circuit_breaker` left no audit trail. Reset
  now writes a journal entry with `source="halt_reset"` and pulls broker
  equity best-effort.
- **R9** (2026-04-21). Crypto bootstrap block size widened from 20d to 40d
  to capture longer regime autocorrelation (BTC bull/bear cycles); equity
  stays on 20d. A4 p5 CAGR tightened +25.1% → +20.9% — more conservative,
  still passes p5≥0.
- **R11** (2026-04-21). `check_price_staleness` silently skipped symbols
  with unfetchable new prices. Now flagged as `drifted` with
  `reason="unfetchable"`; API renders "(unfetchable)" in the 409 detail.
- **R12** (2026-04-21, alongside C7). Kelly / fractional-Kelly position
  sizing in `RiskManager` was dead code — never called from any rebalance
  path. Deleted (`calculate_position_size`, `PositionSize`,
  `kelly_fraction`, `max_loss_per_trade_pct`, `max_position_pct`).
  `kelly_criterion` remains as an informational reporting metric in
  `backtesting/metrics.py` only.
- **R16** (2026-04-21). Rebalance journal didn't persist `vol_scalar` /
  `vol_scalar_diagnostics`. Now does, across all three callers.

Still open (none block paper or real-money operation):
- **R6** — `marginal_portfolio_contribution` correlation uses native
  overlap; CAGR uses union+fillna. Different samples for the two halves
  of the portfolio-fit metric.
- **R7** — Sterling ratio groups by `.index.year`, so partial start-year
  inflates the mean.
- **R8** — OOS/IS CAGR ratio gate threshold (70%) is gameable by moving
  `TRAIN_END`; not load-bearing today since all strategies clear by a
  wide margin.
- **R10** — `is_non_tradeable` regex matches "CVR" anywhere in symbol,
  so future small-cap expansion could spuriously reject CVR-prefixed
  tickers.
- **R13** — Live rejects negative weights as a defensive guard, but no
  current strategy generates negatives. Belt-and-suspenders, kept as-is.
- **R14** — Backtest uses yfinance adjusted closes; live uses Alpaca
  `get_latest_prices()`. Indirectly counted under C6 (transaction costs);
  vendor discrepancy itself is a latent gotcha around splits.
- **R15** — Live qty rounding (`int(dollar/price)` for stocks, 8-decimal
  for crypto) silently drops sub-1-share positions; backtest assumes
  fractional. Cumulative impact <0.1% CAGR.

## 2026-07-18 (later) — A1 book-level vol scaling added (George-approved)

Investigation trigger: A1's clean-window lag vs SPY (dashboard impression
confirmed: +1.34% vs +4.78%, 04-22→07-17). Diagnosis chain: execution
parity CLEAN (live +1.34% vs signal-path +1.46% — no A4-style drag);
controls ruled out sizing scheme (RSP +5.8%) and factor (MTUM +9.6%);
root cause is **design** — StockMomentum vol-targets each name at 20%
((0.20/vol_i)/15) and never re-levers the diversified aggregate, so the
book ran 22% gross (6th percentile since 2019; 16-year average 40-70%)
with the 2026 all-AI-semi momentum cohort at 60%+ name vol. The
diversification benefit was computed and discarded.

Fix: the same book-level vol-scaling overlay as trend_lowvol
(0.15 target / halflife 21 / floor 0.5 / cap 1.5) on `sm_filtered`,
riding the config-driven cap infrastructure from the morning's A2 work.
Backtest: OOS CAGR 25.3% → **31.2%**, MaxDD -9.9% → -11.0%, Calmar 2.56
→ **2.84**. Full 6-test validation PASS (Test 2 median CAGR 18.8% over
26 windows; bootstrap p5 **+15.3%** — above the CAGR gate itself;
Test 6 PASS). Alpaca margin confirmed on A1 (multiplier 4, Reg-T BP
$191K; 1.5× gross $157K fits 2× overnight; all names marginable).
Live scalar at deploy ≈ 1.08 (realized vol 13.9% vs 15% target) —
extensions grow when the momentum cohort rotates calmer. Live from the
2026-07-22 rebalance.

## 2026-07-18 — A2 cap=1.5 restored; validation MARGINAL → PASS

The vol-scaling cap on A2 (`trend_lowvol`) returned to its original
validated design: `scalar_cap` 1.0 → 1.5 in `portfolio_config.py`
(single source — backtest, validation, and live all read it). The 2026-04
cap=1.0 "alignment" existed because `execution/rebalance.py` hardcoded
the cap on the claim "Alpaca paper is spot-only" — true only for crypto.
A2's equity paper account has Reg-T margin (multiplier 4 reported,
2× overnight is what matters; 1.5× gross needs $151K on $100K equity —
fits). Live path now takes the cap from config, clamps crypto books to
1.0 unconditionally, allows weight sums up to the configured cap (loud
failure above), and refuses levered targets on non-margin accounts with
a buying-power log line.

Validation (full 6-test, 2026-07-18): **PASS — OOS CAGR 16.8%
(was 11.0%), MaxDD -10.8%, Calmar 1.56, OOS/IS ratio 99%, bootstrap p5
+11.5%.** Matches the April sweep's shelved projection (16.6%/1.54).
~+2pp book CAGR at A2's ⅓ weight. First levered rebalance: 2026-07-22
(A2's live realized vol ~7-12% vs 15% target → scalar pins at cap).

Caveat logged for real money: backtest models no margin interest. At
~8% broker rates, fully-extended 0.5× borrow costs ~4% of equity/yr;
vol-scaling is only extended in calm regimes, so realistic net drag is
~1-2pp of the +5.8pp gross lift. Paper pays no interest — revisit at
the Fly/real-money gate.

Same session: VIX9D/VIX3M tail signal added to the 4h SPY filter cron
(`scripts/filter_check.py`, alert-only via macOS notification + state
fields `vix_ratio`/`vix_backwardation`, threshold 1.10, never triggers
a rebalance). Tail-leg context: `docs/research/EVENT_KILLTESTS_JUL2026.md`.

## 2026-07-13 — A4 retired (Crypto Momentum Rotation)

Marked `status="retired"` in `validation_state.json` (unconditional
rebalance block, same mechanism as A3). Account was 100% cash since
2026-06-01 (BTC below 125d SMA), so retirement executed zero trades.
Cron entries left in place — the gate returns `skipped` once per UTC
day, which marks the day done and keeps Ops staleness quiet.

Three independent legs, any one of which would have blocked promotion;
together they close the account:

1. **Edge decay.** Test-2 walk-forward CAGR decays monotonically across
   windows: +59.1% (2022-12→2023-12) → +35.2% → +23.3% → +24.6% →
   **+9.6%, Calmar 0.87** (2024-12→2025-12) — the newest window is below
   the Calmar 1.0 funding gate. The strategy monetized the 2020-2023
   alt-trend regime; 2024-2025 crypto is BTC-dominated chop.
2. **Execution never live-validated.** Live -23.1% vs signal-only -5.2%
   (+17.9pp drag). Rebalance-log forensics (05-05..05-09) show the drag
   was bug-era full-notional churn — XRP→LINK→ADA→BTC+DOT→BTC→ADA on
   consecutive days, including three fires in 6h on 05-06 (stale-data
   rank flip-flop + multi-fire cron) and a liquidate→rebuy whipsaw
   within 2 minutes on 05-08. Root causes fixed (C10 Alpaca bars,
   2026-06-09 `--if-due` single-fire), but zero clean signal-trading
   days accrued afterward to prove the fix (in cash from 06-01 on).
3. **Upgrade clock unreachable.** 33%→40% pre-commitment required ≥6
   months of signal-trading days with live Calmar ≥ 2.0; ~28 such days
   accrued in 12 weeks. On regime base rates the clock doesn't complete
   inside a year.

Slot preserved for a successor (candidates as of retirement: A5-Events
pooled sleeve, VIX tail leg, delta-neutral basis carry). Live-performance
detail in `AUDIT_FABLE.md` §2; decomposition method in
`scripts/signal_tracker.py`.

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
+ Calmar. See `VALIDATION.md`.
