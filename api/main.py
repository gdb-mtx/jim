"""
FastAPI Backend — Serves strategy data to the React dashboard.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, strategies, backtests, orders


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: take today's equity snapshots (idempotent)."""
    try:
        from data.snapshots import take_all_snapshots, backfill_from_alpaca

        # Always backfill — fills any gaps since last run (idempotent)
        for acct in (1, 2, 3):
            try:
                backfill_from_alpaca(acct)
            except Exception:
                pass
        take_all_snapshots()
    except Exception as e:
        print(f"Snapshot on startup skipped: {e}")
    yield


app = FastAPI(title="FIRE Trading API", version="0.1.0", lifespan=lifespan)

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
