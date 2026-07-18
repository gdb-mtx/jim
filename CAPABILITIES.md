# FIRE — System Capabilities Brief

*A standing overview of the system's design, validation discipline, and honest limits. Intended for a sophisticated reader (LP, operator, future-self) who wants to understand what was built, what it does, what makes it credible, and what it deliberately isn't.*

> **Status (2026-07-18, post build-out week):** The July sessions retired A4 (edge decay + bug-era drag), killed the entire public-event research family on fresh data, and redirected the breakthrough into **sizing engineering**: A1 book-level vol-scaling (OOS 25.3%→31.2%) + A2 cap=1.5 restoration (11.0% MARGINAL→16.8% PASS) ≈ +4pp validated book CAGR at equal-or-better Calmar. The book also gained a sensory layer (VIX tail signal + 5-sensor macro composite, alert-only) and a live crisis-alpha experiment (VIXY tail-leg paper pilot in A3). BOOK_SHAPE gaps: regime adaptivity CLOSED, crisis alpha in live pilot, non-price edge dead on free data. The full verdict ledger is the `AUDIT_FABLE.md` banner.

**Last updated:** 2026-07-18 (full refresh).
**Status:** Paper-first operational since 2026-03-10. Live book = A1 + A2 (A3 retired 2026-04-20, hosts the tail pilot; A4 retired 2026-07-13).
**Live-money graduation gated on:** (a) Q3 checkpoint — A1 clean-window alpha ≥ 0 vs SPY over 2-3 rebalance cycles with the 07-18 configs (`scripts/live_scorecard.py` is the evidence engine), (b) Fly.io deploy per [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) (deferred by George until live evidence justifies the spend), (c) C3 handled by a ~1-2pp expectation haircut on A1 (Norgate declined 2026-07-18).

---

## Executive summary

FIRE is a multi-strategy systematic trading system operating 2 live paper accounts on Alpaca (equity momentum, equity trend + low-vol — both vol-managed with calm-regime extension to 1.5× via Reg-T margin) plus an automated VIXY tail-hedge paper pilot in a third account. It was designed with **paper-first discipline**: every strategy is validated OOS against pre-committed thresholds before trading; the backtest models the same transaction costs, vol-scaling constraints, and drawdown logic the live book actually executes; and an enforcement gate blocks trading on un-validated accounts. The system is solo-built but operates at a rigor level typical of a small quant shop or sophisticated family office, with a few elements (sim/live parity verification, per-ticker data plausibility guards, pre-committed research thresholds) that exceed that tier. It is not a professional hedge fund stack — point-in-time constituents, execution algos, margin infrastructure, and regulatory compliance are all out of scope by design.

---

## What the system is

**Two-mode architecture** (see [PLAN_MODE2.md](docs/research/PLAN_MODE2.md)):

- **Mode 1 — Structural alpha.** Factor-diversified multi-strategy book. Academic basis: Faber (2007) tactical asset allocation, Moreira & Muir (2017) vol-managed portfolios, Barroso & Santa-Clara (2015) vol-scaled momentum. Live today.
- **Mode 2 — Informational alpha.** Post-earnings-announcement-drift pipeline with transcript scoring. Phase A in progress: pipeline live (Finnhub EPS + Insider Monkey transcripts + scoring prompts + recommendation tracker). Original Claude-as-single-name-filter thesis disproven 2026-04-17 (see [HUNT_APR2026.md](docs/archive/HUNT_APR2026.md)); current PEAD work uses scoring on real transcripts, not Claude as filter. Week 1 (2026-04-15): 6 companies analyzed, 1 long recommendation tracked through 2026-05-25.

**Two-account live book + pilot** (A3 retired 2026-04-20; A4 retired 2026-07-13 — see HISTORY.md):

- **Account 1 — Momentum.** Top-15 S&P 500 momentum + SPY 200d trend filter + book-level vol-scaling (15% target, cap 1.5, added 2026-07-18 — recaptures the diversification benefit that per-name vol targeting discarded). 21-trading-day rebalance.
- **Account 2 — Trend + Low-Vol.** 30% multi-asset trend + 70% low-vol + vol-scaling at its original validated cap=1.5 (restored 2026-07-18). 21-trading-day rebalance.
- **Account 3 — tail-leg pilot host.** Retired as a strategy account; since 2026-07-18 auto-executes the VIXY tail hedge (5% of book) on VIX9D/VIX3M ≥ 1.10 (`execution/tail_leg.py`). Paper evidence for the Q4 real-money-tail decision.
- **Account 4 — retired 2026-07-13.** Was crypto momentum. Shadow-tracked on every `live_scorecard.py` run (reopen threshold: shadow > +10% since retirement).

---

## Current headline numbers

OOS window 2023-01-03 → present, revalidated 2026-07-18 with the current configs:

| Book | Status | CAGR | MaxDD | Calmar | Bootstrap p5 |
|---|---|---|---|---|---|
| A1 Momentum + book vol-scaling ⚠ C3 | PASS | +31.2% | -11.0% | 2.84 | +15.3% |
| A2 Trend + Low-Vol (cap 1.5) | PASS | +16.8% | -10.8% | 1.56 | +11.5% |
| **Live book (A1+A2 @ 50/50)** | — | **+24.1%** | **-8.7%** | **2.77** | — |

A1's bootstrap p5 (+15.3%) clears the 15% CAGR gate outright — the 5th-percentile path passes on its own. Overlay parameters are robust, not fitted: an 18-config sensitivity grid holds Calmar in a flat 2.62-2.84 band; the vol target is a risk dial (0.12→24.5%/-8.9% … 0.18→36.5%/-13.3%).

**Forward-looking haircut — read before citing.** The OOS window is mostly benign (no 2008-style synchronized bear). Correlations in crises spike toward 1. A1 standalone is ~1-2pp overstated by S&P 500 survivorship (C3 — handled by haircut, Norgate declined). Backtests model no margin interest — at ~8% real-money rates the calm-regime extension gives back ~1-2pp when fully deployed (paper pays none). Live evidence to date: A1 execution parity clean (+0.1pp/60d); the clean-window record *lags SPY* pre-upgrade — the Q3 checkpoint judges the upgraded configs. Realistic live Calmar: **~2**, not 2.77.

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
- **Vol-scaling overlay** (Moreira-Muir 2017) — EWMA realized-vol inverse, target 15% vol, scalar bounded **[0.5, 1.5] on equity accounts** (cap raised 2026-07-18; >1.0 extends into Reg-T margin, confirmed live at the broker — the old "Alpaca paper is spot-only" claim was true only for crypto, which stays clamped at 1.0). Levered targets require a margin account (multiplier ≥ 2) and log Reg-T buying power; weight-sum invariant allows gross up to the configured cap. Applied in both paths with math verified to match within 1e-6 on A2 snapshot history (C4 work, 2026-04-21). **Why vol-scaling instead of Kelly for sizing:** Kelly requires reliable forward-looking expected returns per position — our factor signals (momentum rank, trend filter) tell us *which* assets to hold, not *how much we expect to earn* from each. Vol-scaling is mathematically the reduced-form Kelly under the empirical finding (Moreira & Muir) that expected returns don't scale with volatility for momentum factors — it captures the time-varying exposure adjustment without needing the return estimate that Kelly can't get right. Our 15% vol target is roughly quarter-Kelly (full Kelly for a Sharpe-1.76 strategy implies 176% vol target), which is where practitioners land after discounting for estimation uncertainty and fat tails (Barroso & Santa-Clara 2015). Kelly stays in the scorecard as a diagnostic for "is this strategy worth sizing into at all."

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
  - Strategy-weight invariant checks (sums to ≤ the configured vol-scaling cap — 1.5 on the live equity accounts, 1.0 otherwise; no negative weights; loud failure above; margin-account guard on levered targets).
- **Concurrency safety** ([api/locks.py](api/locks.py)) — `dual_rebalance_lock` combines in-process `asyncio.Lock` and cross-process fcntl file lock in one async context manager. All three rebalance entry points (API `/rebalance/execute`, launchd A4 job, launchd `filter_check.py`) serialize through it. Contention returns 409 from the API and `status="locked"` from the cron.
- **Atomic writes** ([data/pipeline.py:write_parquet_atomic](data/pipeline.py)) — tmp-file + `os.replace` across all 7 live-path parquet writes (ETF cache, SP500, crypto universe, BTC, VIX, snapshot save, snapshot backfill).
- **Try/finally around execute** in all three call sites — the rebalance journal survives mid-flight raises; partial order results are captured alongside an `execute_error` field so no audit trail is silently lost.
- **Drawdown monitor** ([execution/risk_manager.py](execution/risk_manager.py)) — two-tier:
  - **-10% alert** (dashboard banner, non-blocking). Derived live from the daily snapshot history + current Alpaca equity, so the "peak" is always accurate regardless of rebalance or dashboard cadence.
  - **-35% catastrophe halt** (manual reset required, audit-journaled). Latches a single persisted boolean; the API endpoint and all launchd jobs refuse to trade while latched. Calibrated so it never fires on 16y of IS+OOS backtest across any live strategy — a "something every other layer missed" backstop, not a routine-DD gate.

### Automation + monitoring

- **cron, three entries** (migrated launchd→cron 2026-05-28 after macOS BTM kept disabling agents; five laptop-scheduling failure modes diagnosed and worked around to date — see AUTOMATION.md):
  - Hourly `--if-due` trigger for the (now gate-blocked) A4 daily job — the TZ-immune, sleep-tolerant pattern that survived failure mode #5.
  - SPY + BTC filter checks every 4h. The SPY run also computes two **alert-only** signals: the VIX9D/VIX3M tail signal (≥1.10 → notification + drives the A3 VIXY paper pilot) and the 5-sensor macro composite (vote alerts at ≥2; led SPY-200d by 34-56 days in 2018/2020/2022; exposure-scaling explicitly tested and rejected — `docs/research/MACRO_COMPOSITE_EVAL.md`).
- **GitHub Actions travel watcher** — `.github/workflows/filter_watch.yml` polls SPY/BTC every ~30 min, pushes ntfy.sh alerts on filter crossings + daily heartbeat. Catches the laptop-fully-off case during digital-nomad travel days. Doesn't trade — notifies only.
- **Ops dashboard tab** consolidates scheduler status, filter state, validation status, and event timeline into one pane (replaces older macOS notifications). Endpoints at `/api/ops/*`.
- **Strategy-discovery workflow** — new candidates get evaluated via the same six-test framework before going live. Never "trust the paper defaults."

### Dashboard + audit trail (React + TypeScript + TradingView Charts)

- **Account switcher** (Combined + live accounts; retired accounts removed from the switcher, their backtests live under Building Blocks).
- **Live equity curves** per account + combined, with SPY benchmark overlay.
- **Correlation panel** — rolling 21-day, per-pair, with alerts when correlation exceeds backtest-expected bands.
- **Backtest runner** with grouped strategy panel (Live / Portfolio Blends / Building Blocks / Solo + Filter). Returns IS / OOS splits with a visual train/test cutoff marker.
- **Rebalance UI** — preview → confirm → execute with action-classified orders (new / increase / decrease / exit). Displays SPY/BTC filter scalars and vol scalar alongside target weights.
- **Risk status panel** — three visual states (green OK with thresholds shown / amber alert active / red catastrophe halt with reset button).
- **Filter status banner** — SPY and BTC price vs MA, last filter check time, recent auto-rebalances. Red plausibility warning banner when data quality issues are flagged. Regime cards (2026-07-18): VIX tail-signal ratio vs the 1.10 trigger + macro-composite vote count with per-sensor chips.
- **Rebalance history** — expandable per-event order details.
- **Structured JSONL journal** ([execution/rebalance_log.py](execution/rebalance_log.py)) — per-event timestamp, account, strategy, portfolio value, orders submitted/failed, SPY/BTC filter scalars, vol scalar + diagnostics, execute_error, source attribution (manual / scheduled / filter_monitor / halt_reset).
- **4 persistent state files**: `validation_state.json`, `filter_state.json`, `plausibility_state.json`, `circuit_breaker_acct{N}.json`. All atomic writes, all versioned schemas.

### Test suite

**131 tests, all green** (suite repaired 2026-07-18 — a `conftest.py` fixture now isolates position-reconciliation state so unit tests can neither read nor clobber real operational files). Covers plausibility, validation gate, risk manager, rebalance mechanics, strategies, vol-scaling, drawdown-halt sim, transaction costs, and rebalance journal. `uv run pytest` from the project root.

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
- **Modest, bounded leverage only.** Equity accounts extend to 1.5× gross via Reg-T margin in calm regimes (built 2026-07-18); crypto stays spot-only. No shorting, no options in live use (Alpaca options L3 is verified available but unexploited — a SPY put-ladder tail hedge is parked pending the VIXY pilot's first realized round trip), no futures.
- **No prime brokerage / compliance / regulatory reporting.** Not relevant at current scale; would be a rebuild at institutional scale.
- **No sub-second market data.** End-of-day cadence only. Correct for monthly / daily rebalance strategies; wrong if you're doing intraday.
- **Sample size is short** for strategies running on crypto. A4's OOS window is 3.3 years; statistical confidence on the Calmar claim is meaningful but not deep. Block-bootstrap p5 of +20.9% is our honest downside estimate.
- **No auto-disaster-recovery.** State files are on a single local disk (laptop). Fly.io migration (Phase 0 deployment) is the remedy; not yet started.

---

## How we know the system is robust

Three lines of evidence:

1. **[HISTORY.md](HISTORY.md)** — an adversarial review (April 2026) surfaced 20+ latent bugs across Tier 1 (headline numbers), Tier 2 (concurrency + safety), Tier 3 (data correctness), and Tier 4 (reporting hygiene). 95% closed as of 2026-04-21. The remaining 5% is C3 survivorship (disclosed, pre-real-money) and low-severity hygiene. Every fix has a commit and a test. Per-item digest in HISTORY.md; full status-threaded discovery context in `docs/archive/AUDIT_MONTH2.md`.

2. **[HUNT_APR2026.md](docs/archive/HUNT_APR2026.md)** (formerly BREAKTHROUGH.md) — two proposed strategy breakthroughs were tested under pre-committed thresholds. Both were killed honestly. The discipline of accepting those negative results is what surfaced the in-sample-tuned Sharpe problem that triggered the audit. Kill discipline > alpha claim.

3. **[VALIDATION.md](VALIDATION.md)** — all three active accounts carry a current validation record with a pass/marginal status and a quarterly expiry. The gate refuses to trade on un-validated accounts, refuses override bypass on retired accounts, and logs warnings when override is active. This isn't a policy document — it's enforced code.

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

**Pre-real-money path (as re-sequenced 2026-07-18):**
- **Q3 checkpoint** — A1 clean-window alpha ≥ 0 vs SPY over 2-3 rebalance cycles under the 07-18 configs. `scripts/live_scorecard.py` is the single source (cycle-by-cycle live/signal/SPY, plus the shadow-A4 tracker). Clock starts at the 2026-07-22 rebalance.
- **Fly.io deploy** ([DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)) — deferred by George until live evidence justifies the spend; recent underperformance was design/bugs, never hosting. Free interim alternative if wanted: run the 4h filter checks on the existing GitHub Actions scaffold.
- **C3** — Norgate declined (2026-07-18); handled by a ~1-2pp expectation haircut on A1, or a free sensitivity test pre-real-money.

**Research state (2026-07-18):** every proposal now carries a disposition — the `AUDIT_FABLE.md` banner is the DONE/KILLED/PARKED ledger, and every doc in `docs/research/` opens with a STATUS banner. Untested cheap vectors: CEF discount reversion, on-chain slices (netflows, stablecoin supply, MSTR/IBIT NAV basis). Parked with triggers: basis carry (funding >8-10% ann.), DBMF A2 swap (A2 live Calmar <1.0 at Q4), SPY put-ladder vs VIXY comparison (after the pilot's first round trip), IBKR bundle ($150K+ real money), micro-cap QM (point-in-time data).

**Low-priority hygiene:** R6-R8, R10, R13-R15 remain (non-blocking); win-rate report bug fixed 2026-07-18. None block paper or real-money operation.

---

## Hands-on onboarding (new collaborators)

1. **Run it locally:** `./scripts/start.sh` → backend on :8001, dashboard on http://localhost:5174.
2. **Read [CLAUDE.md](CLAUDE.md)** next — the operational manual. Loaded every Claude session, so it's the canonical "current state" reference.
3. **Then [BOOK_SHAPE.md](BOOK_SHAPE.md)** for forward direction — what the book is, what's missing, what's prioritized.
4. **Skim [HISTORY.md](HISTORY.md)** before trusting any headline number above — every CAGR/Calmar figure has caveats; this doc tracks them.

When something looks wrong, `git log --follow <file>` first — file behavior often predates current code (lesson learned the hard way; see CLAUDE.md "Working with Claude" section).

---

## Conventions you'll trip on

- **ET is the system reference timezone**, not laptop local. The user is a digital nomad; laptop-local TZ is never load-bearing. Use `data/trading_dates.py:today_et()`, never `date.today()`.
- **Package manager: `uv`.** Always `uv run` to execute Python; `uv add` to install. Not pip/poetry/conda.
- **Backend port: 8001** (not 8000 — :8000 is reserved for FIREMaster, a sibling project). Frontend: 5174.
- **Paper-first.** All 4 Alpaca accounts are paper. Real-money graduation has explicit gates (see Status at top).
- **Commits go to `main` directly.** No feature-branch PRs by default.
- **Async FastAPI handlers MUST use `asyncio.to_thread()`** for blocking calls (Alpaca API, yfinance, parquet I/O, pandas). Direct blocking calls freeze the event loop.
- **Override flags exist but are loud:** `FIRE_VALIDATION_OVERRIDE=1` logs WARNING and cannot bypass retired status. The friction is intentional.
- **Stop-and-confirm before any change >50 lines or new file/architecture decision.** This rule has fired multiple times to good effect — see CLAUDE.md "Working with Claude" for the catalog of past slip-ups it codifies.

---

## Deep-dives

Everything above is a summary. Primary sources, grouped by what you'd open them for:

**Operational state + forward direction (read often):**
- **[CLAUDE.md](CLAUDE.md)** — current operational state, architecture map, scorecard, running next-steps. Loaded every Claude session.
- **[BOOK_SHAPE.md](BOOK_SHAPE.md)** — what the book is, what's missing, prioritized vectors. The forward-direction doc.
- **[AUTOMATION.md](AUTOMATION.md)** — runbook for the launchd jobs (daily A4 + filter monitors), travel-watcher flow, install/uninstall.
- **[HISTORY.md](HISTORY.md)** — resolved fixes and decision deltas. Look here when a code path mentions "post-CN fix."

**Strategic + design references:**
- **[PLAN_MODE2.md](docs/research/PLAN_MODE2.md)** — two-mode architecture strategic framing.
- **[VALIDATION.md](VALIDATION.md)** — CAGR-first validation framework, thresholds, gate logic.
- **[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** — Fly.io migration plan, phased rollout.
- **[SDD.md](SDD.md)** — Software Design Decisions (patterns, lessons learned).
- **[DATA_SOURCES.md](DATA_SOURCES.md)** — yfinance pain log + replacement candidates. Becomes load-bearing at Phase 5.
- **[RATE_VOL_SCOPE.md](docs/research/RATE_VOL_SCOPE.md)** — candidate A4-class strategy scoping.

**Bug catalog + audit trail:**
- **[HISTORY.md](HISTORY.md)** — canonical per-item digest of every C/S/D/R finding (resolved + still-open).

**Time-capsule context (in `docs/archive/`):**
- **[PLAN.md](docs/archive/PLAN.md)** — original project plan, research roadmap, academic references.
- **[HUNT_APR2026.md](docs/archive/HUNT_APR2026.md)** — April 2026 breakthrough hunt (both hypotheses falsified, cascaded into the audit).
- **[DECISIONS_RESOLVED.md](docs/archive/DECISIONS_RESOLVED.md)** — full record of the A3-retirement + A4-weight decisions.
- **[HANDOFF_ALPACA_BARS.md](docs/archive/HANDOFF_ALPACA_BARS.md)** — the C10 migration brief (live crypto signal computation moved to Alpaca bars). Authoritative narrative is now in HISTORY.md C10/C11.
- **[AUDIT_MONTH2.md](docs/archive/AUDIT_MONTH2.md)** + **[AUDIT_47.md](docs/archive/AUDIT_47.md)** + **[AUDIT.md](docs/archive/AUDIT.md)** + **[AUDIT_MONTH2_REVIEW.md](docs/archive/AUDIT_MONTH2_REVIEW.md)** + **[OPS_DASHBOARD_PLAN.md](docs/archive/OPS_DASHBOARD_PLAN.md)** — full audit cycles + design records, all closed.

---

## Glossary

**Accounts:**
- **A1** — Account 1, FIRE 0.1, Stock Momentum (top-15 S&P 500 + SPY filter), monthly rebalance.
- **A2** — Account 2, FIRE 0.2, Trend + Low-Vol blend (30% multi-asset trend + 70% low-vol + vol-scaling), monthly rebalance.
- **A3** — Account 3, FIRE 0.3, RETIRED 2026-04-20 (Reversal + Momentum blend was structurally 40%-A1 by construction). Hosts the VIXY tail-leg paper pilot since 2026-07-18.
- **A4** — Account 4, FIRE 0.4, RETIRED 2026-07-13 (was Crypto Momentum Rotation; walk-forward edge decay + bug-era live drag — HISTORY.md). Shadow-tracked in `live_scorecard.py`.

**Time + windows:**
- **OOS / IS** — Out-of-Sample / In-Sample. OOS test window is 2023-01-03 → 2026-04-20; IS is 2010 → 2022.
- **ET** — America/New_York (DST-aware). System reference timezone.
- **ppy** — periods per year (252 for equity, 365 for crypto-only books).

**Metrics:**
- **CAGR** — Compound Annual Growth Rate. Primary objective per the v2 framework.
- **MaxDD** — Maximum Drawdown (worst peak-to-trough loss).
- **Calmar** — CAGR / |MaxDD|. Primary risk-adjusted return metric.
- **MAR** — equivalent to Calmar in this codebase (used interchangeably in older reports).
- **Sortino, Omega, Sterling, Burke, Pain, Ulcer, UPI** — supplementary scorecard metrics from `backtesting/metrics.py:full_scorecard`. None are gated.
- **Sharpe** — kept for cross-comparability, **not gated**. Treasury bills had Sharpe 5-10 from 2010-2022 — penalizing upside vol is the wrong objective for a wealth-compounding book. See VALIDATION.md.

**System concepts:**
- **Filter scalar** — multiplier applied to target weights based on regime filter (SPY 200d MA, BTC 125d SMA). 1.0 = full exposure, 0.5 = half, 0.0 = cash.
- **Vol scalar** — Moreira-Muir overlay multiplier from realized-vol EWMA. Bounded [0.5, 1.5] on the live equity accounts (A1 book-level, A2 account-level; >1.0 uses Reg-T margin); crypto books clamp at 1.0.
- **Filter monitor** — `scripts/filter_check.py`, runs every 4h via cron, auto-rebalances on filter flip; also computes the alert-only VIX tail signal (drives the A3 pilot) and macro composite.
- **Validation gate** — `execution/validation_gate.py`, blocks rebalance on accounts without a passing record. Quarterly expiry enforced.
- **C-numbering** — `C1`, `C2`, ..., `C11` are stable identifiers for Tier 1 audit findings (changed reported numbers or remain open caveats). `S` = Tier 2, `D` = Tier 3, `R` = Tier 4. Per-item canonical descriptions in HISTORY.md; status-threaded discovery context in `docs/archive/AUDIT_MONTH2.md`.
- **Robust-opt** — parameter search via `min(Calmar_half_A, Calmar_half_B)` rather than naive Sharpe-max. Picked SMA-125/top2 for A4 from a 144-config grid.

---

## Closing frame

FIRE's strongest edge is the **discipline layer**: pre-committed thresholds, enforced validation gates, sim/live parity verification, willingness to kill hypotheses honestly. The mechanics are solid; the audit trail is real; the infrastructure works.

Where the search stands (2026-07-18): the April-July research campaigns measured essentially every cheap public edge — 12 factor vectors, then all four event streams, the switched vol sleeve, and leveraged trend — and killed or priced each one. What survived contact with data was **sizing engineering on the strategies already owned** (+4pp validated book CAGR in one week), a priced insurance leg now running as a live paper pilot, and a regime sensory layer. The honest lesson the system keeps teaching: for a solo operator in 2026, edges live behind regimes, data walls, and drawdowns — not in published anomalies — and the discipline layer is what converts that lesson into decisions instead of drift.

The next verdicts belong to the calendar: the 07-22 levered rebalance, the pilot's first tail event, and the Q3 alpha checkpoint that gates real money.
