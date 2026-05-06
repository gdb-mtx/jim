# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

### Key Documents
- **`CAPABILITIES.md`** — standing system-capabilities brief (LP / operator / future-self framing). Inventory + honest limits + peer comparison in one place. Update as the system evolves.
- **`AUDIT_MONTH2.md`** — open bugs and fix plan from the 2026-04-20 adversarial review. Has caveats on every headline number; read this before trusting CAGR/Calmar figures below.
- `HISTORY.md` — resolved fixes and decision deltas (April 2026 fix pack, A4 first-entry cascade, framework changes). Look here when a code path mentions "post-CN fix" and you want to know what changed.
- `DECISIONS_RESOLVED.md` — record of the April 2026 portfolio-architecture decisions (A3 retired, A4 at 33% with a pre-committed upgrade plan to 40% — manual decision framework, not an automated rule).
- `PLAN.md` — Full project plan with architecture, roadmap, risk framework, and essential reading
- `PLAN_MODE2.md` — Two-mode architecture: Mode 1 (structural alpha, existing) + Mode 2 (informational alpha, PEAD + event-driven + macro regime). The strategic plan for compounding $50K over the bridge to 59½.
- `VALIDATION_PLAN.md` — CAGR-first evaluation framework (v2, 2026-04-18)
- `RATE_VOL_SCOPE.md` — Account 5 candidate scoping (MOVE-conditional TLT reversal)
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `DEPLOYMENT_PLAN.md` — 24/7 cloud deployment research for the live trading module (Fly.io primary, 5-phase migration plan). Paper-first; pre-real-money hardening in Phase 5.
- `AUTOMATION.md` — reference for the A4 daily rebalance automation: APScheduler job, launchd filter monitors (equity + crypto), sleep behavior, install/uninstall commands.
- `OPS_DASHBOARD_PLAN.md` — design spec for a new "Ops" tab consolidating scheduler status, filter state, validation, and event timeline into a single dashboard view. Motivated by killing macOS notifications and prepping for cloud migration. Not yet built — next session.
- `DATA_SOURCES.md` — standing observation that yfinance is the root cause of nearly every cache-corruption incident, with an incident log and candidate replacements (Alpaca/Polygon/hybrid). Becomes load-bearing at Phase 5 (real money).
- `References/` — Original 2020 proposal and Ernie Chan books

### Project Decisions
- **Broker**: Alpaca (primary), QuantConnect (research only when needed)
- **Backtesting**: vectorbt
- **Frontend**: React + TypeScript + TradingView Lightweight Charts (v5)
- **Backend**: Python + FastAPI
- **Risk**: Equal-weight top-N position sizing (at strategy layer) + SPY/BTC trend filters + vol-scaling overlay + a two-tier drawdown monitor (**-10% dashboard alert**, **-35% catastrophe halt with manual reset**). The -10% tier is a dashboard banner only, not persisted, no notifications. The -35% tier is the only persisted state (`{"halted": bool}`). Older controls (-15% auto-halt, -10% strategy-level breaker, Kelly + 2% rule + 20% position cap) are retired — see HISTORY.md C5/C7.
- **Evaluation framework (v2, 2026-04-18)**: CAGR-first scorecard, not Sharpe. Primary gates: OOS CAGR ≥ 15%, OOS MaxDD ≥ -40%, OOS Calmar ≥ 1.0, OOS/IS CAGR ratio ≥ 70%. Full scorecard (MAR, Sterling, Burke, Pain, Ulcer, UPI, Sortino, Omega, Gain-to-Pain, time underwater, max recovery days) reported for context. Sharpe shown informational only — not gated. See `VALIDATION_PLAN.md`.
- **Statistical validation**: Six-test scorecard (all required before real money; quarterly re-validation enforced via gate):
  - **Test 1** — OOS holdout (train 2010-2022, test 2023-today).
  - **Test 2** — Rolling OOS with fixed parameters.
  - **Test 3** — Parameter stability across half-A/half-B splits (crypto only; other accounts skip).
  - **Test 4** — Block bootstrap CAGR p5/p50/p95 (gated: p5 ≥ 0%).
  - **Test 5** — Portfolio fit (satellite marginal contribution; not gated).
  - **Test 6** — Walk-forward REFIT vs defaults (non-gating). Per-window grid search on adapter-defined `refit_param_grid`; PASS if defaults within 10% of refit or better, REVIEW only if refit stably beats defaults by >20%. Strategy-discovery pattern: new candidates get dropped in as `refit_strategy_factory` + grid on an adapter or run via `scripts/walk_forward_refit_*.py`.
- **No shorting**: Use reverse ETFs instead when needed (avoids margin/borrow complexity)

### Three-Account Live Architecture
Uncorrelated factor diversification across 3 Alpaca paper accounts, 1/3 each of total book. A3 is retired but its Alpaca account slot is preserved for future strategy assignment.

- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter — profits when trends persist. Monthly rebalance.
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling — crisis alpha + defensive. Monthly rebalance.
- **Account 3 (FIRE 0.3 — RETIRED)**: Slot preserved for future strategy. See `DECISIONS_RESOLVED.md`.
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 2 of 9 coins by 21-day momentum, BTC 125d SMA trend filter + vol-scaling. **Daily rebalance** at 8:05 PM laptop-local time via launchd (`com.fire.daily-crypto-rebalance` plist → `scripts/daily_crypto_rebalance.py`). Lands at 00:05 UTC when the laptop is in EDT (UTC-4); drifts to other UTC offsets when traveling. Strategy uses 21d momentum so a few-hour intraday drift is signal noise. Replaced in-process APScheduler on 2026-05-05 after a long-uptime drift incident. Schedule was originally Hour=0 with `TZ=UTC` env var, but launchd interprets `StartCalendarInterval` in laptop-local TZ regardless of env var (and LaunchAgents queue during darkwake), so Hour=20 in laptop-local was chosen to fire while the laptop is reliably in FullWake. Cloud target post-Fly is Fly Cron Machines, which honor schedule TZ properly. Parameters picked via `scripts/crypto_robust_opt.py` by maximizing `min(Calmar_half_A, Calmar_half_B)` across 144 configs — regime-robust objective. SMA-125/top2 is the robust winner (half A 2.89 / half B 2.94). A4 weight in combined book is **33%**, with a pre-committed **40% upgrade** once ≥6 months of signal-trading days (not cash-on-filter) confirm live Calmar ≥ 2.0 and A4↔equity correlation ≤ 0.25.

Cross-account correlations (OOS backtest 2023-01-03 → 2026-03-10):
- A1↔A2: **0.38** (backtest) — genuinely diversified
- A1↔A4: 0.10-0.19
- A2↔A4: 0.10-0.19

**Live correlation panel** (dashboard) shows A1/A2/A4 pairs only. A4 first-entered positions on 2026-04-22 (50% BTC/USD + 50% ETH/USD); live correlations populate once A4 has ≥21 daily returns post-entry.

Combined OOS (2023-01-03 → 2026-04-20; equity trading calendar, A4 compounded Fri→Mon, ppy=252; net of costs + vol-scaling):

- Equity core (A1+A2 at 50/50): **CAGR +19.0%, MaxDD -6.1%, Calmar 3.13**
- 3-account live book (A1+A2+A4 at 1/3 each): **CAGR +26.5%, MaxDD -6.2%, Calmar 4.28**

A4 weight sweep (OOS, current vs upgrade target):
- A4 @ 33% / equity 67%: CAGR +26.4% / MaxDD −6.2% / Calmar **4.27** (current)
- A4 @ 40% / equity 60%: CAGR +28.0% / MaxDD −6.5% / Calmar **4.33** (upgrade target)
- Higher A4 → higher Calmar, monotonic across 25/33/40/50. The 40% upgrade gate (Calmar ≥ 2.0) is cleared with wide margin in backtest.

**Forward-looking haircut on the combined Calmar 4.28:** mathematically correct (low pairwise correlations, time-offset drawdowns) but probably optimistic for real-money projections. The 3.3-year OOS window is mostly benign and contains regimes generous to our factor mix. Correlations spike in crises — the live A1↔A3 correlation of 0.84 vs backtest 0.38 is a cautionary example. Expect a realistic live Calmar closer to **2.5-3.5** over a multi-year period once you account for: (a) one stress-event correlation spike, (b) potential filter whipsaw on A4, (c) C3 survivorship ~1-2pp of A1 CAGR. The 2.0 upgrade gate is conservative by design — 4.28 clears it ~2×, which is the right margin, but don't cite 4.28 as "what we'll realize." The live-tracking clock (reset 2026-04-20) is the only thing that will settle this; expect the gap to show up in the A1↔A2 live correlation first.

Account 4 standalone (OOS 2023-01-03 → 2026-04-20):
**CAGR +40.4%, MaxDD -12.7%, Calmar 3.18** (Sharpe 1.76 informational). Block-bootstrap CAGR p5/p50/p95: **+20.9% / +42.9% / +73.6%** (40-day blocks per R9, captures crypto's longer regime autocorrelation).

Multi-account credentials in `.env` (ALPACA_API_KEY, ALPACA_API_KEY_2, ALPACA_API_KEY_3, ALPACA_API_KEY_4). `AlpacaBroker(account=1|2|3|4)` selects credentials. Account 3 is retired; orders endpoint `_require_active()` guard + validation_gate both block rebalance attempts against it.

Rebalance schedule (two layers — exposure management + signal rotation):
- **Every 4 hours (launchd)**: Filter monitor checks all active accounts — auto-rebalances if SPY/BTC filter flips. Both equity and crypto plists use `StartInterval=14400`. Was once-daily-at-16:30 for equity but macOS dropped a fire after a closed-laptop deferred run; relative-interval re-arms reliably on wake. Pre-Fly.io measure.
- **Daily at 8:05 PM laptop-local time**: Account 4 crypto signal rotation — automated via launchd (`com.fire.daily-crypto-rebalance` plist runs `scripts/daily_crypto_rebalance.py`, server-independent). Lands at 00:05 UTC when laptop is in EDT; drifts to other UTC offsets when traveling. Schedule chosen to fire while laptop is reliably in FullWake (LaunchAgents queue during darkwake).
- **First Monday of month**: Accounts 1 & 2 momentum/trend signal rotation (manual).

**Concurrency:** all three rebalance entry points (API `/rebalance/execute`, launchd A4 job, `filter_check.py`) serialize via `dual_rebalance_lock` (async + file lock) or, for the sync cron paths, the same `file_rebalance_lock` they observe. Contention raises `RebalanceLockedError` → 409 from the API, `status="locked"` from the cron.

### Strategies — OOS scorecard (live accounts)

**Fresh-data OOS per the CAGR-first framework (test window ends 2026-04-20). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION_PLAN.md`.**

Numbers below are post the C1+C2+C4+C6 fix pack (calendar/ppy convention, BTC MA warmup, live vol-scaling parity, transaction costs) and C9 (crypto partial-bar signal contamination, 2026-05-06). See `HISTORY.md` for what each fix changed. **C3 (S&P 500 survivorship bias)** is the one open caveat — A1 standalone CAGR is ~1-2pp overstated; not fixed pre-real-money. **C10 (yfinance settled-bar publishing delay)** is the other open caveat — adjacent to C9, affects A4 live↔backtest parity by ≤1 day of stale signal data on some fires; mitigation deferred to post-Fly migration.

| Strategy | Status | CAGR | MaxDD | Calmar | MAR | Sortino | *Sharpe (info)* |
|---|---|---|---|---|---|---|---|
| **Crypto Momentum (Acct 4)** | PASS | **+40.4%** | **-12.7%** | **3.18** | 3.18 | — | *1.76* |
| **Stock Momentum + SPY (Acct 1)** ⚠ C3 | PASS | **+27.2%** | **-9.9%** | **2.76** | 2.76 | 2.10 | *2.04* |
| **Trend + Low-Vol (Acct 2)** | MARGINAL | **+11.0%** | **-7.3%** | **1.51** | 1.51 | — | *1.37* |
| *Reversal + Momentum (Acct 3)* — retired | RETIRED | *14.5%* | *-7.2%* | *2.03* | — | — | — |

A1 + A4 PASS the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates. **A2 is MARGINAL** — backtest used to leverage the low-vol leg up to 1.5× in calm regimes that live could never realize; cap=1.0 alignment brings it to 11%. MARGINAL is allowed for paper per `execution/validation_gate.py`.

A3's historical numbers retained as MARGINAL per last validation; strategy available in Backtests → Building Blocks as `reversal_blend`.

Research/building-block strategies (in-sample only — never went to a live account, OOS not measured):

| Strategy | Sharpe (IS) | Return (IS) | MaxDD (IS) | Notes |
|---|---|---|---|---|
| Short-Term Reversal + SPY | 1.41 | 12.7% | -10.0% | Anti-momentum |
| Low Volatility + SPY | 1.32 | 14.7% | -11.9% | Defensive |
| Blended Portfolio + SPY Filter | 1.37 | 14.2% | -9.3% | 60/20/20 momentum |
| Stock Momentum (S&P 500) | 1.16 | 15.9% | -18.6% | No filter |
| Cross-Sectional Momentum | 0.85 | 7.0% | -10.8% | ETF-based |
| Time-Series Momentum | 0.85 | 6.2% | -15.2% | ETF-based |
| Multi-Asset Trend | 0.76 | 5.8% | -13.0% | Crisis alpha |
| Dual Momentum (Antonacci) | 0.83 | 7.6% | -19.9% | ETF-based |
| Multi-Timeframe Momentum | 0.67 | 4.1% | -11.0% | Regime fail |
| *SPY Buy & Hold (benchmark)* | *0.87* | *14.5%* | *-33.7%* | — |

- **ETF Universe**: 18 assets (8 broad ETFs + 9 sector ETFs + SHY cash proxy)
- **Multi-Asset Universe**: SPY, EFA, TLT, GLD, DBC (5 uncorrelated asset classes)
- **Stock Universe**: 501 S&P 500 stocks (cached parquet, survivorship bias noted). Coverage gate: trailing 500 trading days ≥80% non-NaN — lets recent S&P additions enter the rotation once they have ~2y of history without corrupting backtests (pre-IPO NaN rows propagate to NaN ranks → excluded from selection for periods before the ticker existed).
- **Crypto Universe**: 9 coins (BTC, ETH, SOL, BNB, ADA, AVAX, LINK, DOT, XRP). Quality/volume-gated by design — top-cap L1s and major smart-contract platforms only. Deliberate exclusion of memecoins (DOGE, SHIB, PEPE, etc.) and low-float altcoins. Any future crypto strategy (e.g. the Account 5 reversal candidate) must reuse this same 9-coin list or a subset; no expansion into thin-liquidity or narrative-speculation coins.
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007).
- **BTC 125-day SMA trend filter**: Binary 100% cash when BTC < 125d SMA (sat out all of 2022). Robust-opt picked 125d from 200d/150d/125d/100d grid.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4.
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone.
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period.
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`.

### Risk Controls — Operational Behavior

**Time convention — ET is the system reference timezone.** All scheduled times in FIRE are anchored to America/New_York (ET, DST-aware). The equity market runs on ET, and the user is a digital nomad whose laptop local time shifts constantly — laptop-local timezones must never be load-bearing. Same discipline for both local (launchd) and cloud (Fly cron) schedulers: `TZ=America/New_York` or `CRON_TZ=America/New_York`. Enforced at the code layer by `data/trading_dates.py` helpers (`today_et`, `utc_ts_to_et_date`) — use these, don't call `date.today()` or `datetime.now()` directly. The A4 crypto launchd job is the local-laptop exception: it fires at 8:05 PM laptop-local (= 00:05 UTC during EDT). launchd's `StartCalendarInterval` is interpreted in laptop-local TZ regardless of any `TZ` env var on the plist (LaunchAgents also queue during darkwake), so we picked an evening laptop-local hour for FullWake reliability. Cloud target (Fly Cron Machines) will fire at exact 00:05 UTC.

**When are filters and circuit breakers checked?**
Risk controls are checked at two levels:

1. **Filter monitor (every 4h, automated)**: `scripts/filter_check.py` runs via macOS launchd every 4 hours (both equity and crypto plists, `StartInterval=14400`) — even when the server is off. Computes SPY and BTC filter scalars, compares to last-known state in `data/risk_state/filter_state.json`. If a filter flips, **auto-executes rebalances** for affected accounts with full safety rails. Logs to `data/filter_check.log` with `source="filter_monitor"` in the rebalance journal.

2. **Scheduled rebalance (signal rotation)**: Rotates *which* stocks/assets to hold at the strategy's native cadence:
   - **Account 4** (daily): launchd `com.fire.daily-crypto-rebalance` at 8:05 PM laptop-local (= 00:05 UTC in EDT; drifts on travel). Server-independent.
   - **Accounts 1 & 2** (monthly): Manual trigger first Monday of month

**Key design: exposure management is decoupled from signal rotation.** The filter monitor handles *how much* to hold (reacts same-day to filter changes). The scheduled rebalance handles *what* to hold (monthly/weekly signal rotation). Backtesting showed this split is critical: daily filter reaction = Sharpe 1.27, monthly lag = Sharpe 0.79 (worse than no filter). *Caveat for A4*: A4's signal rotation is daily, matching its filter cadence — so the decoupling is really about A1/A2.

The dashboard's RiskStatusPanel and FilterStatusBanner show current status. FilterStatusBanner also shows the filter monitor's last check time and any recent auto-rebalances.

**Drawdown monitor — two tiers:**

- **-10% dashboard alert** — computed live in `/api/portfolio/risk` from current Alpaca equity + the daily snapshot history. Renders as an amber banner in `RiskStatusPanel`. Not persisted, no push notifications, no heartbeat. Reaction time = next dashboard poll (30s) or next rebalance preview. The SPY/BTC filters + vol-scaling are already de-risking continuously; the alert is a heads-up, not a gate.
- **-35% catastrophe halt** — per-account kill-switch. Latches on first breach seen by either the `/risk` endpoint or a rebalance preview. `POST /api/orders/rebalance/execute` returns **403** while latched; manual reset via dashboard button or `POST /api/portfolio/risk/reset?account=N`.
- **Peak is derived from snapshots, not stored.** `data/snapshots.py` writes one equity row per trading day per account; `compute_drawdown()` takes `max(snapshot_max, current_alpaca_equity)`. Removes the stale-peak failure mode entirely.

**What the -35% threshold is and isn't:**
- Deepest OOS MaxDD observed across live strategies: A1 -9.8%, A2 -7.3%, A4 -11.4%, combined -7.0%. Deepest IS MaxDD: A4 -13.68% (2022 crypto winter, filter trimmed it). -35% sits ~3× deeper than any observed event.
- A test sweep across 16y of IS+OOS confirms **neither -35% nor the old -15% threshold ever fires** in backtest. The old -15% auto-halt was structurally redundant AND empirically inert.
- -10% alert would fire ~3× per 16y per strategy in backtest — rare signal, not spam.

**Breaker state** persists to disk (`data/risk_state/circuit_breaker_acct{N}.json`) — schema: `{"halted": bool}`. That's it. Corrupted file → fail-safe `halted=True` until manual reset.

**Backtest parity:** `backtesting/drawdown_halt.py` provides `simulate_drawdown_halt(returns, halt_threshold=0.35)` — a post-hoc halt-and-hold layer. For the -35% threshold it's a no-op on every current strategy's historical returns (sim/live parity exact), but the scaffolding exists for stress-test scenarios or future threshold experiments.

**Sub-broker-minimum order rejections are expected, not a bug.** Small drift on A4's daily crypto rebalance can produce sub-$10 BTC orders that Alpaca rejects with `cost basis must be >= minimal amount of order 10`. The journal correctly captures `orders_submitted: 2, orders_failed: 1` with the broker error message. Other legs execute normally — net financial impact zero. **Revisit only if dust rejections become recurring** (e.g., daily for >30 days) and start obscuring real failures in the `orders_failed` field.

### Architecture
```
# Mode 1: Factor Trading System
data/pipeline.py          — yfinance ETF data download & caching (threading.Lock serializes yf.download; returned-column verification rejects cross-thread contamination; cache-read schema check refuses corrupt caches; 0-row write+read guards reject empty data)
data/sp500.py             — S&P 500 stock universe + VIX data
data/crypto.py            — Crypto data pipeline (yfinance + symbol mapping; `normalize_alpaca_position_symbol` converts `BTCUSD` → `BTC/USD` so position-API + order-API forms match in the rebalance diff)
data/snapshots.py         — Daily equity snapshots (parquet) + Alpaca backfill
data/trading_dates.py     — ET trading-date helpers (today_et, utc_ts_to_et_date) — TZ-stable
data/correlation.py       — Inter-account correlation monitoring (rolling 21-day)
data/plausibility.py      — Per-ticker value-plausibility checks + cross-validation + state
strategies/base.py        — Abstract strategy interface
strategies/trend_following.py — Time-Series & Multi-Timeframe Momentum
strategies/momentum.py    — Cross-Sectional & Dual Momentum (ETF-based)
strategies/stock_momentum.py — Individual stock momentum + VIX filter
strategies/multi_asset_trend.py — Multi-asset trend following (SPY/TLT/GLD/DBC/EFA)
strategies/low_volatility.py — Low-vol anomaly + momentum quality filter
strategies/mean_reversion.py — Short-term reversal (buy weekly losers)
strategies/crypto_momentum.py — Crypto momentum rotation (21-day, top 2, BTC filter)
strategies/portfolio.py   — Re-export shim. Preserves existing import path.
strategies/portfolio_config.py   — LIVE surface: PORTFOLIOS dict + ETF/STOCK/CRYPTO_STRATEGIES factory maps + compute_spy_trend_filter + compute_btc_trend_filter. Hard invariant: zero imports from backtesting/ or mode2/.
strategies/portfolio_backtest.py — RESEARCH surface: run_portfolio / run_equity_core / run_combined_portfolio / apply_vol_scaling / _generate_strategy_returns. May import from portfolio_config (one-way).
backtesting/metrics.py    — Sharpe, drawdown, Kelly, profit factor
backtesting/validation.py — Rolling-OOS + Monte Carlo + regime tests + walk_forward_refit_analysis (per-window param refit)
backtesting/bootstrap.py  — Block bootstrap for confidence intervals (VALIDATION_PLAN Test 4)
backtesting/account_adapters.py — Per-account (returns, prices, strategy_fn) bundles for the validation runner
backtesting/drawdown_halt.py — Post-hoc halt-and-hold layer. No-op at -35% across all current strategies.
backtesting/costs.py      — Per-strategy transaction-cost layer. 5 bps equity / 20 bps crypto round-trip; subtracts `bps × turnover` from each day's return. `apply_costs=False` recovers gross returns for calibration runs.
execution/risk_manager.py — Halt-latch + pure `compute_drawdown(account, equity, ...)` helper. State file is `{"halted": bool}` only.
execution/notifications.py — Shared macOS notification helper (osascript) used by `scripts/filter_check.py`. `FIRE_DISABLE_NOTIFICATIONS=1` silences for tests/headless.
execution/vol_scaling.py  — Live vol-scaling scalar. Reads account equity returns and computes EWMA vol-target scalar.
execution/validation_gate.py — Rebalance gate; blocks accounts without a passing validation record
execution/alpaca_broker.py — Multi-account Alpaca client (4 paper accounts)
execution/rebalance.py    — Signal-to-order pipeline (target weights → trade list). Crypto orders use `time_in_force="gtc"` and notional (dollar-amount) sizing on buys — sidesteps the price-drift-between-preview-and-fill "insufficient balance" reject path. Notional total capped to 99.9% of live Alpaca cash.
execution/rebalance_log.py — Structured JSONL rebalance audit trail. Each entry carries `raw_signal_weights` (pre-overlay) + `post_filter_weights` (post-SPY/BTC, pre-vol) alongside scalars and final orders.
api/main.py               — FastAPI backend (lifespan; no in-process scheduler — daily crypto rebalance is launchd-fired, see scripts/daily_crypto_rebalance.py)
api/locks.py              — Per-account locks: async (in-process) + file-based (cross-process via fcntl)
api/routes/portfolio.py   — Account summary, positions, equity history, correlation, risk status, filter status (LIVE — ships to cloud)
api/routes/orders.py      — Rebalance preview/execute, order history, rebalance journal (LIVE — ships to cloud)
api/routes/ops.py         — Scheduler status, filter state, validation, event timeline (LIVE — ships to cloud)
api/research/backtests.py — Backtest runner (individual + combined + crypto). LAPTOP-ONLY — imports from backtesting/, won't ship to Fly.
api/research/strategies.py — Strategy list with live metrics. LAPTOP-ONLY — same rationale.
dashboard/src/strategyMetadata.ts — Strategy categories, descriptions, sort order
dashboard/src/components/Tooltip.tsx — Reusable hover tooltip (dark theme)
dashboard/src/components/Toast.tsx — Global toast notification system (error/warning/info)
dashboard/src/components/EquityHistoryChart.tsx — Live equity curves (TradingView, per-account + combined)
dashboard/src/components/CorrelationPanel.tsx — Correlation matrix + rolling chart + alerts (Combined view)
dashboard/src/components/StrategyPanel.tsx — Grouped strategy list (Live/Portfolio/Building Blocks)
dashboard/src/components/RiskStatusPanel.tsx — Circuit breaker status + reset (polls every 30s)
dashboard/src/components/FilterStatusBanner.tsx — SPY/BTC trend filter status with price vs 200d MA
dashboard/src/components/RebalancePanel.tsx — Preview/execute rebalance with action-classified order table (new/increase/decrease/exit)
dashboard/src/components/RebalanceHistory.tsx — Rebalance event journal with expandable order details
dashboard/                — React + Vite + TradingView Charts
scripts/start.sh          — Start backend + frontend (recommended)
scripts/filter_check.py   — Daily filter monitor — auto-rebalances on SPY/BTC filter change
scripts/run_validation.py — VALIDATION_PLAN Tests 1-6 runner; updates data/risk_state/validation_state.json
scripts/crypto_robust_opt.py — Crypto parameter search via min(Calmar_A, Calmar_B); produced SMA-125/top2 production config
scripts/walk_forward_refit_a1.py — True walk-forward REFIT for A1 Stock Momentum (per-window grid search + OOS eval)
scripts/walk_forward_refit_a2.py — Same for A2 Low-Volatility leg
scripts/daily_crypto_rebalance.py — Account 4 daily rebalance, launchd-fired at 00:05 UTC (replaced in-process APScheduler 2026-05-05)
scripts/com.fire.daily-crypto-rebalance.plist — macOS launchd plist for the daily crypto rebalance (Hour=20, Minute=5 laptop-local; = 00:05 UTC in EDT)
scripts/com.fire.filter-check-equity.plist — macOS launchd plist for SPY filter (every 4h, `--filter spy`)
scripts/com.fire.filter-check-crypto.plist — macOS launchd plist for BTC filter (every 4h, `--filter btc`)
scripts/watch_filters.py  — GitHub Actions travel-window watcher; pushes ntfy.sh alerts on SPY/BTC crossings while the laptop is asleep.

# Mode 2: PEAD / Informational Alpha
mode2/earnings.py         — Finnhub EPS data + Insider Monkey transcript scraper + SEC EDGAR
mode2/pead.py             — PEAD scoring prompt templates (structured JSON + quick analysis)
mode2/tracker.py          — Recommendation JSONL tracker with outcome logging
mode2/run_analysis.py     — CLI runner: fetch, summary, analyze, status commands
data/mode2/transcripts/   — Cached transcript JSON files ({SYMBOL}_Q{N}_{YEAR}.json)
data/mode2/recommendations.jsonl — Recommendation log with entry/exit/P&L tracking
data/mode2/reports/       — Weekly markdown research reports
References/mode2-data-sources-research.md — Full data source evaluation (9 sources tested)
```

### Mode 2 Usage
- **Fetch earnings + transcripts**: `uv run python3 -m mode2.run_analysis fetch --symbols JPM,GS,C --quarter 1 --year 2026`
- **Show summary**: `uv run python3 -m mode2.run_analysis summary --quarter 1 --year 2026`
- **Generate analysis prompt**: `uv run python3 -m mode2.run_analysis analyze --symbol JPM`
- **Tracker status**: `uv run python3 -m mode2.run_analysis status`
- **Data sources**: Finnhub (free, EPS surprise + news), Insider Monkey (free, transcript scraping), yfinance (prices). See `References/mode2-data-sources-research.md`.
- **API keys**: `FINNHUB_API_KEY` and `ALPHA_VANTAGE_API_KEY` in `.env`
- **Transcript URL discovery**: Search `site:insidermonkey.com "{COMPANY}" "Q1 2026 earnings call transcript"`, add URL to `TRANSCRIPT_URLS` dict in `run_analysis.py`
- **PEAD drift expectations by market cap**: Large-cap 1-3%, mid-cap 3-5%, small-cap 5-8%. Don't set small-cap targets on mega-cap banks.

### Running the Project
- **Both servers**: `./scripts/start.sh` (recommended — starts backend + frontend, cleans up stale processes)
- **Backend only**: `uv run uvicorn api.main:app --reload` (from project root)
- **Frontend only**: `cd dashboard && npm run dev` → http://localhost:5174
- **Validation**: `uv run python3 scripts/run_validation.py --account N` — runs Tests 1-6. Writes a markdown report + updates `data/risk_state/validation_state.json`. Rebalances on accounts without a `status="pass"` record (and unexpired) return 403. Quarterly re-validation enforced via `expires`. See `VALIDATION_PLAN.md`.
  - Test 6 runs if the adapter defines a `refit_param_grid`; adds ~15-60s per account depending on grid size.
  - Standalone refit explorers: `scripts/walk_forward_refit_a1.py` and `walk_forward_refit_a2.py`. Support `--grid small|medium|large`.
  - **Strategy-discovery workflow** — how to evaluate a new candidate strategy: see `VALIDATION_PLAN.md` → "Test 6 → Recipe for a new candidate strategy" (5-step process: write class → pick grid → run standalone refit → decide → wire into adapter).
- **Filter monitor**: Runs automatically via launchd every 4h (no server needed)
  - Manual run: `uv run python3 scripts/filter_check.py` (or `--dry-run` to check without trading)
  - Check status: `launchctl list | grep fire`
  - View logs: `cat data/filter_check.log` or `cat data/risk_state/filter_state.json`
  - Install (first time or re-install):
    ```
    launchctl unload ~/Library/LaunchAgents/com.fire.filter-check.plist 2>/dev/null  # remove old single-plist if present
    rm -f ~/Library/LaunchAgents/com.fire.filter-check.plist
    cp scripts/com.fire.filter-check-equity.plist scripts/com.fire.filter-check-crypto.plist scripts/com.fire.daily-crypto-rebalance.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.fire.filter-check-equity.plist
    launchctl load ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist
    launchctl load ~/Library/LaunchAgents/com.fire.daily-crypto-rebalance.plist
    ```
  - Uninstall: `launchctl unload ~/Library/LaunchAgents/com.fire.filter-check-equity.plist ~/Library/LaunchAgents/com.fire.filter-check-crypto.plist ~/Library/LaunchAgents/com.fire.daily-crypto-rebalance.plist`
  - View daily rebalance logs: `cat data/daily_rebalance.log` (script log) or `cat data/daily_rebalance_stderr.log` (launchd stderr)

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript
- **Async endpoints**: All FastAPI `async def` endpoints MUST use `asyncio.to_thread()` for blocking calls (Alpaca API, yfinance downloads, parquet I/O, pandas computations). Calling blocking functions directly freezes the event loop and makes the entire server unresponsive to concurrent requests. This applies to route handlers and scheduled jobs alike.
- **Maintainability is a first-class constraint.** George works on this alone with AI partners and re-enters the codebase after gaps. A clever optimization that requires holding three files in your head is worse than a boring implementation a future session can grok cold. Optimize for: fewer surfaces to remember, fewer invariants to re-verify, fewer places a change has to land. Before adding a new file/abstraction/mirror, ask whether it makes the next person's job easier or harder. If a "mirrors X" docstring is needed, the two implementations should probably be one.

### Working with Claude — behavioral defaults

Rules promoted from session memory because they failed concretely in past work. Each one fired at least once. CLAUDE.md is loaded as instruction every session; memory is softer "context I might use" — behavioral guardrails belong here.

- **Preference ≠ requirement.** When the user mentions a tool, library, or platform offhand ("I like X", "use Y"), ask whether it's a hard requirement or a preference before designing around it. Default to the engineering recommendation; surface preference deviations as labeled trade-offs ("if you'd rather X, here's what it costs"). Don't backfill engineering justifications around taste — that produced a Vercel-split deployment plan that didn't survive 5 minutes of re-reading (rewritten in commit `7f618d4`).

- **Stop and confirm before any change >50 lines or any new file/architecture decision.** State the smallest viable alternative + what you're proposing + why, and wait for a yes. The 119-line min-notional patch (commit `da068eb` → reverted `2b7ed8e`) and the original Vercel split both bypassed this checkpoint.

- **Don't duplicate authoritative external validation.** When the broker / upstream / external system already enforces a rule, do not preemptively re-implement it client-side. One occurrence is not a problem to solve. The bar for adding a local check is recurring noise that obscures real signal — weeks of repeated false alarms, not a single instance.

- **Diagnose before workaround.** When something looks broken, run the diagnostic that shows what the upstream actually thinks before proposing infrastructure to route around it. Surface "we could just wait" or "the broker handled it" as peer options, not fallback footnotes.

- **Reset triggers.** If George says "reset stance" / "smallest version" / "do you really need all this?" — drop what's being built, restate the actual problem in one sentence, propose the leanest possible response.

- **Honesty over flattery in commits and docs.** When a decision is driven by preference rather than engineering merit, label it as such ("user prefers X; trade-off is Y"). Future-you re-reading a doc should see what was actually decided and why.

- **Simplicity and clarity over complexity.** When two designs both work, take the smaller one. Prefer one obvious code path over two clever ones; prefer reading values from snapshots over recomputing them; prefer a single source of truth over parallel implementations whose equivalence has to be re-proven. Complexity in this system has consistently been the failure mode — `compute_live_vol_scalar` mirroring `apply_vol_scaling` with subtly different inputs (open-loop vs closed-loop) is exactly the kind of "same math, different reality" trap that simplicity prevents.

- **Test live↔backtest semantic parity, not just numeric parity.** When a live system reads "the same data" backtest used, ask: are the bars settled? Is the latest row a closed bar or a still-forming partial? Are timezone assumptions implicit? "yfinance returned a row, therefore it's a closed bar" is exactly the kind of unstated assumption that produced C9 — the partial-bar contamination silently diverged live from backtest for ~14 days before the gap was investigated. **How to apply:** when comparing live vs backtest results that *should* match but don't, look at the assumptions about data shape (closed vs partial), not just data values. The first question for a live↔backtest gap should be "is the strategy reading the same kind of data point in both modes?"

- **Research before disclaiming.** When asked about an external tool, package, repo, or concept you can't recall confidently, the first move is `WebSearch` / `WebFetch` (or the `claude-code-guide` agent for Claude-Code-internal questions) — not "I don't have firsthand knowledge of X." Stopping at "I don't know" silently puts the work back on George when a 30-second search would have delivered an actionable answer. **Why:** the 4.6 era handled this reflexively; 4.7 has regressed toward over-cautious disclaimers. **How to apply:** when about to write "I'd be guessing" / "I don't have confident knowledge of" / "I'm not sure about" — pause, run the search, then answer with what you found. For unfamiliar repos: hit `api.github.com/repos/<owner>/<repo>/contents/` to confirm structure and `raw.githubusercontent.com/.../README.md` for docs. Disclaimers are fine *after* research has been exhausted, not in place of it.

- **Idea Farm mode for strategic stagnation.** When George signals defensive-cycle fatigue ("do nothing new" verdicts repeating, "breakthrough" in mocking quotes, austerity framing he rejects, "we need bold"), invoke the idea-farm skill (`~/.claude/skills/idea-farm/SKILL.md`, slash `/idea-farm`) BEFORE running another optimization round. Mode = parallel general-purpose agents on bold vectors, generative tone instructed, verifiable URLs required, master INDEX synthesis. Default cadence: monthly minimum. **Why:** the 2026-05-04 session broke through 6 weeks of defensive cycling (HUNT_APR2026 → BOOK_SHAPE → "do nothing new") and produced the most generative output of the project — six tracks at $300K-$1M/yr realistic upside that prior optimization rounds had no path to. The idea-farm protocol is the codified mechanism that prevents that mode from atrophying. **How to apply:** watch for the trigger signals; when fired, propose the session before another round of "tighten the conservative plan." Skill at `~/.claude/skills/idea-farm/` documents the full protocol.

### Current Phase & Next Steps

**Mode 1 (Structural Alpha):** 3-account live book (A1+A2+A4) at 1/3 each; pre-Fly hardening mode.
- Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10, OOS CAGR 27.2%
- Account 2: 34 positions (Trend + Low-Vol) — live since 2026-03-10, OOS CAGR 11.0% MARGINAL
- Account 4: Crypto Momentum Rotation — daily at 00:05 UTC, SMA-125/top2 production, OOS CAGR 40.4%, Calmar 3.18. First live entry 2026-04-22; A4 33%→40% upgrade clock counts from that date (cash-on-filter days don't count).
- Live-tracking clock reset to 2026-04-20 (the Mar 10 → Apr 17 window was compromised by stale-data bug).

**Validation status:** All three active accounts PASS the CAGR-first gates. Results in `data/validation_reports/`, state in `data/risk_state/validation_state.json`. A3 status="retired" — retired accounts are an unconditional block, no override can bypass. `execution/validation_gate.py` blocks FAIL/unvalidated; MARGINAL allowed for paper. Overrides for FAIL/unvalidated/expired only: `FIRE_VALIDATION_OVERRIDE=1` (global) or `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` (scoped). Both surface a WARNING log.

**Open bugs:** Tier 1 closed except C3 (S&P 500 survivorship, ~1-2pp on A1 CAGR — only matters pre-real-money) and C10 (yfinance settled-bar publishing delay, ≤1 day stale data on A4 some fires — mitigation deferred to post-Fly migration). Tiers 2+3 fully closed. Tier 4 R2/R4-R10/R13-R15 are reporting hygiene, non-blocking. See `AUDIT_MONTH2.md` for the ranked detail; `HISTORY.md` for what each closed item changed.

**Mode 2 (Informational Alpha):** Phase A in progress.
- PEAD data pipeline + transcript scraper + scoring prompts + recommendation tracker built (`mode2/`).
- Data sources: Finnhub (EPS surprise, free), Insider Monkey (transcripts, free), yfinance (prices).
- Week 1 (2026-04-15): 6 companies analyzed, 1 long recommendation (C, conviction 4/5), 5 skips. C long at $131.69, stop $125, target $138, 40-day hold (paper).
- **Key learning**: Large-cap PEAD drift is 1-3% (not 5-8% as in academic literature which skews small-cap). Best PEAD opportunities will be mid-caps with less analyst coverage in weeks 2-4 of earnings season.

**Dashboard infrastructure:**
- 5-tab account switcher, live equity charts, correlation monitor, Backtests with grouped strategy panel
- All components `React.memo` optimized, no loading gates on background polls
- Data caching: ETF/SPY/S&P500/VIX/crypto parquets with staleness checks
- Daily equity snapshots, Alpaca backfill, circuit breaker monitoring, filter status
- Rebalance UI: preview → confirm → execute, action-classified orders, per-account locks
- Filter monitor: `scripts/filter_check.py` via launchd every 4h
- Ticker mapping: yfinance hyphens → Alpaca dots via `to_alpaca_equity_symbol()`
- Snapshot data quality: Alpaca backfill writes NaN for cash/positions — don't treat as zero

**Next steps:**
- **Mode 1**: stay alive in pre-Fly hardening mode; fix bugs as they surface; don't optimize. Open R-items in AUDIT_MONTH2 are non-blocking cleanup.
- **Find/build a new Account 4-class strategy** — directive 2026-04-18: current crypto account is acceptable baseline but not extraordinary. Target: OOS CAGR and Calmar that meaningfully exceed the existing single-account results. Funding-rate carry on perps was explored and shelved (infra + exchange risk). Open research vectors: rate vol (see `RATE_VOL_SCOPE.md`), commodity vol, narrative-aware crypto.
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season.
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`).
- Mode 2: Track C recommendation for 40 days (check price by 2026-05-25).
