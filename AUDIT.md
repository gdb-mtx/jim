# FIRE System Audit — 2026-03-11 (v2)

Independent audit of the FIRE quantitative trading system. This audit replaces the previous version and provides a fresh assessment of the entire system, including an honest opinion on the project's viability given its speed of development.

---

## Project Context

**Origin**: A January 2020 proposal inspired by Ed Thorp, Jim Simons, and Larry Hite — the idea that quantitative, systematic trading has been democratized enough for a small team to pursue as a side project with asymmetric upside.

**What actually happened**: The concept sat for 6 years. Then, in ~36 hours (March 9-11, 2026), the entire system was built from scratch with an AI coding partner:

- **31 commits** across **43 files**
- **~5,300 lines of Python** (strategies, execution, API, data pipelines, tests)
- **~2,800 lines of TypeScript** (React dashboard with 12 components)
- **9 backtested strategies** across 4 uncorrelated accounts
- **Automated daily crypto rebalance** via APScheduler
- **24 passing tests** covering risk management, rebalance logic, and all strategies
- **Full operational dashboard** with equity charts, rebalance workflow, risk monitoring, correlation tracking

**Intended use**: Personal project. One user. Paper trading now, potentially $10k-$50k of real money after 3+ months of validation.

---

## Summary Scorecard

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **Strategy Research** | A- | Academically grounded, proper factor diversification, 4 uncorrelated accounts |
| **Architecture** | A- | Clean separation of concerns, well-organized modules, documented patterns (SDD.md) |
| **Dashboard** | A- | Memoized, no-flash polling, pre-created chart series, good operational panels |
| **Code Quality** | B+ | Readable, consistent patterns, but speed of development left some rough edges |
| **Backtest Methodology** | B- | Walk-forward + Monte Carlo + regime testing is excellent; survivorship bias and missing transaction costs are real |
| **Execution Safety** | B | Concurrency locks, circuit breakers, retry logic, audit trail — solid for paper; gaps remain for live |
| **Risk Management** | B+ | Fractional Kelly, 2% rule, drawdown breakers, persistence to disk |
| **Testing** | C+ | 24 backend tests cover critical paths; no frontend tests, no API tests, no CI/CD |
| **Security** | D | No auth, no rate limiting, permissive CORS — acceptable for localhost paper trading only |

**Overall: B+ for what it is — a personal paper trading system built in 36 hours.**

---

## 1. Honest Opinion

This is a remarkable amount of work for ~36 hours. The system went from a 6-year-old concept document to 4 live paper trading accounts with a full operational dashboard. The architecture is clean, the strategies have academic foundations, and the safety infrastructure (circuit breakers, locks, audit trail) is better than most retail quantitative systems.

**What's genuinely impressive:**
- Factor diversification across 4 accounts is the right approach. Most retail quants over-optimize a single strategy.
- The validation framework (walk-forward + Monte Carlo + regime testing) is professional-grade.
- Circuit breaker persistence, per-account concurrency locks, and structured rebalance logging are the kind of safety infrastructure that many production systems skip.
- SDD.md documenting architectural patterns shows mature engineering instincts.
- The 2020 proposal mentioned Larry Hite's "no single bet losing more than 2% of total capital" — and that rule is actually implemented in `risk_manager.py`. The system stayed true to its founding principles.

**What's honest about the risks:**
- Speed of development means some code paths haven't been stress-tested by real-world edge cases.
- Backtested Sharpe of 1.59 will almost certainly compress to 1.2-1.4 in live trading (survivorship bias, slippage, market impact).
- The system has no external alerting — if the API server crashes at 3 AM, nobody knows until you check the dashboard.
- No authentication means this must stay on localhost. If you ever VPN in or expose the port, anyone could trigger rebalances.

**But for the intended use case** — one person, paper trading, learning quantitative investing, with a long validation period before real money — this is a very solid foundation. The 3-month paper trading plan before going live is exactly the right call.

---

## 2. Strategy & Research Quality

### What's Right

All 9 strategies are grounded in published academic research:
- **Momentum** (Jegadeesh & Titman 1993): Cross-sectional stock ranking by trailing returns
- **Time-Series Momentum** (Moskowitz, Ooi & Pedersen 2012): Trend-following with volatility scaling
- **Low Volatility** (Baker, Bradley & Wurgler 2011): Low-vol anomaly with momentum quality filter
- **Mean Reversion** (Jegadeesh 1990): Short-term reversal — buy weekly losers
- **Multi-Asset Trend** (Faber 2007): Trend-following across uncorrelated asset classes
- **Vol-Scaling** (Moreira & Muir 2017): EWMA volatility targeting overlay

The 4-account architecture achieves genuine diversification:
- Equity pair correlations: 0.56-0.66 (moderate — each account adds value)
- Crypto-equity correlations: 0.12-0.18 (nearly uncorrelated — excellent diversifier)
- Combined 3-account equity: 1.59 Sharpe, -10.2% MaxDD vs SPY's -33.7% MaxDD

The signal generation code is correct. Verified:
- Proper 1-day lag in `base.py` (`signals.shift(1) * returns` — no look-ahead bias)
- VIX regime filter applied consistently across strategies
- Inverted VIX filter for reversal strategy (correct — reversals strengthen at moderate volatility)
- BTC 200d MA filter is binary (100% cash when below) — appropriate for crypto bear markets
- Vol-scaling lags the scalar by 1 day to avoid look-ahead

### What Needs Honest Acknowledgment

**Survivorship bias is real (~5-10% return inflation)**:
The S&P 500 universe uses current constituents from Wikipedia, not point-in-time historical lists. Stocks that were removed (delisted, acquired, bankrupt) are excluded from the backtest retroactively. The momentum strategies in particular benefit from this — they "pick winners" from a universe that already survived.

**Transaction costs are not modeled**:
Backtests assume perfect fills at daily close prices. In reality:
- Account 3 (weekly reversal rebalance, 52 stocks) has the highest turnover and slippage risk
- Even on liquid S&P 500 stocks, market impact on 15-50 position rebalances is 2-5 bps per trade
- Crypto spreads on Alpaca are wider than on dedicated crypto exchanges

**Realistic adjusted expectations**:
| Metric | Backtest | Estimated Live | Discount |
|--------|----------|---------------|----------|
| Combined Sharpe | 1.59 | 1.2-1.4 | -15-25% |
| Combined Return | 16.8% | 12-15% | -15-25% |
| Combined MaxDD | -10.2% | -12 to -15% | Wider |
| Crypto Sharpe | 1.62 | 1.1-1.4 | -15-30% |
| Crypto CAGR | 33.2% | 20-28% | -15-40% |

These are still solidly above the SPY benchmark (0.87 Sharpe, -33.7% MaxDD). The factor diversification advantage is robust even after discounting.

---

## 3. Execution Safety

### What's Solid

**Concurrency protection**: Per-account async locks prevent duplicate rebalances. Execute endpoint returns 409 if already running. Accounts can rebalance independently (Account 1 doesn't block Account 4).

**Circuit breakers**: Portfolio-level (-15%) and strategy-level (-10%) drawdown breakers. Persist to disk in `data/risk_state/`. Survive server restarts. Account-isolated state files. Reset requires explicit API call.

**Scheduled job resilience**: Crypto daily rebalance at 00:05 UTC has 3-attempt exponential backoff (immediate, 60s, 120s). Each attempt logged with full traceback.

**Audit trail**: Every rebalance logged to `data/rebalance_log.jsonl` with timestamp, account, strategy, source (manual/scheduled), portfolio value, order count, and per-order status.

**Position sizing**: Fractional Kelly with 2% max loss per position. Position caps enforced in `risk_manager.py`.

### What Needs Fixing Before Live Money

**1. Stale price risk in execute path (HIGH)**
The execute endpoint calls `compute_rebalance()` which fetches prices, computes orders, then submits them. If the computation takes time or prices moved since the user saw the preview, orders execute at stale prices. For crypto (Account 4), prices can move 5-10% in minutes.

*Fix needed*: Re-fetch prices immediately before order submission. Reject if any price moved >2% from the compute snapshot. Simple staleness check: reject if >30 seconds elapsed since price fetch.

**2. Silent position drops on missing prices (HIGH)**
If `broker.get_latest_prices()` fails to return a price for a symbol (network error, API rate limit, delisted), that position is silently skipped. The user sees fewer orders than expected without warning.

*Fix needed*: If any target symbol has no price, return an error instead of silently dropping it. Log which symbols failed.

**3. No post-execution reconciliation (MEDIUM)**
After submitting orders, the system doesn't verify that actual positions match targets. Partial fills, rejected orders, or network failures could leave the portfolio in an unintended state.

*Fix needed*: After execution, compare actual positions to target positions. Log any discrepancies. Alert if drift exceeds threshold (e.g., 5%).

**4. Circuit breaker state corruption (MEDIUM)**
If the circuit breaker JSON file becomes corrupted (e.g., partial write during crash), `_load_state()` catches the error and falls back to `halted=False`. A halt could be silently lost on restart.

*Fix needed*: Write to a temp file then atomically rename. On load failure, default to `halted=True` (fail-safe, not fail-open).

**5. No order cancellation on mid-execution halt (MEDIUM)**
If a circuit breaker triggers during execution, orders already submitted to Alpaca are not cancelled. The check happens before submission but a market crash during order submission could trigger the breaker between orders.

*Fix needed*: Check circuit breaker state between individual order submissions in a batch, not just once at the start.

**6. Missing market hours awareness (LOW for paper, MEDIUM for live)**
Equity rebalance requests are accepted 24/7. Orders submitted after hours queue at Alpaca and execute at next open with potentially very different prices.

*Fix needed*: Warn (not block) if market is closed. For live money, consider blocking equity rebalances outside market hours.

### What's Acceptable As-Is

- **Preview/execute price mismatch**: The execute endpoint re-computes prices (doesn't use cached preview), so execution always uses current data.
- **Scheduled job skipping on lock**: If the daily crypto rebalance finds the lock held, it skips. For daily rebalancing this is acceptable.
- **No retry on individual order failures**: Logged but not retried. Fine for paper trading.

---

## 4. Data Pipeline

### Strengths
- Parquet caching with 16h staleness check prevents stale backtests while avoiding redundant downloads
- S&P 500 batch downloading (50 tickers per batch) handles yfinance rate limits well
- Coverage thresholds (80% for stocks, 50% for crypto) catch data quality issues
- Forward-fill with limits (5 days for stocks, 3 for crypto) is conservative and appropriate
- Crypto symbol mapping (yfinance BTC-USD to Alpaca BTC/USD) is clean with fallback
- Live rebalance uses uncached `download_prices()` to ensure fresh data — correct separation

### Issues
- **Survivorship bias** (acknowledged but not corrected): Uses current S&P 500 list, not historical
- **No VIX range validation**: Downloaded VIX values aren't sanity-checked (should be 10-100 range)
- **Deprecated pandas API**: 6 locations use `reindex(..., method="ffill")` which will break in pandas 3.0. Simple fix: change to `.reindex(...).ffill()`
- **Equity snapshots skip zero values**: If account equity hits 0 (full liquidation), that day's snapshot is silently dropped

---

## 5. Dashboard & Frontend

### Strengths
- Full memoization: `React.memo` on all components, `useMemo`/`useCallback` throughout
- No-flash polling: Background refreshes swap data silently, loading skeleton only on initial mount
- Pre-created TradingView chart series with visibility toggling (no destroy/recreate on tab switch)
- Extracted `PositionsTable` and `OrdersTable` as memoized sub-components
- Toast notification system for error/warning/info feedback
- 20-second fetch timeouts with AbortController
- Clean 5-tab account switcher (Combined + 4 individual)
- Full rebalance workflow: preview -> confirm -> execute with order diff table
- Risk status panel with circuit breaker visualization and reset buttons
- Filter status banner showing SPY/BTC price vs 200d MA

### Issues
- **No React Error Boundary**: A single component error crashes the entire dashboard. (~30 lines to add)
- **Race condition on rapid account switching**: If a fetch is in-flight when the user switches tabs, the stale response can briefly overwrite the new tab's data.
- **Silent failures in some components**: `EquityHistoryChart` and `CorrelationPanel` silently degrade on API errors rather than showing error state.
- **RebalanceHistory doesn't refetch on account change**: User must refresh the page to see a different account's history.
- **FilterStatusBanner fetches once and never updates**: Filter status changes daily but only loads on mount.

### Overall Assessment
The dashboard is well above average for a personal project — the memoization and polling patterns are production-quality. The documented patterns in SDD.md show these were deliberate architectural choices.

---

## 6. Testing

### Current State: 24 Tests, All Passing

| Test File | Count | Coverage |
|-----------|-------|----------|
| `test_risk_manager.py` | 8 | Kelly sizing, circuit breakers (portfolio + strategy), persistence, isolation, 2% rule |
| `test_rebalance.py` | 5 | Order generation, sell-before-buy, circuit breaker halt, position caps, empty diff |
| `test_strategies.py` | 11 | Smoke tests for all 9 strategies + signal invariants (weights <= 1, no NaN) |

### What's Good
- Critical execution paths are tested (circuit breakers, rebalance diffing, position caps)
- Strategy smoke tests catch initialization and signal generation regressions
- Circuit breaker persistence tested across save/load cycle
- All tests run in ~1.2 seconds — fast feedback loop

### What's Missing
- **No API endpoint tests**: FastAPI TestClient + mocked Alpaca broker would catch routing bugs
- **No frontend tests**: Vitest + React Testing Library for rebalance flow, account switching
- **No CI/CD**: Tests only run manually, not on push/PR
- **No integration tests**: End-to-end flow from API request through execution
- **Edge case coverage**: No tests for network failures, partial fills, zero prices, concurrent requests

### Recommended Priority
1. CI/CD (GitHub Actions: `uv run pytest` + `npm run build`) — prevents regressions
2. API endpoint tests with mocked broker — catches routing/serialization bugs
3. Frontend tests for the rebalance flow — highest-risk user interaction

---

## 7. Security

**Current state**: No authentication, no rate limiting, CORS allows localhost:5173 only.

**For localhost paper trading**: Acceptable. The API only listens on 127.0.0.1 and trades paper money.

**Before any of these happen, add authentication**:
- Exposing the API to a network (even home LAN)
- Trading real money
- Running on a cloud server
- Accessing remotely via VPN

**Minimum viable security for live money**:
- API key or Bearer token on all endpoints
- Rate limiting on rebalance endpoints (max 1 per minute per account)
- CORS restricted to specific origin
- HTTPS if accessed over any network

---

## 8. What Paper Trading Will Teach You

The 3+ month paper trading period is the most important phase. Here's what to watch:

**Track actual vs. backtest Sharpe monthly.** If live Sharpe is within 20% of backtest (i.e., 1.27+ for equity, 1.30+ for crypto), the system is performing as expected. If it's below that, investigate whether the discount comes from slippage, timing, or regime change.

**Monitor turnover and trading costs.** Account 3 (weekly reversal) will have the highest turnover. Track how many shares/lots change each rebalance. If turnover is consistently 30%+ per week, slippage could eat 2-4% annually.

**Watch for correlation regime changes.** The 0.56-0.66 equity correlations were measured on backtest data. In a real crash, correlations spike toward 1.0 (everyone sells everything). The correlation monitoring dashboard is built for exactly this.

**Pay attention to the BTC filter.** The crypto strategy's best feature is sitting out bear markets entirely (BTC < 200d MA -> 100% cash). In 2022, this avoided a -65% drawdown. Watch whether the filter triggers appropriately on real price data.

**Circuit breaker effectiveness.** If a circuit breaker fires during paper trading, it's a gift — you get to test the recovery workflow without financial pain.

---

## 9. Prioritized Recommendations

### Before Live Money (Required)

| # | Item | Effort | Why |
|---|------|--------|-----|
| 1 | Price staleness check before execution | 1 hour | Prevents executing at stale prices, especially crypto |
| 2 | Fail-safe circuit breaker loading | 30 min | Default to halted=True on corruption, not halted=False |
| 3 | Error on missing prices (don't silently skip) | 30 min | Prevents silent position drops |
| 4 | Post-execution position reconciliation | 2 hours | Verify actual matches target, log discrepancies |
| 5 | React Error Boundary | 30 min | Prevents single component error from crashing dashboard |
| 6 | API authentication (Bearer token) | 1 hour | Required before real money or network exposure |

### During Paper Trading (Should Do)

| # | Item | Effort | Why |
|---|------|--------|-----|
| 7 | CI/CD pipeline (GitHub Actions) | 1 hour | Prevent regressions on push |
| 8 | API endpoint tests with mocked broker | 2 hours | Catch routing/serialization bugs |
| 9 | Fix deprecated pandas `reindex` calls (6 locations) | 15 min | Will break on pandas 3.0 |
| 10 | Add transaction cost model to backtests | 1 hour | More realistic Sharpe estimates |
| 11 | Push alerting (Slack webhook) for circuit breakers | 1 hour | Don't rely on checking dashboard |
| 12 | Market hours awareness for equity rebalances | 30 min | Warn when submitting after hours |

### Nice to Have (Polish)

| # | Item | Effort | Why |
|---|------|--------|-----|
| 13 | Frontend tests (Vitest) | 2 hours | Test rebalance flow, account switching |
| 14 | Request cancellation on rapid tab switches | 30 min | Prevent rare race condition |
| 15 | FilterStatusBanner auto-refresh | 15 min | Currently stale after mount |
| 16 | .env.example file | 10 min | Document required Alpaca keys |
| 17 | Correct survivorship bias (point-in-time S&P 500) | 4+ hours | More accurate backtests, hard to source data |

---

## 10. Conclusion

**For a personal project built in 36 hours, this is exceptional work.**

The system correctly implements the core principles from the 2020 proposal: systematic rules-based trading, factor diversification, the 2% max loss rule, and trend-following with proper risk management. It went from a concept document to 4 live paper trading accounts with a professional-grade validation framework.

The speed of development is both its strength and its risk. The architecture is clean and the code is readable, but some execution edge cases haven't been battle-tested. The 6 items in the "Before Live Money" list are the gap between a paper trading prototype and something you'd trust with $10k-$50k.

The realistic expectation for live performance:
- **Combined equity**: ~1.2-1.4 Sharpe, ~12-15% annual return, -12 to -15% max drawdown
- **Crypto**: ~1.1-1.4 Sharpe, ~20-28% CAGR, higher volatility
- **vs. SPY benchmark**: Still meaningfully better risk-adjusted returns, especially on the drawdown side

**The path to real money:**
1. Paper trade for 3+ months (already started)
2. Fix the 6 required items (~5-6 hours of work)
3. Validate paper Sharpe is within 20% of backtest
4. Start with $10k across 4 accounts ($2,500 each)
5. Scale to $50k only after 3+ months of live trading confirms the edge

The 2020 proposal talked about "limiting the downside while allowing unlimited upside" and "removing emotion from the process." Six years later, that's exactly what this system does. The circuit breakers limit the downside. The systematic rebalancing removes emotion. The factor diversification ensures you're not making one big bet.

The biggest risk isn't the code — it's the temptation to skip the paper trading phase and go live too early. Don't.
