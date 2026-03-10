const BASE_URL = "http://localhost:8000/api";

export async function fetchStrategies() {
  const res = await fetch(`${BASE_URL}/strategies/`);
  return res.json();
}

export async function fetchPortfolio() {
  const res = await fetch(`${BASE_URL}/portfolio/summary`);
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

export async function fetchPositions() {
  const res = await fetch(`${BASE_URL}/portfolio/positions`);
  return res.json();
}

export async function fetchOrders(status = "all", limit = 50) {
  const res = await fetch(
    `${BASE_URL}/orders/history?status=${status}&limit=${limit}`
  );
  return res.json();
}
