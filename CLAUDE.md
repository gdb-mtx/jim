# George's Projects

## FIRE — Quantitative Trading System

### Guiding Principle
We're optimized for a builder with an AI partner. Different constraints, different optimal path. We build fast, iterate fast, and the infrastructure serves the research.

### Key Documents
- **`CAPABILITIES.md`** — standing system-capabilities brief (LP / operator / future-self framing). Inventory + honest limits + peer comparison in one place. Update as the system evolves.
- **`AUDIT_MONTH2.md`** — open bugs and fix plan from the 2026-04-20 adversarial review. Has caveats on every headline number; read this before trusting CAGR/Calmar figures below.
- `DECISIONS_RESOLVED.md` — record of the April 2026 portfolio-architecture decisions (A3 retired, A4 at 33% with a pre-committed upgrade plan to 40% — manual decision framework, not an automated rule). Formerly DECISIONS_PENDING.md; renamed after both decisions executed.
- `PLAN.md` — Full project plan with architecture, roadmap, risk framework, and essential reading
- `PLAN_MODE2.md` — Two-mode architecture: Mode 1 (structural alpha, existing) + Mode 2 (informational alpha, PEAD + event-driven + macro regime). The strategic plan for compounding $50K over the bridge to 59½.
- `VALIDATION_PLAN.md` — CAGR-first evaluation framework (v2, 2026-04-18)
- `RATE_VOL_SCOPE.md` — Account 5 candidate scoping (MOVE-conditional TLT reversal)
- `SDD.md` — Software Design Decisions — architectural patterns and lessons learned (polling, memoization, caching, startup)
- `DEPLOYMENT_PLAN.md` — 24/7 cloud deployment research for the live trading module (Fly.io primary, 5-phase migration plan). Paper-first; pre-real-money hardening in Phase 5.
- `References/` — Original 2020 proposal and Ernie Chan books

### Project Decisions
- **Broker**: Alpaca (primary), QuantConnect (research only when needed)
- **Backtesting**: vectorbt
- **Frontend**: React + TypeScript + TradingView Lightweight Charts (v5)
- **Backend**: Python + FastAPI
- **Risk**: Equal-weight top-N position sizing (at strategy layer) + SPY/BTC trend filters + vol-scaling overlay + a two-tier drawdown monitor (**-10% dashboard alert**, **-35% catastrophe halt with manual reset**). The old -15% auto-halt + -10% strategy-level breaker were retired 2026-04-21 (AUDIT_MONTH2 C5 resolution): the halt duplicated the SPY/BTC filters + vol-scaling, systematically exited V-shape recoveries, and never fired in 16y of IS+OOS data anyway. The -10% tier is a dashboard banner only (computed live from snapshots + current equity) — no push notifications, no heartbeat daemon, not persisted. The -35% tier is the only persisted state (`{"halted": bool}`). Historical "Fractional Kelly + 2% rule + 20% position cap" were wired in naming only — all three removed 2026-04-21 (AUDIT_MONTH2 C7 + R12).
- **Evaluation framework (v2, 2026-04-18)**: CAGR-first scorecard, not Sharpe. Primary gates: OOS CAGR ≥ 15%, OOS MaxDD ≥ -40%, OOS Calmar ≥ 1.0, OOS/IS CAGR ratio ≥ 70%. Full scorecard (MAR, Sterling, Burke, Pain, Ulcer, UPI, Sortino, Omega, Gain-to-Pain, time underwater, max recovery days) reported for context. Sharpe shown informational only — not gated. See `VALIDATION_PLAN.md`.
- **Statistical validation**: Six-test scorecard (all required before real money; quarterly re-validation enforced via gate):
  - **Test 1** — OOS holdout (train 2010-2022, test 2023-today).
  - **Test 2** — Rolling OOS with fixed parameters. (Previously mislabeled `walk_forward_refit`; corrected 2026-04-20 — no refit happens here.)
  - **Test 3** — Parameter stability across half-A/half-B splits (crypto only; other accounts skip).
  - **Test 4** — Block bootstrap CAGR p5/p50/p95 (gated: p5 ≥ 0%).
  - **Test 5** — Portfolio fit (satellite marginal contribution; not gated).
  - **Test 6** — Walk-forward REFIT vs defaults (added 2026-04-20, non-gating). Per-window grid search on adapter-defined `refit_param_grid`; PASS if defaults within 10% of refit or better, REVIEW only if refit stably beats defaults by >20%. A1 + A2 currently PASS — literature defaults are not demonstrably suboptimal and a true parameter search cannot beat them. See `VALIDATION_PLAN.md`. Strategy-discovery pattern: new candidates get dropped in as `refit_strategy_factory` + grid on an adapter or run via `scripts/walk_forward_refit_*.py`.
- **No shorting**: Use reverse ETFs instead when needed (avoids margin/borrow complexity)

### Three-Account Live Architecture (post-2026-04-20 A3 retirement)
Uncorrelated factor diversification across 3 Alpaca paper accounts, 1/3 each of total book. A3 is retired but its Alpaca account slot is preserved for future strategy assignment.

- **Account 1 (FIRE 0.1 — Momentum)**: SM + SPY Filter — profits when trends persist. Monthly rebalance.
- **Account 2 (FIRE 0.2 — Trend + Low-Vol)**: 30% Multi-Asset Trend + 70% Low-Vol + vol-scaling — crisis alpha + defensive. Monthly rebalance.
- **Account 3 (FIRE 0.3 — RETIRED 2026-04-20)**: 60% STR + 40% SM. Retired because 40% of its book was literally A1 (structural overlap → A1↔A3 OOS correlation 0.876). Liquidated $99,826.89 all-cash. Slot preserved for future strategy. See `DECISIONS_RESOLVED.md`.
- **Account 4 (FIRE 0.4 — Crypto)**: Crypto Momentum Rotation — top 2 of 9 coins by 21-day momentum, BTC 125d SMA trend filter + vol-scaling. **Daily rebalance** at 00:05 UTC via APScheduler. Parameters picked via `scripts/crypto_robust_opt.py` by maximizing `min(Calmar_half_A, Calmar_half_B)` across 144 configs — regime-robust objective. SMA-125/top2 remains the robust winner post-C2 fix (half A 2.89 / half B 2.94 with strict 125d MA warmup; half B was 3.10 under the old min_periods=1 convention). A4 weight in combined book is **33%** (1/3), with a pre-committed **40% upgrade** once ≥6 months of signal-trading days (not cash-on-filter) confirm live Calmar ≥ 2.0 and A4↔equity correlation ≤ 0.25.

Cross-account correlations (OOS backtest 2023-01-03 → 2026-03-10):
- A1↔A2: **0.38** (backtest) — genuinely diversified
- A1↔A4: 0.10-0.19 — genuinely diversified
- A2↔A4: 0.10-0.19 — genuinely diversified
- (A3 retired — historical correlations preserved in DECISIONS_RESOLVED.md)

**Live correlation panel** (dashboard) shows A1/A2/A4 pairs only. Live A4 pairs currently show "—" because A4 has been all-cash since launch (BTC below 125d MA filter → zero-variance returns make Pearson correlation undefined).

Combined OOS (2023-01-03 → 2026-04-20; equity trading calendar, A4 compounded Fri→Mon, ppy=252; post C1+C2+C4+C6):

- Equity core (A1+A2 at 50/50): **CAGR +19.0%, MaxDD -6.1%, Calmar 3.13** (was 22.3%/−7.7%/2.88 pre-C4+C6)
- 3-account live book (A1+A2+A4 at 1/3 each): **CAGR +26.5%, MaxDD -6.2%, Calmar 4.28** (was 30.3%/−7.0%/4.31 pre-C4+C6)

*C4 moved A2 from 16.9% → 11.0% CAGR (live vol-scaling + cap=1.0 alignment); C6 shaved another 0.1-0.2pp from equities and ~3.4pp from A4 (realistic crypto spread). MaxDD actually improved under vol-scaling + cost-adjusted returns. Calmar on the combined book is essentially unchanged (4.31 → 4.28) — the reduction layers offset each other cleanly.*

A4 weight sweep (OOS 2023-01-03 → 2026-04-20, post C4+C6):
- A4 @ 25% / equity 75%: CAGR +24.6% / MaxDD −5.9% / Calmar **4.21**
- A4 @ 33% / equity 67%: CAGR +26.4% / MaxDD −6.2% / Calmar **4.27** (current)
- A4 @ 40% / equity 60%: CAGR +28.0% / MaxDD −6.5% / Calmar **4.33** (upgrade target)
- A4 @ 50% / equity 50%: CAGR +30.2% / MaxDD −6.9% / Calmar **4.39**

Weight-sweep ordering intact (higher A4 → higher Calmar, monotonic across 25/33/40/50). The 40% upgrade gate (Calmar ≥ 2.0) is cleared with wide margin in backtest.

**Forward-looking haircut on the combined Calmar 4.28:** this number is mathematically correct (low pairwise correlations — A1↔A2 0.32, A1↔A4 0.13, A2↔A4 0.05 — and time-offset drawdowns mean each account's worst day falls on a different date) but probably optimistic for real-money projections. The 3.3-year OOS window is mostly benign (no 2008-style synchronized-bear, no LUNA-style crypto flash crash) and contains two regimes (2023-2024 AI-led US large-cap momentum, mixed crypto) that were generous to our factor mix. Correlations spike in crises — the live 29-day A1↔A3 correlation of 0.84 vs backtest 0.38 is a cautionary example (even acknowledging A1/A3 had structural overlap). Expect a realistic live Calmar closer to **2.5-3.5** over a multi-year period once you account for: (a) one stress-event correlation spike, (b) potential filter whipsaw on A4, (c) C3 survivorship ~1-2pp of A1 CAGR. The 2.0 upgrade gate is conservative by design — 4.28 clears it ~2×, which is the right margin, but don't cite 4.28 as "what we'll realize." The live-tracking clock (reset 2026-04-20) is the only thing that will settle this; expect the gap to show up in the A1↔A2 live correlation first.

Account 4 standalone (OOS 2023-01-03 → 2026-04-20, post C1+C2+C4+C6 + R9 bootstrap):
**CAGR +40.4%, MaxDD -12.7%, Calmar 3.18** (Sharpe 1.76 informational). Block-bootstrap CAGR p5/p50/p95: **+20.9% / +42.9% / +73.6%** (40-day blocks to capture crypto's longer regime autocorrelation per R9; was +25.1% / +45.9% / +74.8% on 20-day blocks which understated autocorr). C6 cost drag on A4 was larger than the audit's 0.5-1pp estimate (actual ~3.4pp) because realized daily turnover on the crypto rotation is ~8% (≈20× annualized one-way) vs the audit's implied ~2×.

Multi-account credentials in `.env` (ALPACA_API_KEY, ALPACA_API_KEY_2, ALPACA_API_KEY_3, ALPACA_API_KEY_4). `AlpacaBroker(account=1|2|3|4)` selects credentials. Account 3 is retired; orders endpoint `_require_active()` guard + validation_gate both block rebalance attempts against it.

Rebalance schedule (two layers — exposure management + signal rotation):
- **Daily at 4:30 PM ET**: Filter monitor checks all active accounts — auto-rebalances if SPY/BTC filter flips (launchd, no server needed). A3 excluded from `ACCOUNT_FILTERS`.
- **Daily at 00:05 UTC**: Account 4 crypto signal rotation — automated via APScheduler (requires server)
- **First Monday of month**: Accounts 1 & 2 momentum/trend signal rotation (manual)
- A3 weekly cadence retired with A3 itself.

**Concurrency (AUDIT_MONTH2.md S1, fixed 2026-04-20):** all three rebalance entry points (API `/rebalance/execute`, APScheduler A4 job, `filter_check.py`) now serialize via `dual_rebalance_lock` (async + file lock) or, for the sync cron path, the same `file_rebalance_lock` they observe. Contention raises `RebalanceLockedError` → 409 from the API, `status="locked"` from the cron. Verified end-to-end — real-money-graduation blocker lifted.

### Strategies — OOS scorecard (live accounts)

**Fresh-data OOS per the CAGR-first framework (test window ends 2026-04-20, post-cache-refresh). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION_PLAN.md`.**

**Load-bearing caveats before trusting these numbers (see AUDIT_MONTH2.md):**
- **C1 (fixed 2026-04-20):** `run_combined_portfolio` migrated from union calendar + fillna(0) + ppy=365 to equity trading calendar with A4 compounded Fri→Mon + ppy=252. Empirical delta ≤ 0.3pp CAGR / 0.05 Calmar.
- **C2 (fixed 2026-04-20):** strict `min_periods=period` on BTC MA warmup. SMA-125/top2 remains the min-Calmar winner.
- **C3:** A1 standalone CAGR is ~1-2pp overstated by S&P 500 survivorship bias (known, documented below).
- **C4 (fixed 2026-04-21):** Live vol-scaling wired via `execution/vol_scaling.compute_live_vol_scalar`; backtest `scalar_cap=1.0` in both live and backtest.
- **C6 (fixed 2026-04-21):** Per-strategy transaction costs applied in backtest via `backtesting/costs.apply_transaction_costs` — 5 bps round-trip for equity (slippage only, Alpaca zero-commission), 20 bps round-trip for crypto (bid-ask spread). A4 drag ~3.4pp (higher than the audit's 0.5-1pp estimate — actual daily turnover is ~8% / ~20× annualized one-way, not ~2×).

| Strategy | Status | CAGR | MaxDD | Calmar | MAR | Sortino | *Sharpe (info)* |
|---|---|---|---|---|---|---|---|
| **Crypto Momentum (Acct 4)** | PASS | **+40.4%** | **-12.7%** | **3.18** | 3.18 | — | *1.76* |
| **Stock Momentum + SPY (Acct 1)** ⚠ C3 | PASS | **+27.2%** | **-9.9%** | **2.76** | 2.76 | 2.10 | *2.04* |
| **Trend + Low-Vol (Acct 2)** | MARGINAL | **+11.0%** | **-7.3%** | **1.51** | 1.51 | — | *1.37* |
| *Reversal + Momentum (Acct 3)* — retired | RETIRED | *14.5%* | *-7.2%* | *2.03* | — | — | — |

A1 + A4 PASS the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates. **A2 is MARGINAL** after the C4 fix (cap 1.5 → 1.0): the old backtest was leveraging the low-vol leg up to 1.5× in calm regimes that live could never realize; the actual live book was always closer to 11%. MARGINAL is allowed for paper per `execution/validation_gate.py`. A4's post-C6 drop (-3.4pp CAGR, -0.68 Calmar) reflects honest transaction-cost accounting on daily crypto rotation.

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
- **Stock Universe**: 501 S&P 500 stocks (cached parquet, survivorship bias noted). Coverage gate is **trailing 500 trading days ≥80% non-NaN** — was previously "≥80% of all days since 2010," which locked out every post-2013 IPO / recent S&P addition. The new gate lets recent adds like VRT and LITE enter the live rotation once they have ~2y of history, without corrupting backtests (pre-IPO NaN rows propagate to NaN ranks → excluded from selection for periods before the ticker existed). Fixed 2026-04-20.
- **Crypto Universe**: 9 coins (BTC, ETH, SOL, BNB, ADA, AVAX, LINK, DOT, XRP)
- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007)
- **BTC 125-day SMA trend filter**: Binary 100% cash when BTC < 125d SMA (sat out all of 2022). Robust-opt picked 125d from 200d/150d/125d/100d grid on 2026-04-18.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 + Account 4, +0.1-0.3 Sharpe improvement
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period
- Strategies in `strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`

### Risk Controls — Operational Behavior

**Time convention — ET is the system reference timezone.** All scheduled times in FIRE are anchored to America/New_York (ET, DST-aware). The equity market runs on ET, and the user is a digital nomad whose laptop local time shifts constantly — laptop-local timezones must never be load-bearing. Same discipline applies to both local (launchd) and cloud (Fly cron) schedulers: `TZ=America/New_York` or `CRON_TZ=America/New_York`, not local time. Enforced at the code layer by `data/trading_dates.py` helpers (`today_et`, `utc_ts_to_et_date`) — use these, don't call `date.today()` or `datetime.now()` directly. The A4 crypto APScheduler job is the only exception and runs at 00:05 UTC (crypto markets are 24/7, so UTC-anchoring is the honest convention there).

**When are filters and circuit breakers checked?**
Risk controls are checked at two levels:

1. **Filter monitor (daily, automated)**: `scripts/filter_check.py` runs via macOS launchd at **4:30 PM ET daily** — even when the server is off. Computes SPY and BTC filter scalars, compares to last-known state in `data/risk_state/filter_state.json`. If a filter flips, **auto-executes rebalances** for affected accounts with full safety rails (circuit breakers, price staleness, file locks). Sends macOS notification. Logs to `data/filter_check.log` with `source="filter_monitor"` in the rebalance journal.

2. **Scheduled rebalance (signal rotation)**: Rotates *which* stocks/assets to hold at the strategy's native cadence:
   - **Account 4** (daily): APScheduler at 00:05 UTC (crypto signal + BTC filter)
   - **Account 3** (weekly): Manual trigger every Monday
   - **Accounts 1 & 2** (monthly): Manual trigger first Monday of month

**Key design: exposure management is decoupled from signal rotation.** The filter monitor handles *how much* to hold (reacts same-day to filter changes). The scheduled rebalance handles *what* to hold (monthly/weekly signal rotation). Backtesting showed this split is critical: daily filter reaction = Sharpe 1.27, monthly lag = Sharpe 0.79 (worse than no filter).

The dashboard's RiskStatusPanel and FilterStatusBanner show current status. FilterStatusBanner also shows the filter monitor's last check time and any recent auto-rebalances.

**Drawdown monitor — two tiers (AUDIT_MONTH2 C5 resolution, 2026-04-21):**

- **-10% dashboard alert** — computed live in `/api/portfolio/risk` from current Alpaca equity + the daily snapshot history. Renders as an amber banner in `RiskStatusPanel`. Not persisted, no push notifications, no heartbeat. Reaction time = next dashboard poll (30s) or next rebalance preview. The SPY/BTC filters + vol-scaling are already de-risking continuously; the alert is a heads-up, not a gate.
- **-35% catastrophe halt** — per-account kill-switch. Latches on first breach seen by either the `/risk` endpoint or a rebalance preview. `POST /api/orders/rebalance/execute` returns **403** while latched; manual reset via dashboard button or `POST /api/portfolio/risk/reset?account=N`.
- **Peak is derived from snapshots, not stored.** `data/snapshots.py` writes one equity row per trading day per account; `compute_drawdown()` takes `max(snapshot_max, current_alpaca_equity)`. Removes the stale-peak failure mode entirely — no matter how long between dashboard visits or rebalances, the peak is always accurate.

**What the -35% threshold is and isn't:**
- Deepest OOS MaxDD observed across live strategies: A1 -9.8%, A2 -7.3%, A4 -11.4%, combined -7.0%. Deepest IS MaxDD: A4 -13.68% (2022 crypto winter, filter trimmed it). -35% sits ~3× deeper than any observed event.
- A test sweep across 16y of IS+OOS confirms **neither -35% nor the old -15% threshold ever fires** in backtest. The old -15% auto-halt was structurally redundant AND empirically inert.
- -10% alert would fire ~3× per 16y per strategy in backtest (A1 Oct-14, A2 Feb-18, A4 Nov-22 + Oct-24) — rare signal, not spam.

**Breaker state** persists to disk (`data/risk_state/circuit_breaker_acct{N}.json`) — schema: `{"halted": bool}`. That's it. Corrupted file → fail-safe `halted=True` until manual reset.

**Backtest parity:** `backtesting/drawdown_halt.py` provides `simulate_drawdown_halt(returns, halt_threshold=0.35)` — a post-hoc halt-and-hold layer. For the -35% threshold it's a no-op on every current strategy's historical returns (sim/live parity exact), but the scaffolding exists for stress-test scenarios or future threshold experiments.

### Architecture
```
# Mode 1: Factor Trading System
data/pipeline.py          — yfinance ETF data download & caching
data/sp500.py             — S&P 500 stock universe + VIX data
data/crypto.py            — Crypto data pipeline (yfinance + symbol mapping)
data/snapshots.py         — Daily equity snapshots (parquet) + Alpaca backfill
data/trading_dates.py     — ET trading-date helpers (today_et, utc_ts_to_et_date) — TZ-stable
data/correlation.py       — Inter-account correlation monitoring (rolling 21-day)
data/plausibility.py      — Per-ticker value-plausibility checks + cross-validation + state (AUDIT_MONTH2 S5 full layer, 2026-04-21)
strategies/base.py        — Abstract strategy interface
strategies/trend_following.py — Time-Series & Multi-Timeframe Momentum
strategies/momentum.py    — Cross-Sectional & Dual Momentum (ETF-based)
strategies/stock_momentum.py — Individual stock momentum + VIX filter
strategies/multi_asset_trend.py — Multi-asset trend following (SPY/TLT/GLD/DBC/EFA)
strategies/low_volatility.py — Low-vol anomaly + momentum quality filter
strategies/mean_reversion.py — Short-term reversal (buy weekly losers)
strategies/crypto_momentum.py — Crypto momentum rotation (21-day, top 3, BTC filter)
strategies/portfolio.py   — Portfolio combiner + SPY/BTC filter + vol-scaling + combined portfolios
backtesting/metrics.py    — Sharpe, drawdown, Kelly, profit factor
backtesting/validation.py — Rolling-OOS + Monte Carlo + regime tests; + walk_forward_refit_analysis (true per-window param refit, added 2026-04-20)
backtesting/bootstrap.py  — Block bootstrap for confidence intervals (VALIDATION_PLAN Test 4)
backtesting/account_adapters.py — Per-account (returns, prices, strategy_fn) bundles for the validation runner
execution/risk_manager.py — Halt-latch + pure `compute_drawdown(account, equity, ...)` helper. State file is `{"halted": bool}` only. Strategy-level breaker + Kelly + 2% rule all removed 2026-04-21 (C5/C7/R12).
execution/notifications.py — Shared macOS notification helper (osascript) used by `scripts/filter_check.py` for filter-change alerts. `FIRE_DISABLE_NOTIFICATIONS=1` silences for tests/headless.
backtesting/drawdown_halt.py — Post-hoc halt-and-hold layer (AUDIT_MONTH2 C5 parity). No-op at -35% across all current strategies.
backtesting/costs.py           — Per-strategy transaction-cost layer (AUDIT_MONTH2 C6). 5 bps equity / 20 bps crypto round-trip; subtracts `bps × turnover` from each day's return. `apply_costs=False` recovers gross returns for calibration runs.
execution/vol_scaling.py  — Live vol-scaling scalar (AUDIT_MONTH2 C4 fix, 2026-04-21). Mirrors backtest `apply_vol_scaling` math on snapshot equity.
execution/validation_gate.py — Rebalance gate; blocks accounts without a passing validation record
execution/alpaca_broker.py — Multi-account Alpaca client (4 paper accounts)
execution/rebalance.py   — Signal-to-order pipeline (target weights → trade list)
execution/rebalance_log.py — Structured JSONL rebalance audit trail
api/main.py              — FastAPI backend (lifespan + APScheduler for daily crypto rebalance)
api/locks.py             — Per-account locks: async (in-process) + file-based (cross-process via fcntl)
api/routes/portfolio.py  — Account summary, positions, equity history, correlation, risk status, filter status
api/routes/orders.py     — Rebalance preview/execute, order history, rebalance journal (?account=1|2|3|4)
api/routes/backtests.py  — Backtest runner (individual + combined + crypto)
api/routes/strategies.py — Strategy list with live metrics
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
dashboard/               — React + Vite + TradingView Charts
scripts/start.sh         — Start backend + frontend (recommended)
scripts/filter_check.py  — Daily filter monitor — auto-rebalances on SPY/BTC filter change
scripts/run_validation.py — VALIDATION_PLAN Tests 1-5 runner; updates data/risk_state/validation_state.json
scripts/crypto_robust_opt.py — Crypto parameter search via min(Calmar_A, Calmar_B); produced SMA-125/top2 production config 2026-04-18
scripts/walk_forward_refit_a1.py — True walk-forward REFIT for A1 Stock Momentum (per-window grid search + OOS eval)
scripts/walk_forward_refit_a2.py — Same for A2 Low-Volatility leg
scripts/com.fire.filter-check.plist — macOS launchd plist (4:30 PM ET daily)

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
- **Frontend only**: `cd dashboard && npm run dev` → http://localhost:5173
- **Validation**: `uv run python3 scripts/run_validation.py --account N` — runs Tests 1-6 (OOS holdout, rolling OOS, parameter stability for crypto, block bootstrap, portfolio fit, walk-forward REFIT). Writes a markdown report + updates `data/risk_state/validation_state.json`. Rebalances on accounts without a `status="pass"` record (and unexpired) return 403. Quarterly re-validation enforced via `expires`. See `VALIDATION_PLAN.md`.
  - Test 6 runs if the adapter defines a `refit_param_grid`; adds ~15-60s per account depending on grid size.
  - Standalone refit explorers: `scripts/walk_forward_refit_a1.py` (StockMomentum) and `walk_forward_refit_a2.py` (LowVolatility leg). Support `--grid small|medium|large`.
  - **Strategy-discovery workflow** — how to evaluate a new candidate strategy instead of copying paper defaults: see `VALIDATION_PLAN.md` → "Test 6 → Recipe for a new candidate strategy" (5-step process: write class → pick grid → run standalone refit → decide → wire into adapter). This replaces the old practice of lifting 15-year-old academic parameters wholesale.
- **Filter monitor**: Runs automatically via launchd at 4:30 PM ET daily (no server needed)
  - Manual run: `uv run python3 scripts/filter_check.py` (or `--dry-run` to check without trading)
  - Check status: `launchctl list | grep fire`
  - View logs: `cat data/filter_check.log` or `cat data/risk_state/filter_state.json`
  - Install: `cp scripts/com.fire.filter-check.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.fire.filter-check.plist`
  - Uninstall: `launchctl unload ~/Library/LaunchAgents/com.fire.filter-check.plist`
- **Validation**: `uv run python3 -c "from backtesting.validation import full_validation; ..."`

### Development Rules
- **Package manager**: Always use `uv` (not pip/poetry/conda). Use `uv run` to execute Python, `uv add` to install packages.
- **Python version**: 3.12 via uv
- **Virtual env**: `.venv/` managed by uv (already set up)
- **Node**: managed by nvm, dashboard uses Vite + React + TypeScript
- **Async endpoints**: All FastAPI `async def` endpoints MUST use `asyncio.to_thread()` for blocking calls (Alpaca API, yfinance downloads, parquet I/O, pandas computations). Calling blocking functions directly freezes the event loop and makes the entire server unresponsive to concurrent requests. This applies to route handlers and scheduled jobs alike.

### Current Phase & Next Steps

**Mode 1 (Structural Alpha):** Post-month-2 audit, 3-account live book (A1+A2+A4) at 1/3 each, A3 retired.
  - Account 1: 15 stocks (SM + SPY Filter) — live since 2026-03-10, OOS CAGR 27.2% (post C4+C6)
  - Account 2: 34 positions (Trend + Low-Vol) — live since 2026-03-10, OOS CAGR 11.0% MARGINAL (post C4+C6)
  - Account 3: RETIRED 2026-04-20. Slot preserved. See `DECISIONS_RESOLVED.md`.
  - Account 4: Crypto Momentum Rotation — daily at 00:05 UTC, SMA-125/top2 robust-opt production, OOS CAGR 40.4%, Calmar 3.18 (post C4+C6). Currently 100% cash (BTC below 125d MA since launch).
  - Live-tracking clock reset to **2026-04-20** — Mar 10 → Apr 17 window was compromised by stale-data bug. A4 33%→40% upgrade clock counts from here (and only counts signal-trading days, not cash-on-filter days).

**Validation status (2026-04-20, fresh-data refresh, CAGR-first framework):** All three active accounts PASS. Results in `data/validation_reports/`, state in `data/risk_state/validation_state.json`. A3 status="retired" — retired accounts are an unconditional block, NO override can bypass them (AUDIT_MONTH2 R2 fix). `execution/validation_gate.py` blocks FAIL/unvalidated; MARGINAL allowed for paper. Overrides (for FAIL/unvalidated/expired only): `FIRE_VALIDATION_OVERRIDE=1` (global) or `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` (scoped to account N). Both surface a WARNING log.

**Known open bugs / fix plan** — see `AUDIT_MONTH2.md` for the ranked list. **Tier 1 fully closed except C3** (C1, C2, C4, C5, C6, C7 all fixed). C3 remains as acknowledged survivorship caveat, week+ of work and only matters pre-real-money. Tier 2 (S1-S5), Tier 3 (D1-D4), Tier 4 R1/R3/R11/R12/R16 all resolved; remaining R-items are low-priority hygiene. C4 fix (2026-04-21, option B): live vol-scaling via `execution/vol_scaling.compute_live_vol_scalar`, `scalar_cap=1.0` in both live and backtest for sim/live parity; A2 dropped PASS → MARGINAL (still allowed for paper), A4 remains PASS. **Tier 2 S1-S4 all fixed 2026-04-20**; **S5 fully resolved 2026-04-21** — `data/plausibility.py` adds per-ticker value-plausibility bands + write-time assertions + read-time cache-vs-live cross-validation on `/filters`; state surfaced via `/api/portfolio/plausibility` + red warning banner in `FilterStatusBanner.tsx`. What started as "one ticker defended" (inline BTC check 2026-04-21 morning) is now a full defensive layer across BTC/ETH/SPY/VIX/SHY. **Tier 3 D1-D4 all fixed 2026-04-20**. **Tier 4 R11 fixed 2026-04-21** — `check_price_staleness` now flags unfetchable symbols as drifted with `reason="unfetchable"` instead of silently skipping; unit-tested. Tier 4 R2-R9 remain open — none block paper or real-money operation.

**Sharpe is explicitly deemphasized.** The prior framework used OOS Sharpe ≥ 1.0 as the gate, which is the wrong objective function for a 3-5 year wealth compounder (Sharpe penalizes upside vol and normalizes absolute return magnitude). Sharpe is still shown on reports as informational context but is not gated on. Primary gates are CAGR + MaxDD + Calmar. See `VALIDATION_PLAN.md` for rationale.

**Mode 2 (Informational Alpha):** Phase A in progress — research infrastructure built, first weekly analysis running.
  - **Built 2026-04-15**: PEAD data pipeline (`mode2/`), transcript scraper, scoring prompts, recommendation tracker
  - **Data sources**: Finnhub (EPS surprise, free), Insider Monkey (transcripts, free scraping), yfinance (prices)
  - **Week 1 analysis (2026-04-15)**: 6 companies analyzed (JPM, GS, C, WFC, BLK, JNJ), 1 long recommendation (C, conviction 4/5), 5 skips. BAC (+8.6%), MS (+10.9%), PNC (+5.5%) reported same day — transcripts pending.
  - **Paper tracking**: C long at $131.69, stop $125, target $138, 40-day hold. All paper — no real money until Month 2 (June) per PLAN_MODE2.md.
  - **Key learning**: Large-cap PEAD drift is 1-3% (not 5-8% as in academic literature which skews small-cap). Best PEAD opportunities will be mid-caps with less analyst coverage in weeks 2-4 of earnings season.

**Dashboard infrastructure** (unchanged from Mode 1 build):
- 5-tab account switcher, live equity charts, correlation monitor, Backtests with grouped strategy panel
- All components `React.memo` optimized, no loading gates on background polls
- Data caching: ETF/SPY/S&P500/VIX/crypto parquets with staleness checks
- Daily equity snapshots, Alpaca backfill, circuit breaker monitoring, filter status
- Rebalance UI: preview → confirm → execute, action-classified orders, per-account locks
- Filter monitor: `scripts/filter_check.py` via launchd at 4:30 PM ET daily
- Ticker mapping: yfinance hyphens → Alpaca dots via `to_alpaca_equity_symbol()`
- Snapshot data quality: Alpaca backfill writes NaN for cash/positions — don't treat as zero

**Next steps:**
- **Mode 1 priority:** Tier 1 fully closed except C3 survivorship (C1, C2, C4, C5, C6, C7 all fixed). Tier 2 (S1-S5) + Tier 3 (D1-D4) + Tier 4 (R1, R3, R11, R12, R16) all fixed. **C6 resolved 2026-04-21** — per-strategy transaction costs in backtest via `backtesting/costs.py` (5 bps equity round-trip, 20 bps crypto round-trip); A4 drag came in at 3.4pp (vs audit's 0.5-1pp estimate) due to higher-than-assumed rotation frequency; all three accounts still PASS/MARGINAL. Combined headline re-issued: 3-acct @ 1/3 is **26.5% CAGR / -6.2% MaxDD / Calmar 4.28** OOS. Tier 4 R2, R4-R10, R13-R15 reporting hygiene remain as lower-priority cleanup.
- **Find/build a new Account 4-class strategy** — user's directive 2026-04-18: current crypto account is acceptable baseline but not extraordinary. Target: OOS CAGR and Calmar that meaningfully exceed the existing single-account results. Funding-rate carry on perps was explored and shelved (infra + exchange risk). Open research vectors: rate vol (see `RATE_VOL_SCOPE.md`), commodity vol, narrative-aware crypto.
- Mode 1: Add dashboard banner showing validation status per account (reads `data/risk_state/validation_state.json`).
- Mode 2: Analyze BAC/MS/PNC transcripts (pending Insider Monkey), continue weekly PEAD analysis through Q1 earnings season.
- Mode 2: Build weekly report generator (markdown output stored in `data/mode2/reports/`).
- Mode 2: Track C recommendation for 40 days (check price by 2026-05-25).
