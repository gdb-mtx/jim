"""
FastAPI Backend — Serves strategy data to the React dashboard.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, strategies, backtests, orders

app = FastAPI(title="FIRE Trading API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
