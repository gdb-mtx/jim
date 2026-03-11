const BASE_URL = "http://localhost:8000/api";
const TIMEOUT_MS = 20_000;

async function fetchWithTimeout(
  url: string,
  opts?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetchWithTimeout(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
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
    `${BASE_URL}/backtests/run/${strategyId}?start=${start}`
  );
}

export async function fetchEquityCurve(strategyId: string, start = "2010-01-01") {
  return fetchJSON(
    `${BASE_URL}/backtests/equity/${strategyId}?start=${start}`
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

export async function takeSnapshot(account?: number) {
  const url =
    account !== undefined
      ? `${BASE_URL}/portfolio/snapshot?account=${account}`
      : `${BASE_URL}/portfolio/snapshot`;
  return fetchJSON(url, { method: "POST" });
}
