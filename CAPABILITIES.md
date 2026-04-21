# FIRE — System Capabilities Brief

*A standing overview of the system's design, validation discipline, and honest limits. Intended for a sophisticated reader (LP, operator, future-self) who wants to understand what was built, what it does, what makes it credible, and what it deliberately isn't.*

**Last updated:** 2026-04-21
**Status:** Paper-first operational since 2026-03-10 across 3 active Alpaca accounts.
**Live-money graduation gated on:** (a) resolution of C3 (point-in-time S&P 500 constituents, pre-real-money), (b) Phase 0 deployment refactor per [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md), (c) ≥6 months of signal-trading-day evidence from live paper.

---

## Executive summary

FIRE is a multi-strategy systematic trading system operating 3 paper accounts on Alpaca (equity momentum, equity trend + low-vol, crypto momentum rotation). It was designed with **paper-first discipline**: every strategy is validated OOS against pre-committed thresholds before trading; the backtest models the same transaction costs, vol-scaling constraints, and drawdown logic the live book actually executes; and an enforcement gate blocks trading on un-validated accounts. The system is solo-built but operates at a rigor level typical of a small quant shop or sophisticated family office, with a few elements (sim/live parity verification, per-ticker data plausibility guards, pre-committed research thresholds) that exceed that tier. It is not a professional hedge fund stack — point-in-time constituents, execution algos, margin infrastructure, and regulatory compliance are all out of scope by design.

---

## What the system is

**Two-mode architecture** (see [PLAN_MODE2.md](PLAN_MODE2.md)):

- **Mode 1 — Structural alpha.** Factor-diversified multi-strategy book. Academic basis: Faber (2007) tactical asset allocation, Moreira & Muir (2017) vol-managed portfolios, Barroso & Santa-Clara (2015) vol-scaled momentum. Live today.
- **Mode 2 — Informational alpha.** Post-earnings-announcement-drift pipeline with transcript scoring. Research paused 2026-04-18 after Breakthrough #1 failed (see [HUNT_APR2026.md](HUNT_APR2026.md)). Infrastructure preserved; directional thesis (Claude-as-single-name-filter) disproven.

**Three-account live book** (post-2026-04-20 A3 retirement, per [DECISIONS_RESOLVED.md](DECISIONS_RESOLVED.md)):

- **Account 1 — Momentum.** Top-15 S&P 500 momentum + SPY 200d trend filter. Monthly rebalance.
- **Account 2 — Trend + Low-Vol.** 30% multi-asset trend + 70% low-vol + vol-scaling overlay. Monthly rebalance.
- **Account 4 — Crypto.** Top-2-of-9 crypto momentum + BTC 125d SMA filter + vol-scaling. Daily rebalance at 00:05 UTC via APScheduler. Weight currently 33% of combined book, with a pre-committed upgrade plan to 40% (manual decision framework, gates on live evidence).

---

## Current headline numbers

OOS window 2023-01-03 → 2026-04-20, post all 7 Tier-1 audit fixes (C1, C2, C4, C5, C6, C7 + C3 caveat):

| Book | CAGR | MaxDD | Calmar | Sharpe (info) |
|---|---|---|---|---|
| A1 Momentum | +27.2% | -9.9% | 2.76 | 2.04 |
| A2 Trend + Low-Vol | +11.0% | -7.3% | 1.51 | 1.37 |
| A4 Crypto | +40.4% | -12.7% | 3.18 | 1.76 |
| **Equity core (A1+A2 @ 50/50)** | **+19.0%** | **-6.1%** | **3.13** | 2.16 |
| **3-acct book (A1+A2+A4 @ 1/3)** | **+26.5%** | **-6.2%** | **4.28** | 2.57 |

Block-bootstrap CAGR p5 / p50 / p95 for A4 (40-day blocks, regime-appropriate for crypto): **+20.9% / +42.9% / +73.6%**.

**Forward-looking haircut — read before citing.** The 3.3-year OOS window is mostly benign (no 2008-style synchronized bear, no LUNA-style flash crash). Correlations in crises spike toward 1; the backtest sample doesn't contain that. A1 standalone is 1-2pp overstated by S&P 500 survivorship. Realistic live Calmar over a multi-year period: **2.5-3.5** for the combined book, not 4.28. The 2.0 upgrade gate for A4 weight expansion is deliberately conservative for this reason. See [CLAUDE.md](CLAUDE.md) "Strategies — OOS scorecard" for full caveat list.

---

## Capability stack

### Data layer (production-grade)

- **Six price pipelines** (ETF universe, S&P 500, SPY filter cache, VIX, crypto universe, BTC) with TTL caches (16-24h), atomic tmp-rename writes, and exponential-backoff retry at the downloader.
- **Per-ticker value-plausibility layer** ([data/plausibility.py](data/plausibility.py)) — hard `(min, max)` bands for BTC/ETH/SPY/VIX/SHY with cited rationale, wired into every `download_*` before write, plus read-time cross-validation against Alpaca live quotes on the `/filters` endpoint. Catches the "structurally valid but semantically wrong" failure mode (e.g., yfinance returned a 4099-row series under "BTC-USD" with values in the $9-$29 range — observed 2026-04-21, defended same-day).
- **S&P 500 constituent list** with 7-day TTL auto-refresh from Wikipedia + stale-cache fallback. Coverage gate is trailing-500d ≥80% non-NaN (allows recent IPOs to enter live rotation once they have ~2y history).
- **ET-anchored trading-date helpers** ([data/trading_dates.py](data/trading_dates.py)) — `today_et()`, `utc_ts_to_et_date()`, `zoneinfo`-based. TZ-stable across local (ET laptop) and cloud (UTC Fly) servers.
- **Daily equity snapshots** per account (parquet) with cross-process-safe read-modify-write (fcntl file lock).

### Strategy layer

- **10 strategies** across 3 universes: 18 ETFs + SHY, 501 S&P 500 stocks, 9 liquid coins.
- **Signal → weights API** ([strategies/base.py](strategies/base.py)) — every strategy exposes `generate_signals(prices) → weights DataFrame` and inherits `generate_returns` from base, with `signals.shift(1) × asset_returns` convention (no forward-look).
- **Equal-weight top-N + blend combiners** with SPY 200d trend filter (Faber 2007: half exposure below MA) and BTC 125d SMA filter (binary cash below MA; parameter picked by robust-opt via `min(Calmar_half_A, Calmar_half_B)` across a 144-config grid, not naive Sharpe-max).
- **Vol-scaling overlay** (Moreira-Muir 2017) — EWMA realized-vol inverse, target 15% vol, scalar bounded [0.1, 1.0] for crypto / [0.5, 1.0] for equity. Applied in both backtest AND live with math verified to match within 1e-6 on 10 days of A2 snapshot history (C4 sim/live parity work, 2026-04-21).

### Backtest + validation layer

- **Full scorecard metrics** ([backtesting/metrics.py](backtesting/metrics.py)) — CAGR, MaxDD, Calmar, MAR, Sterling, Burke, Pain, Ulcer, UPI, Sortino, Omega, gain-to-pain, time underwater, max recovery days, Kelly criterion (diagnostic only, not wired to sizing).
- **Six-test validation framework** ([scripts/run_validation.py](scripts/run_validation.py), gate in [execution/validation_gate.py](execution/validation_gate.py)):
  1. OOS holdout (train 2010-2022, test 2023-today).
  2. Rolling OOS with fixed parameters.
  3. Parameter stability across half-A / half-B splits (crypto only).
  4. Block bootstrap CAGR percentiles (asset-appropriate block size: 40d crypto, 20d equity, per R9 fix).
  5. Portfolio fit — satellite marginal contribution vs equity core.
  6. Walk-forward REFIT vs defaults (added 2026-04-20, non-gating; A1 + A2 both PASS — literature defaults are within noise of refit winners).
- **Pre-committed thresholds**: OOS CAGR ≥ 15%, OOS MaxDD ≥ -40%, OOS Calmar ≥ 1.0, OOS/IS CAGR ratio ≥ 70%. Quarterly expiry enforced via gate (expired records block new rebalances).
- **Transaction-cost layer** ([backtesting/costs.py](backtesting/costs.py)) — per-strategy cost rates (5bps round-trip equity, 20bps round-trip crypto), turnover-weighted via `sum(|Δw|)/2 × bps/10000`. Applied to every backtest path including validation adapters' strategy_fn and refit_factory closures.
- **Halt simulation layer** ([backtesting/drawdown_halt.py](backtesting/drawdown_halt.py)) — post-hoc halt-and-hold simulator for sim/live parity on the -35% catastrophe kill-switch. Empirically a no-op on all current strategies across 16y IS+OOS (deepest observed MaxDD is A4 -13.68%; halt never fires).

### Execution + risk layer

- **Multi-account Alpaca broker** ([execution/alpaca_broker.py](execution/alpaca_broker.py)) — selects credentials via `AlpacaBroker(account=1|2|3|4)`. Active-account guard + validation gate guard enforced at preview and execute.
- **Signal → order pipeline** ([execution/rebalance.py](execution/rebalance.py)):
  - Tradeability check against new target symbols (catches delisted / acquired).
  - Price staleness guard (re-fetches prices after weight computation; blocks at >2% drift; flags unfetchable symbols as drifted with `reason="unfetchable"`).
  - Sell-before-buy ordering so buys have freed cash.
  - Fractional crypto rounding (8 decimals; Alpaca minimum).
  - yfinance↔Alpaca ticker translation (hyphens → dots for share classes like BF.B, BRK.B).
  - Strategy-weight invariant checks (sums to ≤ 1.0, no negative weights, no individual weight > 1.0).
- **Concurrency safety** ([api/locks.py](api/locks.py)) — `dual_rebalance_lock` combines in-process `asyncio.Lock` and cross-process fcntl file lock in one async context manager. All three rebalance entry points (API `/rebalance/execute`, APScheduler A4 job, cron `filter_check.py`) serialize through it. Contention returns 409 from the API and `status="locked"` from the cron.
- **Atomic writes** ([data/pipeline.py:write_parquet_atomic](data/pipeline.py)) — tmp-file + `os.replace` across all 7 live-path parquet writes (ETF cache, SP500, crypto universe, BTC, VIX, snapshot save, snapshot backfill).
- **Try/finally around execute** in all three call sites — the rebalance journal survives mid-flight raises; partial order results are captured alongside an `execute_error` field so no audit trail is silently lost.
- **Drawdown monitor** ([execution/risk_manager.py](execution/risk_manager.py)) — two-tier:
  - **-10% alert** (dashboard banner, non-blocking). Derived live from the daily snapshot history + current Alpaca equity, so the "peak" is always accurate regardless of rebalance or dashboard cadence.
  - **-35% catastrophe halt** (manual reset required, audit-journaled). Latches a single persisted boolean; the endpoint, APScheduler, and cron all refuse to trade while latched. Calibrated so it never fires on 16y of IS+OOS backtest across any live strategy — a "something every other layer missed" backstop, not a routine-DD gate.

### Automation + monitoring

- **APScheduler** for daily A4 crypto rebalance at 00:05 UTC (runs in FastAPI lifespan; dual_rebalance_lock).
- **macOS launchd** ([scripts/filter_check.py](scripts/filter_check.py), [scripts/com.fire.filter-check.plist](scripts/com.fire.filter-check.plist)) for 4:30 PM ET daily filter monitor. Runs even when the server is off. Detects SPY/BTC filter flips and auto-rebalances affected accounts with all safety rails active (validation gate, locks, staleness guard, halt check). macOS notifications on state changes.
- **Strategy-discovery workflow** — new candidates get evaluated via the same six-test framework before going live. Never "trust the paper defaults."

### Dashboard + audit trail (React + TypeScript + TradingView Charts)

- **5-tab account switcher** (Combined + 4 individual views).
- **Live equity curves** per account + combined, with SPY benchmark overlay.
- **Correlation panel** — rolling 21-day, per-pair, with alerts when correlation exceeds backtest-expected bands.
- **Backtest runner** with grouped strategy panel (Live / Portfolio Blends / Building Blocks / Solo + Filter). Returns IS / OOS splits with a visual train/test cutoff marker.
- **Rebalance UI** — preview → confirm → execute with action-classified orders (new / increase / decrease / exit). Displays SPY/BTC filter scalars and vol scalar alongside target weights.
- **Risk status panel** — three visual states (green OK with thresholds shown / amber alert active / red catastrophe halt with reset button).
- **Filter status banner** — SPY and BTC price vs MA, last filter check time, recent auto-rebalances. Red plausibility warning banner when data quality issues are flagged.
- **Rebalance history** — expandable per-event order details.
- **Structured JSONL journal** ([execution/rebalance_log.py](execution/rebalance_log.py)) — per-event timestamp, account, strategy, portfolio value, orders submitted/failed, SPY/BTC filter scalars, vol scalar + diagnostics, execute_error, source attribution (manual / scheduled / filter_monitor / halt_reset).
- **4 persistent state files**: `validation_state.json`, `filter_state.json`, `plausibility_state.json`, `circuit_breaker_acct{N}.json`. All atomic writes, all versioned schemas.

### Test suite

**90 tests** across 8 modules: plausibility (17), validation gate (14), risk manager (14), rebalance mechanics (11), strategies (11), vol scaling (6), drawdown halt sim (6), costs (7), rebalance log (4). Full suite runs in <1s.

---

## What distinguishes this from the typical retail quant stack

Concretely: things here that most solo / small-team setups don't do.

- **Explicit sim/live parity verification.** Most small setups assume backtest math matches live — and it usually doesn't. Here: C4 (live vol-scaling matches backtest within 1e-6), C6 (per-strategy transaction costs in backtest at rates calibrated to Alpaca's actual fee structure), C5 (drawdown-halt semantics modeled in both paths), C7 (strategy-produced weights flow directly to dollar-sizing, no clamping).
- **Validation enforcement that can't be hand-waved.** Most retail setups let the researcher override their own gates in practice. Here: `FIRE_VALIDATION_OVERRIDE=1` is logged as a warning, scoped per-account, and **cannot** bypass retired status. The override exists; the friction is real.
- **Semantic data-quality guards, not just coverage checks.** Most shops check "did yfinance return a DataFrame?" Here: per-ticker plausibility bands with cited reasons ("BTC has not closed below $1k since Dec 2017"), cross-validation against a live broker quote on reads, persistent state + dashboard banner. Catches the "looks right, is wrong" class of bug that usually only surfaces after production loss.
- **Pre-committed research thresholds.** Breakthrough #1 was killed honestly (-1.68%/month excess, not moved to -0.5% by goalpost-shifting). That discipline exposed the in-sample-tuned Sharpe discovery that triggered the entire month-2 audit.
- **Adversarial review as SOP.** The month-2 audit had three independent adversarial reviewers find 20+ bugs in a system that was passing all its own tests. That's the standard operating procedure for a real quant shop; most solo traders skip it.
- **Audit-trail completeness.** Rebalance journal captures filter scalars, vol scalar, diagnostics, execute errors, and source. Halt resets get journaled as their own event type. Post-hoc "what happened on day X" is a single parquet read.

---

## Honest limitations — what this system is NOT

- **Not point-in-time in its equity universe.** The S&P 500 backtest uses today's constituent list, not the as-of-date list. A1 standalone CAGR is ~1-2pp overstated by survivorship bias. Fix requires CRSP or Kenneth French data and ~week of work; deferred until pre-real-money gate. Documented caveat on every A1 CAGR citation.
- **Not a real-money system yet.** Paper-first discipline is deliberate. Live-money graduation gated on C3 resolution + Phase 0 cloud deployment + ≥6 months of live paper evidence.
- **No execution algos.** Market orders only. Fine at a $50k book; wrong at a $50M book. No VWAP / TWAP / implementation shortfall / liquidity-seeking logic. Not required at scale but worth flagging.
- **No formal factor-risk model.** No Barra / Axioma attribution. No sector-level risk decomposition. The strategies' implicit factor exposures (momentum, low-vol, trend) are documented but not decomposed into a formal risk model.
- **No margin / leverage infrastructure.** Alpaca paper is spot-only. Backtest and live both capped at 1.0× exposure (no margin). Future research vector (`scalar_cap > 1.0` via CME micros / Coinbase Advanced / equity Reg-T margin) is scoped but not built.
- **No prime brokerage / compliance / regulatory reporting.** Not relevant at current scale; would be a rebuild at institutional scale.
- **No sub-second market data.** End-of-day cadence only. Correct for monthly / daily rebalance strategies; wrong if you're doing intraday.
- **Sample size is short** for strategies running on crypto. A4's OOS window is 3.3 years; statistical confidence on the Calmar claim is meaningful but not deep. Block-bootstrap p5 of +20.9% is our honest downside estimate.
- **No auto-disaster-recovery.** State files are on a single local disk (laptop). Fly.io migration (Phase 0 deployment) is the remedy; not yet started.

---

## How we know the system is robust

Three lines of evidence:

1. **[AUDIT_MONTH2.md](AUDIT_MONTH2.md)** — an adversarial review surfaced 20+ latent bugs across Tier 1 (headline numbers), Tier 2 (concurrency + safety), Tier 3 (data correctness), and Tier 4 (reporting hygiene). 95% closed as of 2026-04-21. The remaining 5% is C3 survivorship (disclosed, pre-real-money) and low-severity hygiene. Every fix has a commit, a test, and a docstring citation.

2. **[HUNT_APR2026.md](HUNT_APR2026.md)** (formerly BREAKTHROUGH.md) — two proposed strategy breakthroughs were tested under pre-committed thresholds. Both were killed honestly. The discipline of accepting those negative results is what surfaced the in-sample-tuned Sharpe problem that triggered the audit. Kill discipline > alpha claim.

3. **[VALIDATION_PLAN.md](VALIDATION_PLAN.md)** — all three active accounts carry a current validation record with a pass/marginal status and a quarterly expiry. The gate refuses to trade on un-validated accounts, refuses override bypass on retired accounts, and logs warnings when override is active. This isn't a policy document — it's enforced code.

---

## What this would have taken historically

**Team composition** for equivalent scope: 1 quant researcher + 1 backend engineer + 1 frontend engineer + 1 data engineer + 1 DevOps/SRE = 4-5 people.

**Time estimate:**
- Strategy + backtest framework: 2-3 months.
- Data layer + quality guards: 2-3 months (the plausibility layer is the kind of defensive code teams only add after getting burned; proactively built here).
- Execution + risk: 2-3 months.
- Validation framework with enforcement: 1-2 months.
- Dashboard: 2-3 months.
- Sim/live parity audit + fixes: 1-2 months of a senior quant's time typically — and most teams find these issues in production, not in audit.

**Total: 10-14 months initial build; 18-24 months to reach the sim/live parity + audit discipline currently in place.**

**Fully-loaded engineering cost** (US market, $200-300k/year per head): **$1.0M-$2.0M** for a year of work across that team.

This system was built solo with AI tooling over ~2 months of part-time work. The mechanical acceleration from AI is real, but the *direction* — which bug is load-bearing, which caveat is worth disclosing on the headline, which "fix" is a commitment device vs a real change, when to kill a thesis — is human. That's the harder half.

---

## Peer comparison bracket

| Level | Example | Our system's position |
|---|---|---|
| Retail Python backtester (PyPortfolioOpt, Zipline notebook) | Hobbyist quant | **Well above.** They don't have sim/live parity, validation enforcement, or atomicity. |
| Small quant shop / sophisticated family office | 3-5 people running systematic strategies | **Roughly peer.** Exceeds on sim/live parity + data plausibility + research discipline; below on execution infra + formal risk models. |
| Sophisticated quant research group | 10-20 person team at a multi-strat fund | **Meaningfully below** on infrastructure surface area (exec algos, factor models, compliance, disaster recovery). Roughly peer on validation rigor. |
| Top-tier quant shop | Renaissance / Two Sigma / Citadel | **Different category.** Sub-millisecond execution, proprietary signals, 30+ PhD research staff, dedicated compute clusters. Not a comparable bar. |

**Appropriate framing:** small-quant-shop / sophisticated family-office tier, with research and sim/live parity discipline that exceeds most of that bracket. Correct bar for a solo trader running a bridge-to-retirement book with paper-first rigor.

---

## Roadmap

**Pre-real-money hardening (must-do):**
- **C3** — point-in-time S&P 500 constituents (CRSP / Kenneth French). Resolves the survivorship caveat on A1. ~week of work.
- **Phase 0 deployment refactor** per [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) — Fly.io migration precondition. Bug-hunt window is now closed; this is the right time.
- **≥6 months of signal-trading days** in live paper with Calmar ≥ 2.0 and A4↔equity correlation ≤ 0.25 (A4 upgrade gates).

**Strategic research vectors (pick-based-on-appetite):**
- **New A4-class strategy.** Rate vol ([RATE_VOL_SCOPE.md](RATE_VOL_SCOPE.md)), commodity vol, narrative-aware crypto (Candidate B from HUNT_APR2026), macro liquidity overlay (Candidate C, FRED-based, no Claude dependency).
- **Mode 2 revival** — only after a new hypothesis that isn't "Claude as single-name filter" (disproven). Cross-transcript industry synthesis remains architecturally interesting but is a months-out bet.
- **Dashboard validation-status banner** — low priority; currently a mental-model problem solved by the operator.

**Low-priority hygiene (Tier 4 audit items remaining):**
- R6 (correlation sample mismatch in portfolio-fit diagnostic).
- R7 (Sterling ratio partial-year).
- R8 (OOS/IS threshold gameable by moving TRAIN_END).
- R10 (CVR regex future-proofing).
- R13-R15 (doc footnotes on parity gotchas).

None block paper or real-money operation.

---

## Deep-dives

Everything above is a summary. For the primary sources:

- **[CLAUDE.md](CLAUDE.md)** — current operational state, architecture map, scorecard table, running next-steps list.
- **[PLAN.md](PLAN.md)** — original project plan, research roadmap, academic references.
- **[PLAN_MODE2.md](PLAN_MODE2.md)** — two-mode architecture strategic framing.
- **[VALIDATION_PLAN.md](VALIDATION_PLAN.md)** — CAGR-first validation framework, thresholds, gate logic.
- **[AUDIT_MONTH2.md](AUDIT_MONTH2.md)** — month-2 adversarial review, bug catalog, per-finding resolution.
- **[DECISIONS_RESOLVED.md](DECISIONS_RESOLVED.md)** — portfolio-architecture decisions (A3 retirement, A4 weight + upgrade plan).
- **[HUNT_APR2026.md](HUNT_APR2026.md)** — April 2026 breakthrough hunt archive (both hypotheses falsified, cascade into the audit).
- **[SDD.md](SDD.md)** — Software Design Decisions (patterns, lessons learned).
- **[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** — Fly.io migration plan, phased rollout.
- **[RATE_VOL_SCOPE.md](RATE_VOL_SCOPE.md)** — candidate A4-class strategy scoping.

---

## Closing frame

FIRE is a legitimate small-quant-shop-tier systematic trading system built solo on a bridge-to-retirement horizon. Its strongest edge is not any particular strategy — it's the discipline layer: pre-committed thresholds, enforced validation gates, sim/live parity verification, and willingness to kill hypotheses honestly. That discipline built the system; it's what will make the eventual real-money graduation honest; and it's what will catch the next load-bearing bug before it matters.
