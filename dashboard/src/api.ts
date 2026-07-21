const BASE_URL = "http://localhost:8001/api";
const DEFAULT_TIMEOUT_MS = 20_000;
// Backtests can trigger cold-cache yfinance downloads (S&P 500 = ~5min for
// 451 tickers). 20s is too short after overnight inactivity.
const BACKTEST_TIMEOUT_MS = 360_000;
// Rebalance execute submits orders serially to Alpaca (~0.5-1s per order);
// a 40-order rebalance needs 40-50s. Use a generous timeout so the frontend
// waits for the backend to finish, matching the backend file-lock guarantee
// that only one execute runs per account at a time.
const REBALANCE_EXECUTE_TIMEOUT_MS = 180_000;
// Preview computes signals + fetches live prices serially (~1 Alpaca call
// per symbol); a 30+ symbol book needs 25-40s. The 20s default aborts it.
const REBALANCE_PREVIEW_TIMEOUT_MS = 120_000;

async function fetchWithTimeout(
  url: string,
  opts?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

async function fetchJSON<T>(
  url: string,
  opts?: RequestInit,
  timeoutMs?: number,
): Promise<T> {
  const res = await fetchWithTimeout(url, opts, timeoutMs);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail)
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchStrategies() {
  return fetchJSON(`${BASE_URL}/strategies/`);
}

export async function fetchAccounts() {
  return fetchJSON(`${BASE_URL}/portfolio/accounts`);
}

export async function fetchPortfolio(account = 1) {
  return fetchJSON(`${BASE_URL}/portfolio/summary?account=${account}`);
}

export async function fetchBacktest(strategyId: string, start = "2010-01-01") {
  return fetchJSON(
    `${BASE_URL}/backtests/run/${strategyId}?start=${start}`,
    {},
    BACKTEST_TIMEOUT_MS,
  );
}

export async function fetchEquityCurve(strategyId: string, start = "2010-01-01") {
  return fetchJSON(
    `${BASE_URL}/backtests/equity/${strategyId}?start=${start}`,
    {},
    BACKTEST_TIMEOUT_MS,
  );
}

export async function fetchPositions(account = 1) {
  return fetchJSON(`${BASE_URL}/portfolio/positions?account=${account}`);
}

export async function fetchOrders(account = 1, status = "all", limit = 50) {
  return fetchJSON(
    `${BASE_URL}/orders/history?account=${account}&status=${status}&limit=${limit}`
  );
}

export async function fetchCombinedPortfolio() {
  return fetchJSON(`${BASE_URL}/portfolio/combined`);
}

export async function fetchEquityHistory(account = 0) {
  return fetchJSON(`${BASE_URL}/portfolio/history?account=${account}`);
}

export async function fetchCorrelation() {
  return fetchJSON(`${BASE_URL}/portfolio/correlation`);
}

export async function fetchDataFreshness() {
  return fetchJSON<import("./types").DataFreshnessResponse>(
    `${BASE_URL}/portfolio/data-freshness`
  );
}

export async function refreshCache() {
  return fetchJSON<{ refreshed: string[]; errors: string[]; ok: boolean }>(
    `${BASE_URL}/portfolio/refresh-cache`,
    { method: "POST" },
    BACKTEST_TIMEOUT_MS,
  );
}

export async function takeSnapshot(account?: number) {
  const url =
    account !== undefined
      ? `${BASE_URL}/portfolio/snapshot?account=${account}`
      : `${BASE_URL}/portfolio/snapshot`;
  return fetchJSON(url, { method: "POST" });
}

export async function fetchRiskStatus() {
  return fetchJSON<import("./types").RiskStatusResponse>(
    `${BASE_URL}/portfolio/risk`
  );
}

export async function resetCircuitBreaker(account: number) {
  const params = new URLSearchParams({ account: String(account) });
  return fetchJSON<{ account: number; can_trade: boolean }>(
    `${BASE_URL}/portfolio/risk/reset?${params}`,
    { method: "POST" }
  );
}

export async function fetchRebalancePreview(
  strategyId: string,
  account: number
) {
  return fetchJSON<import("./types").RebalancePreview>(
    `${BASE_URL}/orders/rebalance/preview?strategy_id=${strategyId}&account=${account}`,
    { method: "POST" },
    REBALANCE_PREVIEW_TIMEOUT_MS,
  );
}

export async function executeRebalance(strategyId: string, account: number) {
  return fetchJSON<import("./types").RebalanceExecuteResult>(
    `${BASE_URL}/orders/rebalance/execute?strategy_id=${strategyId}&account=${account}`,
    { method: "POST" },
    REBALANCE_EXECUTE_TIMEOUT_MS,
  );
}

export async function fetchRebalanceHistory(limit = 50, account?: number) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (account && account > 0) params.set("account", String(account));
  return fetchJSON<import("./types").RebalanceHistoryEntry[]>(
    `${BASE_URL}/orders/rebalance/history?${params}`
  );
}

export async function fetchFilterStatus() {
  return fetchJSON<import("./types").FilterStatusResponse>(
    `${BASE_URL}/portfolio/filters`
  );
}

export async function fetchFilterMonitorState() {
  return fetchJSON<import("./types").FilterMonitorState | null>(
    `${BASE_URL}/portfolio/filter-state`
  );
}

export async function fetchPlausibilityState() {
  return fetchJSON<import("./types").PlausibilityState>(
    `${BASE_URL}/portfolio/plausibility`,
  );
}

// --- Ops dashboard ------------------------------------------------------

export async function fetchOpsScheduler() {
  return fetchJSON<import("./types").OpsSchedulerResponse>(
    `${BASE_URL}/ops/scheduler`
  );
}

export async function fetchOpsFilters() {
  return fetchJSON<import("./types").OpsFiltersResponse>(
    `${BASE_URL}/ops/filters`
  );
}

export async function fetchOpsValidation() {
  return fetchJSON<import("./types").OpsValidationResponse>(
    `${BASE_URL}/ops/validation`
  );
}

export async function fetchOpsEvents(
  limit = 50,
  opts?: { source?: string; type?: import("./types").OpsEventType; since?: string },
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (opts?.source) params.set("source", opts.source);
  if (opts?.type) params.set("type", opts.type);
  if (opts?.since) params.set("since", opts.since);
  return fetchJSON<import("./types").OpsEventsResponse>(
    `${BASE_URL}/ops/events?${params}`
  );
}
