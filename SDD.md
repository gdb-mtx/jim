# Software Design Decisions

Architectural decisions and patterns learned from building this project. Reference for future projects with a similar stack (React + TypeScript frontend, Python + FastAPI backend, real-time data polling).

---

## Frontend Architecture (React + TypeScript)

### Polling & Live Data Updates

**Never gate rendered content behind a loading flag during background refreshes.** Only show loading skeletons on initial load (when no data exists yet). For subsequent polling updates, keep stale data visible while the fetch is in flight and swap it in silently when the response arrives.

```tsx
// BAD: flashes skeleton every poll cycle
const [loading, setLoading] = useState(false);
const refresh = () => {
  setLoading(true);            // skeleton replaces the whole page
  fetch(...).finally(() => setLoading(false));
};
if (!data || loading) return <Skeleton />;

// GOOD: skeleton only on first load, data swaps in seamlessly
const refresh = () => {
  fetch(...).then(setData);    // overwrites stale data, no flash
};
if (!data) return <Skeleton />;
```

**Don't clear state on view/tab switches.** When switching between views that each have their own data (e.g., account tabs), keep the previous view's data visible until the new data arrives. Clearing state to null forces a loading skeleton flash. The brief mismatch (~200ms) of showing old data is far less jarring.

```tsx
// BAD: causes flash
const switchView = (id) => {
  setData(null);
  setView(id);
};

// GOOD: old data visible briefly, then swapped
const switchView = (id) => {
  setView(id);  // useEffect fetches new data, overwrites when ready
};
```

### Memoization Strategy

**Start with memoization from day one.** Add `React.memo`, `useMemo`, and `useCallback` as you build, not as a retrofit. The cost of adding them upfront is trivial; the cost of debugging unnecessary re-renders later is not.

Rules of thumb:
- **`React.memo`** every component that receives props from a parent that re-renders frequently (e.g., a parent with polling). Self-contained components that fetch their own data and take no props (or only stable primitives) benefit the most.
- **`useMemo`** any derived/computed object or array. Inline object literals and `array.sort()`/`.filter()`/`.slice()` create new references every render, defeating `React.memo` on children that receive them.
- **`useCallback`** any function passed as a prop to a memoized child (especially event handlers like `onSwitch`, `onSelect`). Without it, the child re-renders every time the parent does.

```tsx
// Memoize computed data
const sortedItems = useMemo(
  () => [...items].sort((a, b) => b.value - a.value),
  [items]
);

// Memoize callbacks passed to memoized children
const handleSelect = useCallback((id: string) => {
  setSelected(id);
}, []);

// Wrap child components
const MyPanel = memo(function MyPanel({ data }: Props) { ... });
```

### Expensive Components (Charts, Maps, Rich Editors)

**Pre-create expensive instances once, update data in place.** Libraries like TradingView Lightweight Charts, Mapbox, or Monaco Editor are expensive to instantiate. Never destroy and recreate them on data changes.

Pattern: Create the instance and all possible sub-elements (e.g., chart series) on mount with `visible: false`. On data changes, call `setData()` on existing elements and toggle visibility. This eliminates blank flashes during transitions.

```tsx
// Create chart + all series once on mount
useEffect(() => {
  const chart = createChart(container, options);
  for (const config of ALL_POSSIBLE_SERIES) {
    const series = chart.addSeries(LineSeries, { ...config, visible: false });
    seriesRefs.current.set(config.key, series);
  }
  return () => chart.remove();
}, []);

// On view change: update data + toggle visibility (no destroy/recreate)
useEffect(() => {
  for (const [key, series] of seriesRefs.current) {
    if (shouldShow(key, currentView)) {
      series.setData(fetchedData[key]);
      series.applyOptions({ visible: true });
    } else {
      series.applyOptions({ visible: false });
    }
  }
}, [currentView, fetchedData]);
```

### Component Extraction for Large Tables

**Extract data tables into their own memoized components.** Tables with 50+ rows are the largest DOM subtrees and the most expensive to reconcile. When they live inline in a parent that re-renders on a polling interval, the entire table re-renders every cycle even if the data hasn't changed. Extracting them into `memo()`-wrapped components with stable props (via `useMemo`) lets React skip them entirely.

### Independent Polling Coordination

**Avoid multiple uncoordinated polling intervals.** If a parent polls every 30s and a child independently polls every 30s, the page re-renders twice per cycle from two offset timers. Either:
- Have the parent fetch all data (including what the child needs) in one coordinated poll, passing it down as props
- Or give components with independent polls significantly different intervals (e.g., parent 30s, child 60s+) so they don't compound

Prefer the first approach for data that's always visible. Reserve independent polling for components that are rarely shown or need different freshness guarantees.

---

## Backend Architecture (Python + FastAPI)

### API Design for Polling Frontends

**Return typed, structured responses.** Use Pydantic models (or typed dicts) for every endpoint response. When the frontend's `fetch()` calls return `unknown`/`any`, type bugs accumulate silently. Define response types once in a shared types file and cast/validate at the boundary.

**Keep polling endpoints lightweight.** If the frontend polls every 30s, the endpoint must respond well under 1s. Precompute or cache expensive calculations; never run full strategy backtests in a polling handler.

### Async Endpoints with Blocking Dependencies

**Never call blocking functions directly from `async def` endpoints.** FastAPI runs `async def` handlers on the main event loop. If a handler calls a synchronous function that does network I/O (Alpaca API, yfinance), file I/O (parquet, JSON), or heavy computation (pandas, numpy), the entire server blocks — no other request can be served until it returns.

This is invisible during development because each endpoint works fine in isolation. It only surfaces under concurrent load (e.g., the dashboard polling 5 endpoints simultaneously while a rebalance downloads 451 stock prices). The symptom: the server appears hung, CPU spins, and the frontend shows "API not connected."

```python
# BAD: blocks event loop for 2-10 seconds
@router.post("/rebalance/preview")
async def preview(account: int):
    broker = get_broker(account)
    result = compute_rebalance(broker, strategy)  # downloads prices, runs strategy
    return result

# GOOD: offloads to thread pool, event loop stays free
@router.post("/rebalance/preview")
async def preview(account: int):
    broker = get_broker(account)
    result = await asyncio.to_thread(
        compute_rebalance, broker, strategy
    )
    return result
```

This applies to **all** blocking calls: Alpaca REST API (`get_account()`, `get_positions()`, `get_orders()`), data downloads (`download_prices()`, `download_and_cache()`), file reads (`pd.read_parquet()`, `json.loads(path.read_text())`), and heavy computation (`get_correlation_report()`).

For simple one-call endpoints, `await asyncio.to_thread(broker.get_positions)` is clean enough. For endpoints with multiple blocking calls, wrap them in a `_compute()` closure:

```python
@router.get("/combined")
async def combined_summary():
    def _compute():
        # All blocking calls happen in thread pool
        for acct in accounts:
            broker = get_broker(acct)
            data = broker.get_account()      # Alpaca API
            positions = broker.get_positions() # Alpaca API
            ...
        return result

    return await asyncio.to_thread(_compute)
```

**Alternative**: You can also declare handlers as plain `def` (not `async def`), and FastAPI will automatically run them in a thread pool. But `async def` + explicit `to_thread` is preferred when the handler mixes async operations (like `async with lock`) with blocking calls.

### Concurrent Execution Safety

**Use per-resource async locks for mutating operations.** When the same operation can be triggered by both a scheduler and a user (e.g., rebalance), protect it with an async lock keyed to the resource (e.g., account ID). Return 409 Conflict if the lock is already held rather than queuing or silently dropping.

### Credentials Management

**Use environment variables with a suffix convention for multi-instance setups.** For multiple accounts/instances of the same service, suffix env vars (`API_KEY`, `API_KEY_2`, `API_KEY_3`) and select via a parameter. Keep a `.env.example` (or `settings.yaml.example`) in the repo with placeholder values. The real file is gitignored.

---

## General Patterns

### Startup Script

**Provide a single `start.sh`** that launches both backend and frontend, kills stale processes on the relevant ports, and handles shell environment quirks (e.g., sourcing nvm for Node). Developers should never need to remember multiple terminal commands.

**Gate the frontend on backend readiness.** Start the backend first, poll its health endpoint, and only launch the frontend after the backend is confirmed ready. If the frontend starts first, every API call fails and the user sees a broken page. Also check that the backend process is still alive during the wait — don't silently loop for 30 seconds if it crashed on startup.

```bash
# Start backend
$UV run uvicorn api.main:app --reload --port 8001 &
BACKEND_PID=$!

# Wait for backend health check BEFORE starting frontend
for i in $(seq 1 30); do
  curl -s --max-time 2 http://localhost:8001/api/health > /dev/null 2>&1 && break
  kill -0 $BACKEND_PID 2>/dev/null || { echo "Backend crashed"; exit 1; }
  sleep 1
done

# Only now start frontend
npm run dev &
```

### Server Startup Work

**Never block the server from accepting requests with slow initialization.** If the backend needs to backfill data, sync with external APIs, or compute caches on startup, run that work in a background thread/task. The health endpoint should respond immediately so the startup script (and load balancers) can proceed.

```python
# BAD: blocks server startup for 10+ seconds
@asynccontextmanager
async def lifespan(app):
    for acct in accounts:
        backfill_from_api(acct)   # 4 API calls, 4 parquet writes
    take_all_snapshots()          # 8 more API calls
    yield

# GOOD: server starts immediately, work happens in background
@asynccontextmanager
async def lifespan(app):
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_backfill)  # non-blocking
    yield
```

### Batch I/O Operations

**Never read-modify-write in a loop.** If you need to append N rows to a file (parquet, CSV, SQLite), collect all rows first, then do one read + one write. Reading and writing the full file per row turns O(N) into O(N^2) I/O.

```python
# BAD: reads + writes parquet 60 times for 60 new rows
for row in new_data:
    df = pd.read_parquet(path)
    df = pd.concat([df, row])
    df.to_parquet(path)

# GOOD: one read, one write
df = pd.read_parquet(path)
new_df = pd.DataFrame(new_rows)
df = pd.concat([df, new_df])
df.to_parquet(path)
```

### Cache External Data Downloads

**Always cache external API data to disk with a staleness check.** If endpoints download market data, weather data, or any slow external fetch, cache the result to a file (parquet, JSON) and serve from cache on subsequent requests. Add a `max_age_hours` parameter so the cache auto-refreshes daily but avoids re-downloading on every server restart or page load.

```python
# BAD: downloads 18 tickers from yfinance on every call (~5-10s)
def get_etf_prices():
    return yf.download(symbols, start="2010-01-01")

# GOOD: cache to parquet, re-download only when stale
def get_etf_prices(max_age_hours=16):
    cache_path = DATA_DIR / "etf_prices.parquet"
    if cache_path.exists():
        age = (time.time() - cache_path.stat().st_mtime) / 3600
        if age < max_age_hours:
            return pd.read_parquet(cache_path)
    prices = yf.download(symbols, start="2010-01-01")
    prices.to_parquet(cache_path)
    return prices
```

Keep separate cache files for different data scopes (e.g., `etf_prices.parquet` vs `spy_filter.parquet`). Leave the uncached version available for code paths that genuinely need fresh data (e.g., live trade execution).

### Audit Trails

**Log all mutating operations to a structured append-only file (JSONL).** Every rebalance, trade, or state change gets a timestamped JSONL entry with full context (who triggered it, what parameters, what happened). This is invaluable for debugging and reconciliation.

### Circuit Breakers and Safety

**Persist safety state to disk, not just memory.** If the process restarts, circuit breaker flags, halt states, and risk limits should survive. Use a simple JSON file or SQLite, not in-memory flags that reset on deploy.
