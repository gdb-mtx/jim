# Decisions — Resolution Log

Historical record of the April 2026 portfolio-architecture decisions. Both outstanding questions from the 2026-04-18 handoff have been resolved and executed.

---

## Decision 1 — Account 3 → **RETIRED** (2026-04-20)

### The call

**Option A (retire A3)** chosen over Option B (redesign as pure STR) and Option C (reduce weight to 20%).

Capital redeployed: $100K A3 → effectively 1/3 each across A1, A2, A4.

### Why retire (primary basis: backtest, confirmed by live)

**Structural argument:** A3 is 60% STR + **40% Stock Momentum**. A1 is 100% Stock Momentum. 40% of A3 IS A1 by construction. That's an architectural fact independent of any window or data quality.

**Evidence:**

| | Value | Source |
|---|---|---|
| A1↔A3 backtest correlation (3-yr OOS) | 0.876 | Fresh data (sp500 cache was fresh at audit) |
| A1↔A3 full-sample backtest | 0.884 | — |
| A1↔A3 live 29-day | 0.842 | Mar 10 → Apr 18; partial stale-data influence but consistent |
| A3 standalone OOS CAGR | 14.5% | Below the 15% PASS floor |
| A3 contribution to 3-acct Calmar | ≈0 | 50% A1 + 50% A2 gives Calmar 2.11 vs 1/3-each 2.12 |
| A3 CAGR cost in 3-acct blend | −1.7pp | 50/50 A1+A2 gives 19.7% vs 1/3-each 18.0% |

Option B (pure STR replacing the 60/40 blend) was tested and LOSES on both CAGR AND Calmar at every A4 weight — so it was eliminated during the audit. Option C (reduce to 20%) gave only marginal improvement and added complexity.

### What was done

- **2026-04-20**: Liquidated A3 via `scripts/liquidate_account.py --account 3 --confirm`. 53 positions sold at open/early session, $99,826.89 all-cash.
- **`ACCOUNT_INFO[3]`** set to `{strategy: None, status: "retired", retired_at: "2026-04-20", label: "Retired (slot open)"}`
- **`active_accounts()`** helper added; live paths (combined view, correlation, filter monitor, rebalance endpoints) iterate active only
- **A3 tab hidden** from the Live Portfolio account switcher; correlation matrix recast as A1/A2/A4; historical snapshots preserved on disk
- **`reversal_blend` strategy** moved to Backtests → Building Blocks with "Retired 2026-04-20" description
- **Validation gate** blocks A3 (`status="retired"` is not `"pass"` or `"marginal"`)
- **A3 Alpaca paper account** is preserved as a future strategy slot; balance can be reset to $100K when a new strategy is ready

### Caveat from the Tier-1 audit (see AUDIT_MONTH2.md)

The live 29-day correlation (0.84) was observed during the stale-data window and may have been partly an artifact. The **backtest** correlation (0.876) is from fresh data and stands — it's the primary basis. Decision does not need revisiting.

---

## Decision 2 — Account 4 weight → **33%** initially, **40% upgrade after live evidence**

### The call

**Drop-A3 + 33% A4** (equivalent to 1/3 each across A1, A2, A4) chosen over (a) status quo 3-acct + 25% A4 and (b) keep-A3 + 40% A4.

**Upgrade path pre-committed:** A4 can scale to 40% of book once it has ≥6 months of actual *signal-trading days* (not cash-on-filter days), with live Calmar ≥ 2.0 and live A4↔equity correlation ≤ 0.25. Absent those conditions, stay at 33%.

### Why 33% was chosen

- **Simplicity:** one fewer account to maintain (A3 retired), weekly rebalance cadence gone, lower cognitive overhead for Mode 2 build
- **Material CAGR lift vs status quo:** projected ~3.5pp on paper (**biased high** — see caveats)
- **Leaves room to scale:** 33% → 40% ladder preserves upside once live data confirms
- **Concentration comfort:** 33% A4 at worst-case -30% crypto-only drawdown = -10% combined, vs -12% at 40%. Psychologically manageable.

### What was done (2026-04-20)

- `strategies/portfolio.py`: split `COMBINED_ACCOUNT_STRATEGIES` into `LIVE_ACCOUNT_STRATEGIES = [A1, A2, A4]` (for dashboard combined view) and `EQUITY_CORE_STRATEGIES = [A1, A2]` (for validation base)
- `run_combined_portfolio`: A1 + A2 + A4 at 1/3 each on union calendar, ppy=365
- `run_equity_core`: A1 + A2 at 50/50 on equity calendar, ppy=252
- `scripts/run_validation.py`: A4 `portfolio_fit` baseline moved to `run_equity_core`; default weight 25% → 33%
- `api/routes/backtests.py`: uses ppy=365 when combined includes crypto
- `dashboard/src/strategyMetadata.ts`: combined_3account description updated; `reversal_blend` retired
- A3 liquidation: cash stays in A3's Alpaca paper account (no physical redistribution); weights are calculated from A1+A2+A4 live equity only

### Live-tracking clock reset (2026-04-20)

The Mar 10 → Apr 17 paper trading window ran on stale data (see AUDIT_MONTH2.md: BTC/crypto/VIX/SP500 caches frozen Mar 10; SP500 briefly ran at 91/451 tickers on Apr 20). 10 manual rebalances executed on stale signals.

Effective live-clock reset date: **2026-04-20** (post-cache-fix, post-A3-retirement). The A4 33→40% upgrade clock measures signal-trading days from this date forward (with BTC filter currently below the 125d MA, actual signal-trading days hadn't started as of the reset).

### Caveats from the Tier-1 audit

- **C1 (weekend-zero bias):** the "drop-A3 + 33% A4 → Calmar 3.79, CAGR 28.5%" number is inflated because `run_combined_portfolio` treats equity weekends as 0% return rather than held positions. Realized weights drift over a year from 33/33/33 toward ~23/23/54. Direction still favors 33% over 25%, margin smaller than stated.
- **C2 (BTC MA warmup):** SMA-125/top2's Test-3 half-A Calmar (2.89) — the primary robust-opt gate — is partly flattered by `min_periods=1`. The A4 production config may not survive a clean recompute.

Before scaling to 40%, both Tier-1 bugs should be fixed and numbers re-verified. The 33% weight choice itself does not need revisiting — it's dominated by 25% on any reasonable correction.

---

## Reference commits

- `cbd7422` — original correlation finding + CLAUDE.md correction (April 18)
- `1baad0d` — Crypto robust-opt + SMA-125/top2 promotion (April 18)
- `c278896` — Scorecard metrics module
- `d23bd80` — CAGR-first validation runner
- **2026-04-20 (to be committed)** — A3 retirement, ACCOUNT_INFO refactor, data-cache staleness fixes, SP500 batch retry, freshness pill, metrics fixes, reviewer-audit findings

## See also

- `AUDIT_MONTH2.md` — bugs found during adversarial review, ranked fix plan
- `CLAUDE.md` — current system state (3-account architecture post-retirement)
- `VALIDATION_PLAN.md` — v2 framework and thresholds
