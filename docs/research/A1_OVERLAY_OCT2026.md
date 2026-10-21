# A1 overlay research — sign-aware vol scaling and idle-cash yield

> **STATUS (2026-10-21): CLOSED.** Sign-aware gating REJECTED for A1 (costs
> CAGR, Calmar flat); idle-cash yield is a REAL-MONEY CHECKLIST item
> (+2.5pp OOS CAGR at current rates; paper earns nothing, backtest stays
> yield-free for parity). Nothing here changes the live path. Harness:
> `scripts/a1_overlay_research.py` (re-run anytime; no look-ahead — every
> gate uses information through D-1 like the production scalar).

## Why

The vol overlay is sign-agnostic: it measures how *calm* the book's recent
returns are, not whether they're positive, so a grinding drawdown of small
down days reads as low vol and gets the 1.5× cap. That is how A2 died
(levered 1.2× of equity on a losing low-vol book). After the 10-20
rebalance A1 sat at the cap, four months into a −6.7% drawdown — so the
question was whether A1 has the same exposure. Second question: the
backtest earns 0% on the ~45–55% of the account the overlay leaves in cash.

## 1. Sign-aware vol scaling (A1, net of 5 bps costs + 5.5% financing)

| variant | OOS CAGR | OOS maxDD | Calmar | full CAGR | full maxDD | Calmar | time at cap (OOS) |
|---|---|---|---|---|---|---|---|
| **production (cap 1.5 always)** | **+31.6%** | −16.5% | **1.92** | +19.8% | −19.5% | 1.02 | 46% |
| no overlay (1.0×) | +24.2% | −12.8% | 1.89 | +16.1% | −15.6% | 1.03 | 0% |
| cap 1.0 below SPY 200d | +31.0% | −16.1% | 1.92 | +19.9% | −18.4% | **1.08** | 45% |
| cap 1.0 in own drawdown > 3% | +27.7% | −14.0% | 1.98 | +16.7% | −16.1% | 1.04 | 18% |
| cap 1.0 in own drawdown > 5% | +28.0% | −14.9% | 1.87 | +17.8% | −17.0% | 1.05 | 22% |
| cap 1.0 in own drawdown > 8% | +28.6% | −15.4% | 1.87 | +18.5% | −17.4% | 1.06 | 30% |
| cap 1.0 if own 63d return < 0 | +29.1% | −14.7% | 1.98 | +18.6% | −17.6% | 1.05 | 39% |
| SPY 200d + drawdown > 5% | +27.8% | −14.9% | 1.86 | +17.8% | −17.0% | 1.05 | 22% |

OOS = 2023-01-01 → 2026-10-20; full = 2010-10 → 2026-10-20.

**Read:** every gate trades 2.5–4pp of OOS CAGR for 1–2.5pp of drawdown
and leaves Calmar where it was. The A2 failure mode does not transfer:
A1's own de-risk stack (SPY-filter halving, VIX regime) already handles
the bad tape, and the quiet-drawdown days the overlay levers are followed
by recoveries it also levers. The one gate with no CAGR cost — cap 1.0
below the SPY 200d — adds +0.06 full-sample Calmar and nothing in the
OOS; a note for a future crisis-era re-run, not a change. The scale of
the exposure also matters: 1.5× is relative to the strategy's own ~0.30
gross, i.e. the account is ~46% invested at the cap — not A2's 1.2× of
equity on margin.

## 2. Idle cash yield (3-month T-bill, FRED DTB3)

| variant | avg cash (OOS) | OOS CAGR | Calmar | full CAGR | Calmar | Δ OOS CAGR |
|---|---|---|---|---|---|---|
| production | 45% | +34.1% | 2.12 | +20.6% | 1.07 | **+2.5pp** |
| cap 1.0 in own drawdown > 5% | 51% | +30.9% | 2.17 | +18.6% | 1.10 | +2.9pp |
| SPY 200d + drawdown > 5% | 51% | +30.7% | 2.15 | +18.6% | 1.10 | +2.9pp |

T-bill 4.10% now; OOS average 4.49%; 2010–2015 average 0.06%.

**Read:** at current rates the idle cash is worth +2.5pp CAGR and +0.2
Calmar — a feature of the rate regime, not a historical constant (zero in
2010–2015). The paper account earns nothing on cash, so the backtest
stays yield-free to keep live↔signal parity honest. **Real-money
checklist:** sweep idle cash to SGOV/BIL (or confirm Alpaca's cash
interest rate) — it is the cheapest +2pp in the system and it carries no
strategy risk. Note the gated variants hold more cash (51%), so the yield
narrows but does not close their CAGR gap to production.

## What this does not say

Both runs are one strategy on one 16-year sample with one rate regime in
the OOS. The sign-aware rejection should be re-run after the first live
crisis-era cycle; the cash yield should be re-priced whenever T-bills move
more than a point.
