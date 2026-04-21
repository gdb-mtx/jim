# Month-2 Audit — Findings & Fix Plan

**Date opened:** 2026-04-20
**Context:** Mid-session we discovered (a) data caches had no staleness check → 41 days frozen, (b) `download_sp500_prices` silently wrote a 91/451 truncated cache after its batch-download recovery path swallowed errors. Spawned three adversarial reviewers to see what else we'd missed. This doc consolidates their findings, ranks them, and is the pick-up point for the next session.

**TL;DR —** the foundation is sound (signal lagging, vol-scaling shifts, bootstrap resampling, gates, circuit-breaker persistence are all correct). The bugs cluster where pieces are **composed**: calendar handling, cross-process concurrency, cache atomicity, MA warmup. These are the fast-iteration-with-AI failure mode.

**Status 2026-04-20:** Tier 1 C1 + C2 fixed; C1 empirically non-material (<0.3pp CAGR), C2 does not flip the SMA-125/top2 production config. C3 disclosure in place. **Tier 2 S1-S4 all fixed 2026-04-20** — cross-process lock unified, parquet writes atomic, snapshot RMW locked, yfinance retry helper shared across every live-path downloader. Real-money-graduation blocker lifted. **Tier 3 D1-D4 all fixed 2026-04-20** — ET trading-date helper (`data/trading_dates.py`), backfill/snapshot TZ-stable, SP500 ticker list on 7-day TTL (discovered the cached list was 998h old → refresh pulled 451→503 tickers, confirming 52 silently-dropped delistings), SPY fetch failures now render "—" instead of misleading 0%. Tier 4 remains open.

**Sim/Live Parity Audit 2026-04-20 (session 2) — NEW Tier 1 findings:** A second adversarial pass specifically targeting divergence between the backtest path (`run_combined_portfolio`, `apply_vol_scaling`, etc.) and the live rebalance path (`compute_rebalance`, `_daily_crypto_rebalance`, `filter_check.py`) found **three new Tier 1 items (C4, C5, C6)** where the headline CAGR/MaxDD/Calmar numbers are produced by code the live book does not run. Cumulative effect: A4 MaxDD is materially understated in the backtest (vol-scaling floor of 10% never applies live); A4 CAGR is ~0.5-1pp overstated (no fee model); all accounts' backtests assume trading continues through -15% drawdowns that would halt live. Details below under Tier 1 → C4/C5/C6. **Not yet fixed.**

**Session 3 follow-up 2026-04-20 — C7 corrected and promoted to 🔴:** Re-verified the 20% `max_position_pct` cap against A4's top-2 crypto strategy. Session-2 mechanical check was wrong ("never binds" was based on comparing the 50% weight to the 20% cap without realizing 50% is the *design*, not a weight to cap). Reality: the cap forces A4 from its designed 50/50 top-2 to 20/20 top-2 + 60% cash. A4 has been 100% cash since launch, masking the bug — **but BTC is 1.2% below the 125d MA right now, so the first live rebalance after a crossover will execute the wrong book.** C7 is now the largest A4-specific sim/live gap and is time-sensitive.

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

### 🔴 C4. Vol-scaling overlay absent from live rebalance — NEW 2026-04-20 (session 2)
**Files:** `strategies/portfolio.py:242-281` (defines `apply_vol_scaling`), `strategies/portfolio.py:346-347` (backtest calls it), `execution/rebalance.py` (never calls it), `api/main.py:22-108` (never calls it), `scripts/filter_check.py` (never calls it).
**Finding:** `apply_vol_scaling` multiplies the **returns series** by `vol_target / realized_vol` clipped to `[floor, cap]`. It is invoked inside `run_combined_portfolio` (backtest) and in the validation adapters + research scripts, but **never in any live code path**. Configs `trend_lowvol` (A2, defaults: floor 0.5 / cap 1.5) and `crypto_momentum_filtered` (A4, params: target 15%, halflife 30, **floor 0.1 / cap 1.5**) both have `"vol_scaling": True`. The overlay does nothing in live — weights are just `top_n equal-weight × BTC/SPY filter scalar`, capped at 100% exposure by construction.
**Why overlooked:** (a) `"vol_scaling": True` sits next to `"spy_filter": True` in the same PORTFOLIOS dict — reads like a peer setting; SPY/BTC filters ARE applied in both paths, vol-scaling only in one. (b) Architectural mismatch — `apply_vol_scaling` operates on a return series, not on weights; scaling weights in live is different code that was never written. (c) AUDIT_MONTH2 session 1 scoped for data correctness (calendars, warmup, survivorship), not sim/live parity. (d) A4 has been 100% cash since launch (BTC below 125d MA), so the live path doesn't hold positions that would expose the divergence. (e) A2's realized vol has been close to the scalar=1.0 regime since 2026-03-10, so live and backtest returns haven't visibly diverged yet.
**Impact:**
  - **Upside mostly harmless:** Alpaca crypto is spot-only + A1/A2 have no margin, so even if live *tried* to apply scalars up to 1.5×, it couldn't lever the book. The backtest's 1.0 → 1.5 range is unrealizable in prod either way. This overstates backtest CAGR by an unknown margin during sustained calm vol regimes.
  - **Downside is the real problem:** In a high-vol regime the backtest cuts A4 exposure to 10% (floor 0.1); live stays **100% invested** until the binary BTC 125d MA filter finally trips. A4 MaxDD is materially understated. The reported **-11.4% MaxDD / 3.98 Calmar** for A4 in a crypto-crash regime could be 2-3× worse in live book (rough estimate; needs a re-run to quantify).
  - A2 impact is smaller: floor 0.5 means backtest only cuts to 50% in extreme equity vol, and equity realized vol rarely pins the floor. MaxDD understatement probably 1-3pp.

**Per-account scope (verified from `strategies/portfolio.py:40-118` PORTFOLIOS dict):**

| Account | `vol_scaling` in config | Backtest scalar range | Applied in live? |
|---|---|---|---|
| **A1 `sm_filtered`** | **not set** (= False) | **none — always 1.0×** | n/a (nothing to apply) |
| **A2 `trend_lowvol`** | `True`, defaults | **[0.5, 1.5]** (target 15%, halflife 21) | No |
| A3 `reversal_blend` (retired) | not set | none | n/a |
| **A4 `crypto_momentum_filtered`** | `True`, custom params | **[0.1, 1.5]** (target 15%, halflife 30) | No |

Defaults on `apply_vol_scaling`: `scalar_floor=0.5, scalar_cap=1.5`. A2 inherits those. A4 overrides `floor=0.1` explicitly — that's why A4's downside scaling is so much more aggressive.

**Full exposure stack — backtest vs live (product of all multipliers):**

| Account | Backtest composite range | Live composite range | Max divergence |
|---|---|---|---|
| **A1** | `signal_weights × SPY_filter(0.5 or 1.0)` → **[0.5, 1.0]** | **same** | **none — A1 is clean** |
| **A2** | `signal_weights × SPY_filter(0.5 or 1.0) × vol_scalar(0.5-1.5)` → **[0.25, 1.5]** | `signal_weights × SPY_filter(0.5 or 1.0)` → **[0.5, 1.0]** | Backtest can go as low as 25% exposure; live floors at 50%. Backtest can lever to 150%; live caps at 100%. |
| **A4** | `50/50_top2 × BTC_filter(0 or 1) × vol_scalar(0.1-1.5)` → **{0} ∪ [0.1, 1.5]** | `50/50_top2 × BTC_filter(0 or 1)` → **{0, 1.0}** | Backtest cuts to 10% on vol spikes; live stays 100% invested until BTC<MA. Backtest can lever to 150%; live caps at 100%. |

**Consequences for headline numbers:**
- **A1 is the clean case.** CAGR 27.3%, MaxDD -9.8%, Calmar 2.77 are apples-to-apples with what the live book produces. The C4 fix does not change A1's numbers. (C3 survivorship caveat still applies, but that's universe, not divergence.)
- **A2 is mildly affected.** Floor 0.5 rarely pins on equity vol; cap 1.5 overstates CAGR modestly in calm regimes. Expected revision: CAGR -0.5 to -1pp, MaxDD -1 to -3pp worse.
- **A4 is the material case.** Floor 0.1 pins hard in crypto crashes — the whole point of the overlay. Live can't replicate, so the backtest -11.4% MaxDD / 3.98 Calmar represent a book we cannot actually trade. Expected revision: CAGR -2 to -5pp, MaxDD -5 to -15pp worse (order-of-magnitude guess, needs quantification).

**Fix options (to decide):**
  - **A. Strip vol-scaling from backtest** — simplest; headline numbers become what the live book can actually produce. Re-run A2 and A4 CAGR/MaxDD/Calmar without the overlay, update CLAUDE.md and validation reports.
  - **B. Implement vol-scaling in live weights** — scale target weights by `min(1.0, vol_target / realized_vol)` inside `compute_rebalance`. Upside cap must be 1.0 (no margin). Requires persisting/recomputing realized vol series per account.

**Decision 2026-04-21: option B, with `scalar_cap=1.0` for the Alpaca-paper era.** Reasoning: per the Kelly design-notes section below, vol-scaling IS Kelly-on-leverage — the one form of Kelly-adjacent sizing that belongs in the live book. Stripping it from backtest (option A) would sacrifice a legitimate edge for simplicity. B is more work (need per-account realized-vol persistence) but it's the sophisticated answer, not just the honest answer.

**Planned implementation (future session, not now):**
1. Add `compute_vol_scalar(account, returns_series, vol_target, halflife, floor, cap)` in `execution/risk_manager.py` or a new `execution/vol_scaling.py`. Returns today's scalar; reads realized-vol from account snapshot history (`data/processed/snapshots_acct{N}.parquet` already has daily equity → compute returns → EWMA vol).
2. Call it in `_get_portfolio_signals` after the SPY/BTC filter scalars. Cap at 1.0 until we have leverage infrastructure.
3. Strip `scalar_cap=1.5` from the backtest configs too — backtest and live both cap at 1.0 → apples-to-apples.
4. Re-run A2 and A4 validation; update CLAUDE.md headline numbers.
5. Verify live-computed scalar matches backtest-computed scalar on historical snapshots for the period since 2026-03-10.

**Future research: `scalar_cap > 1.0`.** User flagged (2026-04-21) interest in exploring leverage once the paper stack is stable. Options by asset class:
- **Equity (A1, A2):** Alpaca offers Reg T margin (2× overnight, 4× intraday) on equity accounts — can enable without switching brokers. Real risk: margin-call on a systematic strategy that rides out -15% drawdowns would be catastrophic. Requires careful Kelly math + margin-interest cost modeling (C6 doesn't currently cover financing).
- **Crypto (A4):** Alpaca crypto is spot-only. Credible alternatives for US residents:
  - **CME micro BTC/ETH futures** — cleanest regulatory path, but different API, different tax treatment (Section 1256 mark-to-market), lower granularity than spot.
  - **Coinbase Advanced** — up to 3× on some pairs for US residents (state-dependent).
  - **Kraken** — up to 5×, broader state coverage.
  - **Offshore perps (Bybit, OKX, Binance)** — deepest liquidity but KYC/compliance issues for US residents; not recommended.
  - dYdX / on-chain perps — interesting long-term but infrastructure lift is significant.
- **Priorities for the leverage research vector:** (a) quantify how much CAGR/Calmar >1.0 could unlock (worth doing via backtest before committing operational work); (b) pick one asset class to start with (likely crypto via CME micros, since that's where A4's Sharpe is highest and the Kelly-optimal leverage is largest); (c) build margin-cost + margin-call modeling into the backtest.
- **Not in Month 3 scope.** File under post-real-money-graduation research. Cap stays at 1.0 through the deployed-paper window.

**Status:** 🔴 Open. Decision made (option B); implementation deferred to a dedicated session.

### 🔴 C5. Circuit breakers not simulated in backtest — NEW 2026-04-20 (session 2)
**Files:** `execution/risk_manager.py:186-233` (live implementation), `strategies/portfolio.py` (no equivalent), `backtesting/` (no equivalent).
**Finding:** Live trading halts at -15% portfolio drawdown and -10% strategy drawdown. Halts persist to disk and require manual reset. The backtest `run_combined_portfolio` and the validation harness never model a halt — they assume continuous trading through arbitrarily deep drawdowns.
**Why this matters both ways:** it's a genuine two-sided effect.
  - **Scenario 1 (crash + recovery):** Backtest trades straight through a -20% drawdown and catches the rebound. Live halts at -15%, holds the residual positions, and misses the rebound until manual reset. Live underperforms backtest.
  - **Scenario 2 (crash + deeper crash):** Backtest eats the full drawdown. Live halts at -15% and avoids the additional 10-20% of the crash. Live outperforms backtest (lower MaxDD, potentially higher CAGR over the cycle).
**Impact:** Backtest MaxDD is the true worst case; live MaxDD is bounded by -15% portfolio DD. Backtest Calmar treats that worst case as investable return; live treats it as "time out of market." Combined 3-acct OOS MaxDD -7.0% is already well above the halt threshold, so the equity core hasn't hit it historically — but A4's backtest MaxDD -11.4% assumes you'd ride a hypothetical -15-20% crypto drawdown; live would halt at -15% (strategy level if isolated, portfolio level on the full book).
**Fix:** Add circuit-breaker simulation to the backtest — either a halt-and-hold layer in `run_combined_portfolio`, or run post-hoc and blank out returns during halted periods. Non-trivial but tractable (~half-day).

**Design origin (traced 2026-04-20, session 3):**
- Committed in the initial FIRE build (`175c234 Add complete FIRE quantitative trading system`), specified in [PLAN.md:144-158](PLAN.md#L144-L158) under "Drawdown Circuit Breakers."
- Cited motivation: **Larry Hite** (Market Wizards) — *"the #1 thing that separates survivors from blowups."*
- Manual reset is intentional per PLAN.md: *"you must consciously decide to re-enter, not have the system silently recover."*
- Hardened 2026-03-16 (`ce30558`): atomic writes, fail-safe-on-corruption (defaults to halted=True).
- No one critiqued the design itself until the 2026-04-20 session 3 review raised the concerns below.

**Critical review — the design may be primitive and counterproductive (research notes, not a decision):**

Portfolio-level drawdown halt + manual reset has substantive problems beyond the sim-live parity issue the original C5 finding identified:

1. **Drawdowns don't predict returns.** Van Hemert, Ganesh, Nguyen, Rudd (2020), *Drawdowns*, Journal of Financial Data Science — shows drawdown depth has no forward-looking predictive power; post-drawdown base rate is mean reversion, not continued decline. Halting at -15% systematically exits positions with *positive* expected forward returns.

2. **Manual reset + mobile user = recovery missed.** Mar 2020: SPY bottomed at -34% then recovered to new highs in ~5 months, including the best daily returns of the decade clustered in the weeks immediately after the bottom. A halt + "George is in Europe, didn't see the notification for 3 days" = miss the V-shape. This is the worst-case interaction with the digital-nomad operational profile in [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

3. **Duplicates — and crudely reproduces — better layers we already have.**
   - **SPY/BTC 200d MA filters** are already regime-based trend-following de-risking. Smooth, signal-driven, auto-reverses on recovery. Better than a binary halt.
   - **Vol-scaling overlay** (currently C4-broken in live) is continuous exposure sizing inversely to realized vol. Better than a binary halt.
   - The portfolio breaker is effectively a ham-fisted, hysteretic, human-in-the-loop version of what those layers do continuously.

4. **Sophisticated systematic funds do not use this pattern.** AQR, Winton, Man AHL, Two Sigma publicly describe dynamic vol-targeting and drawdown-aware sizing, not binary portfolio halts with manual reset. The pattern is more common in discretionary-with-guardrails shops than in pure systematic ones.

5. **It does not distinguish signal drawdown from model failure.** A -15% DD on a backtest-CAGR-30% / backtest-MaxDD-10% strategy is ~1.5σ — expected and routine. A -15% DD accompanied by 5σ tracking error vs. the strategy's expected daily returns = model is genuinely broken. Only the second warrants a halt; the current breaker conflates them.

6. **Strategy-level breaker (-10%) is dead code.** Per R3 below, it's never wired in `compute_rebalance`. So the "strategy-level circuit breaker" advertised in CLAUDE.md does not actually protect anything — it's documentation without implementation.

7. **Larry Hite's principle is position-level, not portfolio-level.** Hite's emphasis in Market Wizards is on per-trade stop losses and position sizing (the "2% rule" which we also have — and *that's* well-founded). Extending it to "halt the whole portfolio at -15% with manual reset" is a translation error: the underlying logic does not scale the same way.

8. **Asymmetric: likely hurts CAGR, uncertain benefit to MaxDD.** Scenario 1 (halt + recovery missed) is very costly to CAGR. Scenario 2 (halt + further decline avoided) reduces MaxDD by 5-15pp. Which dominates depends on the distribution of crash types in the window. Historically V-shapes outnumber L-shapes, so expected-value tilts negative.

**Alternatives for a future session to consider (none committed):**
- **Alert-only at -10%, not halt.** Notify user, don't stop trading. Pushover/Telegram push. User can manually halt if they think something is structurally broken.
- **Model-residual monitoring.** Track realized daily returns vs. backtest-expected distribution. Halt only if >3σ tracking error over N days (genuine sign of model failure), not on drawdown alone.
- **Move the halt threshold much deeper** (-30% or -40%) and keep it as a "catastrophe kill switch" for truly anomalous events only. Accept that within-backtest-expectation drawdowns are not halt-worthy.
- **Auto-reset on trend filter reversal.** If the regime filter (SPY/BTC>MA) flips back to bullish, automatically clear the halt — the filter itself is the recovery signal.
- **Delete the portfolio breaker entirely** and rely on the SPY/BTC filters + vol-scaling (once C4 is fixed in live) to do the risk management. Keep only the 2% rule at the trade level (Hite's actual principle).
- **Hybrid:** halt on drawdown-plus-tracking-error-AND together, not drawdown alone. Captures "something is wrong" without firing on routine drawdowns.

**This critique does NOT unblock C5's original finding** — the backtest still doesn't simulate whatever halt logic we end up with, so the sim/live parity gap persists regardless of whether we keep, modify, or delete the breaker. But it reshapes the fix:
  - If we **keep the breaker as-is**: add halt simulation to backtest per the original C5 fix. MaxDD gets bounded, CAGR drops in backtests with deep-DD regimes.
  - If we **delete the breaker**: no simulation needed, but the C5 parity issue vanishes because there's nothing to simulate. Live MaxDD becomes whatever the regime filters + vol-scaling allow.
  - If we **replace with alert-only**: similar to delete — no binary halt to simulate.

**Status:** 🔴 Open. C5's original gap (backtest doesn't sim the halt) remains. **But the prior question — whether to keep the halt at all — is now open and should be resolved first.** Research references (Van Hemert et al., AQR/Winton public methodology) should inform the next-session decision. This is a good research question for a future session, not something to fix mechanically.

### 🔴 C6. Zero fee/slippage model in backtest — NEW 2026-04-20 (session 2)
**Files:** `strategies/portfolio.py`, `backtesting/metrics.py` — grep for `fee|commission|slippage|cost` returns nothing in live backtest path.
**Finding:** Backtests assume gross returns. Alpaca equity commissions are effectively zero, but **crypto is not** — Alpaca crypto charges ~0.1-0.3% spread per side (bid-ask markup). A4 rebalances daily → up to 2× full turnover per year under active regimes → **~0.5-1pp annual CAGR drag** not reflected in the backtest.
**Impact by account:**
  - A1/A2 (equity, monthly rebalance, zero commission): negligible, ~5-15 bps/yr slippage only (not modeled but small).
  - A4 (crypto, daily rebalance, ~0.1-0.3% spread per side): **0.5-1.0pp CAGR overstatement**. On a 45.2% backtest CAGR, realistic live CAGR is more like **43-45%**. Calmar impact ~-0.05 to -0.10.
**Fix:** Add a transaction-cost layer in `apply_portfolio_costs()` (backtest-side) — parameterize by account (equity ~0 bps, crypto ~20 bps round-trip), apply per rebalance day. Re-issue A4's validation report with post-cost numbers.
**Status:** 🔴 Open. Smallest of the three C4-C6, but adds honesty. ~30 min to implement the cost layer + re-run A4 validation.

### ✅ C7. Live `max_position_pct=20%` cap silently kneecaps A4 — FIXED 2026-04-21 (option C: cap removed entirely)
**File:** `execution/rebalance.py:325` (`capped_weight = min(weight, risk_manager.limits.max_position_pct)`), `execution/risk_manager.py:36` (cap is 0.20), `strategies/portfolio.py` (no cap).

**Session 2 finding was wrong — corrected here.** Session 2 claimed "CryptoMomentum (A4): max weight 50% (top-2 equal) → never binds." That was based on a shallow comparison (max weight vs cap value) without thinking about what the strategy *intends*. A4 is designed to hold the top 2 momentum coins at 50/50 — that's not a bug to cap, that's the strategy.

**What the cap actually does to each account (verified 2026-04-20 by running `generate_signals` + tracing `compute_rebalance`):**

| Account | Strategy's intended max weight | After 20% cap | Binds? | Effective behavior when "invested" |
|---|---|---|---|---|
| A1 (StockMomentum, top-15) | 12.6% | 12.6% | **No** | 15 stocks, ~6-13% each, fully invested |
| A2 LowVol leg (10 stocks, ×0.70 blend) | 7.0% | 7.0% | **No** | 10 stocks, ~7% each |
| A2 MAT leg (5 ETFs, ×0.30 blend) | 20.9% | 20.0% | Barely (~1pp) | negligible impact |
| **A4 (CryptoMomentum, top-2)** | **50%** | **20%** | **Yes — hard cap** | **Only 40% invested (20% × 2); 60% forced to cash** |

**This means A4's live book when BTC>MA is not "100% invested in top-2 at 50/50" — it's "40% invested, 60% cash."** A4 has been 100% cash since launch (BTC below filter), so this has never manifested in P&L. **But BTC is currently $76,165 vs 125d MA $77,110 — 1.2% below. A4 is close to crossing up. When it does, the next scheduled rebalance will hit this cap and allocate only 40% of the book to signal positions.** That's the moment we'll see the divergence in real P&L.

**Impact:**
- **A4 CAGR is MUCH worse than backtest claims.** Backtest-expected when invested: 50/50 × coin returns. Live-actual: 20/20 × coin returns + 60% × 0. The "when invested" CAGR drops by ~60% from what the backtest assumes. A4 backtest CAGR 45.2% translates to a rough live expectation of ~18-20% (invested fraction 0.4 × full-book return). **This is a bigger effect than C4 (vol-scaling) and C6 (fees) combined.**
- **A4 MaxDD is better than backtest claims** (60% cash cushion), but only because exposure is chopped — not a free benefit.
- **Calmar is lower in both directions.** Can't estimate without a re-run.
- The A4 weight decision (33% of combined book, ladder to 40%) was sized on pre-cap numbers. The 40% Calmar threshold in CLAUDE.md's upgrade ladder will never be hit on the live book's actual behavior.

**Design origin (traced 2026-04-20, session 3):**
- Committed in the initial FIRE build (`175c234 Add complete FIRE quantitative trading system`) inside `RiskLimits` dataclass, comment: `# No single position > 20% of portfolio`.
- Wired into `compute_rebalance` in `7e1b063 Add Alpaca paper trading execution layer (Phase 4)` on 2026-03-10. Commit message: *"risk checks (circuit breakers, position limits)."*
- [PLAN.md:496](PLAN.md#L496) lists it as *"Pre-trade risk checks — circuit breakers, position limits (max 20% per position), portfolio halt at -15% drawdown."*
- **No cited academic reference.** It's a round-number heuristic — 40-act mutual funds commonly use 5-25% caps; retail-trader rules of thumb say 10-20% max per name.
- **When this was set (2026-03-10), only equity accounts were planned.** 3 equity accounts (A1, A2, A3) holding diversified baskets of 10-52 stocks each. A 20% cap was loose for those — never binds, harmless belt-and-suspenders.
- **A4 (crypto) was added later.** CryptoMomentum's top-2 design implies 50% per position by construction. The cap was never revisited for the new strategy shape.

**Bug or feature?** Both — it's **an equity-appropriate feature that becomes a silent bug when applied uniformly to a concentrated top-2 crypto strategy.** The 20% value was correct for the world it was written in; it's wrong for the world that exists post-A4.

**Why overlooked until now:**
- A4 has been 100% cash since launch → the cap has never bound in live trading.
- Session 2 audit checked "does max weight exceed cap?" mechanically but didn't ask "was the strategy designed to be that concentrated?" — a conceptual error not a code error.
- The 2% loss rule and the 20% cap live in the same `RiskLimits` dataclass, so they feel like a package. The 2% rule is load-bearing (Hite principle, position sizing). The 20% cap is an unexamined heuristic that came along for the ride.

**Fix options (to decide):**
- **A. Raise `max_position_pct` to 0.55 globally** — lets A4 top-2 work as designed with a small safety margin. Equity accounts still nowhere near binding. Risk: no other guardrail prevents a future strategy from going 60%+ on a single name. ~1 minute of work.
- **B. Per-strategy / per-account cap.** Add a `max_position_pct` key to each `PORTFOLIOS` config; default 0.20, A4 override 0.55. Explicit about per-strategy shape. ~20 min of work.
- **C. Remove the cap entirely and rely on strategy design** — `top_n` already imposes concentration by construction; StockMomentum at top-15 can't exceed ~1/15, etc. Simplest code, but loses the belt-and-suspenders safety against a future strategy that produces an unintentional extreme weight. Not recommended.
- **D. Keep the cap at 0.20 and change CryptoMomentum to top-5.** Hostile to the strategy's design. The robust-opt specifically picked top-2 over top-3 for regime robustness — forcing top-5 throws that away.

**Recommended:** **B (per-strategy cap)** for explicitness and safety. Fast to implement, clear in the config. **Urgent — should be fixed before BTC crosses the 125d MA, otherwise the first A4 rebalance will execute the wrong book.** At current BTC price, we have days-to-weeks of runway, not months.

**Resolution 2026-04-21 — went with option C (cap removed entirely), not option B.** Reasoning: strategy shape (top_n + equal-weight / blend weights) IS the concentration control. A runtime cap was either redundant (A1/A2) or wrong (A4). Per-strategy caps (B) preserved the "config soup" failure mode that caused the original bug. Safer to validate strategy-output invariants than to clamp raw values.

**Changes made 2026-04-21:**
1. `execution/rebalance.py:325` — removed `capped_weight = min(weight, risk_manager.limits.max_position_pct)`. Strategy-produced weights now flow directly to dollar-sizing.
2. `execution/rebalance.py` (after `get_current_signals`) — added invariant check: `sum(weights) <= 1.0 + eps` and each `0 <= w <= 1.0 + eps`. Raises `ValueError` loudly on violation instead of silently clamping.
3. `execution/risk_manager.py` — removed `max_position_pct`, `kelly_fraction`, `max_loss_per_trade_pct` from `RiskLimits`. Removed the dead `calculate_position_size` method + `PositionSize` dataclass (R12 resolved in same pass). Module now only handles circuit breakers.
4. `tests/test_risk_manager.py` — removed Kelly-sizing tests + 2%-rule test that were exercising the deleted code. Circuit-breaker tests untouched; all 6 pass.
5. `tests/test_rebalance.py` — removed obsolete `test_position_cap_at_20_percent`.
6. `CLAUDE.md` — corrected the risk-controls line from *"Fractional Kelly + 2% max loss + drawdown circuit breakers"* to accurate description (strategy-layer sizing + regime filters + breakers).

**Verified:** `pytest tests/test_risk_manager.py` → 6/6 passing. Pre-existing unrelated failures in `test_rebalance.py` (mock harness doesn't configure `check_tradeable`) persist but are not caused by this change — confirmed by `git stash && pytest` baseline.

**Net effect:** A4 will now rebalance to its designed 50/50 top-2 when BTC crosses above the 125d MA, not the pre-fix 20/20 + 60% cash. A1/A2 unchanged (cap never bound for them). Sim/live parity on sizing is now exact — both paths use raw strategy weights. R12 (dead Kelly code) simultaneously closed.

**Status:** ✅ **RESOLVED 2026-04-21. Landed before BTC crossed the 125d MA (current: $76,165 vs MA $77,110, still 1.2% below).**

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
| R12 | `execution/risk_manager.py:123-184` (`calculate_position_size`) | ~~Kelly/fractional-Kelly sizing computed in live risk manager but never called from any rebalance path. Dead code.~~ **Resolved 2026-04-21 alongside C7** — `calculate_position_size`, `PositionSize` dataclass, `kelly_fraction`, `max_loss_per_trade_pct`, `max_position_pct` all deleted from `RiskLimits` / `RiskManager`. Kelly remains as a reporting metric in `backtesting/metrics.py:kelly_criterion` (never wired to sizing, diagnostic only). | ~~Low~~ Resolved |
| R13 | `strategies/portfolio.py` (backtest) vs `execution/rebalance.py:320-323` (live) | Live rejects negative weights as a defensive guard, but **no strategy currently generates negative weights** (verified: StockMomentum, LowVolatility, MultiAssetTrend, CryptoMomentum all produce min weight ≥ 0.0). Dead rejection branch — safe to keep as belt-and-suspenders, but flag in docs. | Low |
| R14 | Backtest uses yfinance adjusted closes; live uses Alpaca `get_latest_prices()` | Systematic price-source mismatch. yfinance = adjusted close; Alpaca = last trade / mid. Cumulative slippage is already indirectly counted under C6 fees but the vendor discrepancy itself is its own latent gotcha — e.g., after a split, yfinance adjusts historical series but Alpaca position cost basis doesn't. No live bug observed; flag for awareness. | Low |
| R15 | Live qty rounding (`int(dollar/price)` for stocks, `round(..., 8)` for crypto at `execution/rebalance.py:328-330`) vs backtest fractional weights | Small micro-positions (<1 share) silently dropped in live. Backtest assumes perfectly fractional execution. Cumulative impact negligible (<0.1% CAGR) but worth noting for ultra-small accounts. | Low |

---

## Design notes — ratified as intentional (not bugs)

### Kelly sizing — why we don't use it, and what we use instead (2026-04-21)

The C7 + R12 cleanup deleted `calculate_position_size` (Kelly + 2% rule + 20% cap) from the live risk manager. Before that, Kelly was implemented but never called from any rebalance path. The question came up: **should we be using Kelly?** Conclusion: **no, and our current approach is already Kelly-adjacent in the places that matter.**

**Why Kelly doesn't cleanly apply to FIRE's strategies:**
1. **Kelly assumes a single bet with known edge.** Our strategies produce portfolio *weights* across many names simultaneously, not discrete trade signals with per-trade `(win_rate, win_loss_ratio)`. StockMomentum holds 15 stocks based on relative ranks — you can't decompose that into per-stock Kelly inputs.
2. **Kelly assumes independent trials.** Our 15 momentum stocks are highly correlated (all regime-exposed). Per-stock Kelly would double-count.
3. **Kelly assumes known edge.** We have *estimated* edge from backtests; estimation error amplifies destructively. A 2pp overestimate on win rate → Kelly says bet 2× too much → losing streaks hurt proportionally worse.
4. **Kelly maximizes log-wealth; we're Calmar-first.** Full Kelly historically produces 50-80% drawdowns. Fractional Kelly (¼ or ½) reduces this but the fraction is arbitrary. Our CAGR-first scorecard with Calmar gates (see `VALIDATION_PLAN.md` v2) explicitly optimizes a drawdown-sensitive objective — more conservative than Kelly would ever recommend.

**Where Kelly-adjacent math IS being used, just not called "Kelly":**
- **Vol-scaling overlay** (`apply_vol_scaling`) — `scalar = vol_target / realized_vol` is literally Kelly-on-leverage in continuous form (f* = μ/σ²). Moreira & Muir 2017 is the academic basis. C4 is "this should also apply in live, not just backtest."
- **Cross-account weight sweep** (A1/A2/A4 at 1/3 each, ladder-to-40% for A4, see `DECISIONS_RESOLVED.md`) — Kelly-adjacent portfolio optimization with a Calmar objective instead of log-wealth.
- **Robust-opt on crypto** (`scripts/crypto_robust_opt.py`: SMA-125/top-2 via `min(Calmar_A, Calmar_B)`) — picks concentration + lookback that maximize risk-adjusted return under regime-robustness, a more conservative cousin of Kelly.
- **`kelly_criterion()` in `backtesting/metrics.py`** — shown on the validation scorecard as a *sanity check* ("if this were a simple up/down bet, Kelly would suggest X%"). Diagnostic only. Never wired to sizing.

**Could explicit Kelly meaningfully improve CAGR/Calmar? Probably not:**
- **Leverage sizing:** Kelly-on-leverage would push A4 toward ~2-3× leverage. Alpaca crypto is spot-only. Moot.
- **Allocation between accounts:** Kelly would push MORE into A4 (highest CAGR) at the cost of deeper drawdowns. Our Calmar-first sweep already picked 33% + ladder-to-40% — *more* conservative than Kelly. Moving to Kelly here would worsen Calmar for marginal CAGR gain.
- **Concentration (top-N):** Already handled by robust-opt. Explicit Kelly redundant.

**What we ARE missing from the Kelly-adjacent family:**
- **C4 (vol-scaling overlay not applied in live)** — this IS Kelly-on-leverage and it's the one legitimate place where Kelly-adjacent math would improve the live book. Fix per C4 = "turn on Kelly-on-leverage in live, with cap=1.0 because no margin."

**The deleted `calculate_position_size` was misaligned with our strategy architecture from day one.** It was written as if strategies produce "trade recommendations with known edge + stop loss" — a Phase-3-era aspiration that never fit the Phase-4 signal-to-order pipeline where strategies emit portfolio weights directly. Removal 2026-04-21 corrected an architectural mismatch, not just dead code.

**Bottom line:** Kelly shouldn't be used for per-position sizing in FIRE (wrong strategy architecture). Kelly-on-leverage (vol-scaling) IS the right use and needs C4 to work in live. Cross-account allocation should stay Calmar-first, not Kelly-first, because we're a retirement-bridge compounder with low drawdown tolerance, not an infinite-horizon log-wealth maximizer.

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

**Session 4 — Sim/live parity (Tier 1 NEW) — HIGHEST PRIORITY, ORDERED:**
10. ✅ **C7 (position cap)** — FIXED 2026-04-21 via option C (removed cap entirely; strategy shape is concentration control). R12 closed simultaneously.
11. **C4 (vol-scaling) — decided 2026-04-21: option B.** Implement vol-scaling in live `compute_rebalance` with `scalar_cap=1.0`; strip cap=1.5 from backtest too so sim/live are apples-to-apples. Per-account realized vol from snapshot returns + EWMA. Re-run A2 + A4 validation. `scalar_cap > 1.0` is future research (leverage via CME micros / Coinbase Advanced; file under post-real-money scope). See C4 section for full plan.
12. **C5 (circuit breakers)** — **research question first** (keep/modify/delete the design per the session-3 critical review), then simulate whatever lands in the backtest. Don't mechanically add halt simulation without resolving the design question.
13. **C6 (fee/slippage)** — add per-account transaction-cost layer to backtest (0 bps equity, ~20 bps round-trip crypto). Re-run A4 validation; issue post-cost CAGR.

**Session 5 — Reporting hygiene (Tier 4):**
14. R1: Relabel A2 validation as "holdout only" until walk-forward is implemented.
15. R2: Per-account validation override + never-overridable "retired".
16. R3: Wire strategy-level breakers or delete the claim from docs.
17. R4: try/finally around execute + journal.
18. R6: Align correlation sample to blended CAGR sample in portfolio_fit.
19. R8, R9, R11: Medium-value fixes; pick up as time permits.
20. R12: Delete or wire up the unused Kelly sizing code.
21. R13-R15: Belt-and-suspenders docs / parity footnotes (low priority).

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

**Post sim/live parity audit (2026-04-20 session 2) — OPEN:**

- **C4 vol-scaling live gap** — per-account scope (full table in C4 itself):
  - **A1: clean.** No vol-scaling in config → scalar always 1.0× in backtest. CAGR 27.3% / MaxDD -9.8% / Calmar 2.77 are apples-to-apples with live.
  - **A2: mildly affected.** Backtest scalar range [0.5, 1.5]; live stuck at 1.0. MaxDD understated by ~1-3pp.
  - **A4: materially affected.** Backtest scalar range **[0.1, 1.5]**; live stuck at 1.0 until BTC<MA flip. **A4 backtest MaxDD -11.4% / Calmar 3.98 is understated. Plausible live MaxDD in a real crypto crash is 2-3× the backtest number.** **Do not trust A4 Calmar for real-money sizing until C4 is fixed or the backtest is re-run without vol-scaling.**
- **C5 circuit breakers unsimulated** — backtest Calmar treats a hypothetical -15-20% crash as investable return; live would halt at -15% portfolio DD. Two-sided effect (helps in continued crashes, hurts on V-shaped recoveries). Not yet quantified.
- **C6 fee/slippage** — A4 CAGR 45.2% is ~0.5-1pp optimistic (daily crypto rebalance × 0.1-0.3% spread). Realistic live A4 CAGR closer to **43-45%**. A1/A2 fee drag negligible.
- **C7 position cap** — ✅ **FIXED 2026-04-21** via option C (cap removed entirely; rely on strategy shape for concentration control). A4 will rebalance to 50/50 top-2 as designed when BTC crosses the 125d MA. R12 (dead Kelly code) closed in the same pass. Invariant checks on strategy output added to `compute_rebalance` as replacement defense (loud failure > silent clamp).

**The A3 retirement / A4 weight decisions are not affected by C4-C7** — those decisions compared *relative* Calmar across weight configurations, and all four findings bias the backtest numbers in consistent directions across the 25% / 33% / 40% A4 weight scenarios. The ladder-to-40% direction stands.

The **retired/kept/weight decisions themselves** (A3 retired, A4 at 33%) stood on the Tier 1 predictions; post-fix numbers **confirm** they remain the right calls (corrected weight-sweep: 33% → Calmar 3.76, 25% → 3.50, 40% → 3.94). Ladder to 40% direction intact. **However**, the absolute Calmar numbers in that sweep need to be re-issued post C4/C5/C6 fixes before using them to argue for the 40% upgrade — the 2.0 Calmar threshold in CLAUDE.md's upgrade gate is stated on pre-fix numbers.

---

## References

- `MEMORY.md` (auto-memory) — session-level feedback patterns
- `CLAUDE.md` — current system state (updated 2026-04-20 with audit caveats)
- `DECISIONS_RESOLVED.md` — A3 retirement + A4 @ 33% weight decisions + full context
- Git log 2026-04-18 → 2026-04-20 — the month-2 changes that introduced most of the Tier 2 bugs
