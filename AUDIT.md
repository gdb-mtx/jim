# FIRE System Audit — 2026-03-11

Comprehensive audit of the FIRE quantitative trading system covering frontend code quality, backend architecture, testing, security, and production readiness.

---

## Summary Scorecard

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **Strategy Research** | A- | Academically grounded, good factor diversification |
| **Architecture** | B+ | Clean separation, sensible abstractions |
| **Dashboard** | B | Functional, good UX, needs error boundaries |
| **Code Quality** | B | Readable, well-structured, but inconsistent error handling |
| **Backtest Validity** | C+ | Survivorship bias + warmup trimming inflate metrics ~10-15% |
| **Execution Safety** | C | No retries, no concurrency locks, no partial fill handling |
| **Risk Management** | C- | Circuit breakers exist but don't survive restarts |
| **Security** | D | No auth, no rate limiting, permissive CORS |
| **Testing** | F | Zero tests, zero CI/CD |
| **Production Readiness** | D | Paper trading works; real money would be reckless |

**Overall: B- as a prototype, D+ as production software**

---

## 1. Frontend Code Quality & Architecture

### Strong Points
- **Strict TypeScript Configuration** (`strict: true` in tsconfig.app.json) — no implicit `any`, unused variables flagged, strict null checks
- **Well-organized component structure**: 7 focused, single-responsibility components (~1,880 total lines)
- **Clean separation**: `EquityHistoryChart`, `CorrelationPanel`, `StrategyPanel`, `LivePortfolio`, etc.
- **Reusable utilities**: `Tooltip`, `MetricCard`
- **ESLint + React Hooks rules enforced** with React Refresh for HMR
- **Proper useState/useEffect patterns** with useRef for TradingView chart integration
- **Cleanup functions** for event listeners and chart disposal
- **No console.log() statements** found in production code

### Issues

#### Inconsistent Error Handling (Critical)
- **Silent failures** in API client (`api.ts`):
  - `fetchOrders()` returns `[]` on error — silently hides failures
  - Other functions throw — inconsistent patterns
- **Overly broad catch blocks**:
  - `catch(() => setError(true))` — no error type, message, or logging
  - `catch(() => setReport(null))` — silently clears data on any error
  - `catch(() => [])` — can't distinguish "no data" from "failed"
- No error recovery or retry logic for transient failures
- No user-facing error messages beyond generic "API not connected" banner
- Correlation Panel silently fails if data < 20 days; no logging

#### Missing Error Boundaries (High)
- No React Error Boundary component
- Single error in any component crashes entire dashboard
- If `EquityHistoryChart` throws, entire `LivePortfolio` tab fails

#### Loading State Inconsistencies (Medium)
- `EquityHistoryChart` shows "Loading equity data..." but can timeout silently
- `LivePortfolio` shows "Loading portfolio..." for 30s refresh interval — no timeout handling
- No skeleton loaders; abrupt placeholder text

#### Type Safety Gaps
- API responses not validated — trusts backend types implicitly
- `api.ts` uses `.json()` without try-catch; JSON parse errors not handled
- No TypeScript `as const` for strategy IDs — refactoring risk
- `CorrelationMatrix` has fragile index math with minimal guards

#### Chart Library Edge Cases (Medium)
- Charts created once, updated via setData — no null checks
- Resize listener not cleaned up if component unmounts during setup
- No handling for empty data arrays (chart renders blank without warning)
- TradingView Charts v5 can be slow with >10k data points (no aggregation)

#### Race Conditions (Medium)
- `EquityHistoryChart` fetches on account change but doesn't cancel pending requests
- Rapid account switching causes multiple parallel fetches (inefficient)
- `LivePortfolio` sets state after component unmounts if fetch completes post-unmount

#### Performance Issues
- No data memoization: `StrategyPanel` re-groups strategies on every render
- No virtualization for strategy list or positions table (OK for current size ~15-50 items)
- Re-renders chart on every equity data update (no diffing)
- `EquityHistoryChart` renders 5 series simultaneously (heavy)

#### Accessibility & UX
- No ARIA labels or semantic HTML
- Tooltips only work on hover (keyboard users can't access)
- Colors used for meaning without fallback (red/green for P&L) — colorblind unfriendly

---

## 2. Testing Infrastructure

### Status: ZERO TESTS

**Evidence**:
- `/home/user/fire/tests/` directory is empty (only `__init__.py`)
- No test files found (`.test.ts`, `.test.tsx`, `.spec.ts`, `test_*.py`, `*_test.py`)
- No test configuration (no Jest, Vitest, Pytest, Mocha setup)
- No CI/CD pipeline (no GitHub Actions, CircleCI, or GitLab CI)

**Impact**:
- Zero regression protection — refactoring is risky
- No API contract testing — backend changes can silently break frontend
- No strategy validation tests — risk of deploying broken backtests to live accounts
- No integration tests — can't verify dashboard-to-backend-to-Alpaca flow

**Recommendations**:
- **Frontend**: Vitest + React Testing Library (test rendering, state changes, error handling; mock API with `msw`)
- **Backend**: Pytest (test each API endpoint, mock Alpaca API, test circuit breakers)
- **E2E**: Cypress or Playwright for dashboard flows
- **Strategy tests**: Validate equity curves, Sharpe ratio bounds, no NaN/Inf values

---

## 3. Configuration & Build Setup

### Strong Points
- React 19.2.4, TypeScript 5.9.3, Vite 7.3.1 (fast HMR)
- Tailwind CSS 4.2.1 with dark theme via utility classes
- TradingView Lightweight Charts 5.1.0 (industry-standard)
- ESLint with React Hooks rules and TypeScript ESLint integration
- Strict TypeScript enforced project-wide

### Issues

#### Vite Config is Bare Bones
- No `base` path configuration (works for root-only deployment)
- No environment variable handling
- No build optimizations beyond Vite defaults
- No source maps for production debugging

#### Python Dependencies Not Pinned
```toml
alpaca-trade-api >= 3.2.0   # Could jump 3.x → 4.0
fastapi >= 0.135.1
numpy >= 2.4.3
```
- **Risk**: Major version bumps in transitive dependencies without warning
- **Recommendation**: Pin to semver ranges (`alpaca-trade-api = "^3.2"`)

#### Missing Developer Setup
- No `.env.example` file (user must guess what Alpaca keys are needed)
- No "Getting Started" section in docs
- CORS hardcoded to `http://localhost:5173` — fine for dev, will fail in production

---

## 4. Scripts & Deployment

### `scripts/start.sh` Analysis

**Good**:
- Kills stale processes on ports 8000 and 5173
- Waits for backend health check before reporting "ready"
- Shows dashboard and API docs URLs

**Issues**:
- Hardcoded paths (`$HOME/.local/bin/uv`)
- No error handling if backend fails to start (silently waits 15 loops)
- No `.env` loading (Alpaca credentials must already be in shell)
- Race condition: frontend can start before backend is ready

---

## 5. Dependency Security & Freshness

### Frontend (npm)
| Package | Status | Risk |
|---------|--------|------|
| React | 19.2.0 → 19.2.4 available | Low (patch) |
| @vitejs/plugin-react | Latest | OK |
| TypeScript | ~5.9.3 Latest | OK |
| lightweight-charts | 5.1.0 Latest | OK |
| Tailwind CSS | 4.2.1 Latest | OK |

### Backend (pyproject.toml)
| Package | Spec | Risk |
|---------|------|------|
| alpaca-trade-api | >=3.2.0 | **HIGH** — open-ended, could jump major versions |
| fastapi | >=0.135.1 | **MEDIUM** — active project with breaking changes |
| numpy | >=2.4.3 | **MEDIUM** — pandas/sklearn depend heavily |
| yfinance | >=0.2.58 | **LOW** — stable, but Yahoo API can break |

---

## 6. Backtest Validity Concerns

### Survivorship Bias (~5-10% Return Inflation)
- S&P 500 universe uses current constituents, not point-in-time
- Stock momentum picks "winners" from a universe that already survived
- Mitigation: acknowledged in CLAUDE.md but not corrected

### Warmup Trimming (~3-5% Metric Inflation)
- Equity curves exclude flat warmup period (12-month lookback)
- This drops the worst-performing initial segment from Sharpe/MaxDD calculations
- Real performance will include this drag

### Transaction Costs Not Fully Modeled
- Backtests assume commission-free (correct for Alpaca)
- But slippage not modeled — significant for 50+ stock portfolios
- Weekly reversal rebalance (Account 3) has highest turnover/slippage risk

### Estimated Real-World Discount
- Reported combined Sharpe: 1.59 → likely 1.35-1.45 after adjustments
- Still solidly above SPY benchmark (0.87), but margins are tighter

---

## 7. Execution Safety

### Critical Issues for Paper/Live Trading

#### No Concurrency Protection
- Multiple rebalance requests can fire simultaneously
- No mutex/lock on rebalance execution
- Could result in duplicate orders or inconsistent state

#### No Partial Fill Handling
- Rebalance assumes all-or-nothing execution
- Alpaca market orders can partially fill
- No reconciliation between target weights and actual fills

#### Silent Failures in Scheduled Rebalance
- `_daily_crypto_rebalance()` catches broad `Exception` but only logs
- If Alpaca API is down, scheduled job silently fails (no alert)
- No retry logic — crypto momentum at 00:05 UTC is missed if error occurs

#### Circuit Breakers Don't Persist
- Risk manager state is in-memory only
- Server restart resets circuit breaker state
- Could re-enter positions after a drawdown-triggered exit

#### No Request Timeouts
- Frontend fetch calls have no explicit timeout
- Browser will eventually timeout (~30s) but no graceful handling

---

## 8. Security Concerns

- **No hardcoded secrets** in code (Alpaca keys in .env, not committed)
- **CORS permissive in dev** (`allow_origins=["http://localhost:5173"]`) — must be env-gated for prod
- **No authentication** on API endpoints — anyone on the network can trigger rebalances
- **No input validation** on API endpoints beyond type hints
- **No rate limiting** on API endpoints
- **No HTTPS** configured (fine for localhost, needed for any remote access)

---

## 9. Recommended Actions

### Priority 1 (Blockers for Live Money)
1. Add try-catch with proper error logging to all API calls
2. Create React Error Boundary component to prevent full dashboard crashes
3. Add validation for API responses against TypeScript interfaces
4. Document `.env` setup with example file
5. Add timeouts to all fetch() calls (15-30s)
6. Add concurrency locks to rebalance execution
7. Persist circuit breaker state to disk

### Priority 2 (Should Do During Paper Trading)
1. Set up Vitest + React Testing Library (start with 3-5 critical paths)
2. Add pytest to backend (test API endpoints, risk manager, circuit breakers)
3. Create GitHub Actions workflow (lint + test + build)
4. Pin Python dependency versions (use `^` for semver ranges)
5. Add retry logic to scheduled rebalance jobs
6. Handle partial fills in rebalance execution

### Priority 3 (Polish)
1. Add skeleton loaders instead of "Loading..." text
2. Implement request cancellation for rapid account switches
3. Add ARIA labels and keyboard navigation
4. Create production Dockerfile with multi-stage build
5. Add Sentry or similar for error tracking
6. Correct survivorship bias in backtests (use point-in-time constituents)

---

## Conclusion

The FIRE system is a genuinely impressive prototype. The strategy research is academically grounded, the architecture decisions are pragmatic, and the dashboard provides real operational value. Even after discounting for survivorship bias and warmup trimming, the combined portfolio likely delivers a ~1.35-1.45 Sharpe — solidly above benchmark.

The gaps are exactly what you'd expect from a fast build: no tests, inconsistent error handling, no state persistence for safety mechanisms, and execution edge cases not covered. The planned 3-month paper trading window is the right call — use it to harden the system while the strategies prove themselves. If returns hold on paper, going live requires 2-3 focused hardening sessions, not a rebuild.
