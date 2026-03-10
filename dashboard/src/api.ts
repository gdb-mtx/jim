const BASE_URL = "http://localhost:8000/api";

export async function fetchStrategies() {
  const res = await fetch(`${BASE_URL}/strategies/`);
  return res.json();
}

export async function fetchAccounts() {
  const res = await fetch(`${BASE_URL}/portfolio/accounts`);
  return res.json();
}

export async function fetchPortfolio(account = 1) {
  const res = await fetch(`${BASE_URL}/portfolio/summary?account=${account}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchBacktest(strategyId: string, start = "2010-01-01") {
  const res = await fetch(
    `${BASE_URL}/backtests/run/${strategyId}?start=${start}`
  );
  return res.json();
}

export async function fetchEquityCurve(strategyId: string, start = "2010-01-01") {
  const res = await fetch(
    `${BASE_URL}/backtests/equity/${strategyId}?start=${start}`
  );
  return res.json();
}

export async function fetchPositions(account = 1) {
  const res = await fetch(`${BASE_URL}/portfolio/positions?account=${account}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchOrders(account = 1, status = "all", limit = 50) {
  const res = await fetch(
    `${BASE_URL}/orders/history?account=${account}&status=${status}&limit=${limit}`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function fetchCombinedPortfolio() {
  const res = await fetch(`${BASE_URL}/portfolio/combined`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchEquityHistory(account = 0) {
  const res = await fetch(`${BASE_URL}/portfolio/history?account=${account}`);
  return res.json();
}

export async function fetchCorrelation() {
  const res = await fetch(`${BASE_URL}/portfolio/correlation`);
  return res.json();
}

export async function takeSnapshot(account?: number) {
  const url =
    account !== undefined
      ? `${BASE_URL}/portfolio/snapshot?account=${account}`
      : `${BASE_URL}/portfolio/snapshot`;
  const res = await fetch(url, { method: "POST" });
  return res.json();
}
