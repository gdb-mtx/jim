# Strategies — Scorecards, Universes & Filters

> **Status (2026-08-12):** Sizing made honest, then revalidated. The live vol scalar now comes bit-for-bit from the signal book (exact backtest parity; the old account-equity estimator is a diagnostic only), **margin financing above 1.0× gross is modeled in every backtest at 5.5%/yr**, and vol_target moved 0.15→0.18 per a juice grid net of costs + financing (cap raise past 1.5 rejected in every combo). Net result: **A1 PASS 33.0%** and **A2 MARGINAL 12.9%** — A2's drop from 16.8% is entirely the financing drag its old PASS booked for free; the Q4 Calmar < 1.0 kill/swap trigger stands. Live test in progress: Q3-checkpoint cycle 1 closes at the 2026-08-20 rebalance (which also resets the book to ~70/30 A1/A2). July context (A4 retirement, book-level overlay, cap restoration) in `HISTORY.md`.

## OOS scorecard (live accounts)

Fresh-data OOS per the CAGR-first framework (revalidated 2026-08-12, test window 2023-01-03 → 2026-08-11). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION.md`.

Numbers below are post the C1+C2+C4+C6 fix pack (calendar/ppy convention, BTC MA warmup, live vol-scaling parity, transaction costs), C9 (crypto partial-bar signal contamination, 2026-05-06), C10 (Alpaca-bars migration for live crypto, 2026-05-06), and the 8-coin universe switch (2026-05-17, backtest now uses `LIVE_CRYPTO_UNIVERSE` matching Alpaca's tradeable set — see HISTORY.md C11). See `HISTORY.md` for what each fix changed. **C3 (S&P 500 survivorship bias)** is the one remaining open caveat — A1 standalone CAGR is ~1-2pp overstated; not fixed pre-real-money.

| Strategy | Status | CAGR | MaxDD | Calmar | Bootstrap p5 | Win rate |
|---|---|---|---|---|---|---|
| **Stock Momentum + SPY + book vol-scaling (Acct 1)** ⚠ C3 | PASS (09-09) | **+34.6%** | **-13.4%** | **2.59** | +14.3% | 58% |
| **Trend + Low-Vol, cap=1.5 (Acct 2)** | MARGINAL (09-09) | **+11.8%** | **-13.1%** | **0.90** | +8.8% | 54% |
| *Crypto Momentum (Acct 4)* — RETIRED 2026-07-13 | RETIRED | *+38.6%* | *-12.6%* | *3.05* | — | — |
| *Reversal + Momentum (Acct 3)* — retired; hosts tail pilot | RETIRED | *+14.5%* | *-7.2%* | *2.03* | — | — |

No fresh combined-book OOS number is published for the current configs — the 08-20 rebalance moves the allocation to ~70/30 A1/A2, and the old 50/50 figure (24.1%, pre-financing-model) is superseded. Shadow tracking of retired A4 runs in `scripts/live_scorecard.py` (reopen threshold: shadow > +10%).

A1 PASSes the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates (revalidated 2026-09-09 with the re-ranking grid phased to the live calendar — `REBALANCE_ANCHOR`, HISTORY.md 2026-09-09 — vol_target 0.18, financing modeled: OOS CAGR 34.6%, MaxDD -13.4%, Calmar 2.59, ratio 185%, bootstrap p5 +14.3%; the 08-12 run at the old phase read 33.0% / 2.49). **A2 is MARGINAL as of 2026-09-09** — OOS CAGR 11.8%, Calmar 0.90, ratio 78% (08-12 old phase: 12.9% / 1.05 / 84%). The phase change alone moved A2's Calmar from 1.05 to 0.90 — under the 1.0 gate — which says how thin the edge is. Nothing about the strategy changed: the 07-18 PASS at 16.8% booked ~3pp of margin financing for free, and the vol_target raise is a no-op for A2 (raw vol ~7% pins the scalar at the cap either way). MARGINAL is allowed for paper; the pre-committed Q4 trigger stands — live Calmar < 1.0 at the review → kill or DBMF swap. **A4 RETIRED 2026-07-13** — walk-forward edge decay (newest window +9.6% CAGR, Calmar 0.87) + bug-era live drag never re-validated; canonical narrative in `HISTORY.md`.

A3's historical numbers retained as MARGINAL per last validation; strategy available in Backtests → Building Blocks as `reversal_blend`.

## Research/building-block strategies (in-sample only)

Never went to a live account, OOS not measured:

| Strategy | Sharpe (IS) | Return (IS) | MaxDD (IS) | Notes |
|---|---|---|---|---|
| Short-Term Reversal + SPY | 1.41 | 12.7% | -10.0% | Anti-momentum |
| Low Volatility + SPY | 1.32 | 14.7% | -11.9% | Defensive |
| Blended Portfolio + SPY Filter | 1.37 | 14.2% | -9.3% | 60/20/20 momentum |
| Stock Momentum (S&P 500) | 1.16 | 15.9% | -18.6% | No filter |
| Cross-Sectional Momentum | 0.85 | 7.0% | -10.8% | ETF-based |
| Time-Series Momentum | 0.85 | 6.2% | -15.2% | ETF-based |
| Multi-Asset Trend | 0.76 | 5.8% | -13.0% | Crisis alpha |
| Dual Momentum (Antonacci) | 0.83 | 7.6% | -19.9% | ETF-based |
| Multi-Timeframe Momentum | 0.67 | 4.1% | -11.0% | Regime fail |
| *SPY Buy & Hold (benchmark)* | *0.87* | *14.5%* | *-33.7%* | — |

## Universes

- **ETF Universe**: 18 assets (8 broad ETFs + 9 sector ETFs + SHY cash proxy)
- **Multi-Asset Universe**: SPY, EFA, TLT, GLD, DBC (5 uncorrelated asset classes)
- **Stock Universe**: 501 S&P 500 stocks (cached parquet, survivorship bias noted). Coverage gate: trailing 500 trading days ≥80% non-NaN — lets recent S&P additions enter the rotation once they have ~2y of history without corrupting backtests (pre-IPO NaN rows propagate to NaN ranks → excluded from selection for periods before the ticker existed).
- **Crypto Universe**: 9 coins for backtest, 8 coins for live (BTC, ETH, SOL, BNB*, ADA, AVAX, LINK, DOT, XRP). *BNB is in the backtest universe but excluded from live — Alpaca doesn't list it (regulatory non-listing post 2023 SEC v. Binance, see HISTORY.md C11). `data/crypto.CRYPTO_UNIVERSE` is the 9-coin backtest set; `data/crypto.LIVE_CRYPTO_UNIVERSE` is the 8-coin tradeable subset that live signal computation operates on. Quality/volume-gated by design — top-cap L1s and major smart-contract platforms only. Deliberate exclusion of memecoins (DOGE, SHIB, PEPE, etc.) and low-float altcoins. An ML or alternative crypto strategy may use different data sources (on-chain metrics, funding rates, exchange flows) or a modified universe if justified by the thesis.

## Filters & overlays

- **VIX regime filter**: Reduce exposure at VIX > 35, exit at VIX > 45. Reversal strategy has inverted VIX filter (boost at moderate VIX).
- **SPY 200-day MA trend filter**: Reduce exposure by 50% when SPY < 200-day MA (Faber 2007).
- **BTC 125-day SMA trend filter**: Binary 100% cash when BTC < 125d SMA (sat out all of 2022). Robust-opt picked 125d from 200d/150d/125d/100d grid.
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting at **18% (0.15→0.18 on 2026-08-12**, per a juice grid net of costs + financing; cap raise past 1.5 rejected in every combo), scalar [0.5, 1.5], on **both** live accounts since 2026-07-18 — A2 at the account level (original design restored) and A1 at the book level (recaptures the diversification benefit that per-name 20% vol targeting discarded; the strategy historically ran 40-70% gross, 22% in the 2026 all-semi cohort). >1.0 extends into Reg-T margin (equity only; crypto clamped 1.0) and **pays 5.5%/yr financing in every backtest since 2026-08-12** — pre-August levered numbers booked the margin for free. The live scalar is captured from the signal book itself (bit-for-bit backtest parity; the account-equity estimator with its three divergences is retired to a diagnostic), and a daily cron drift check compares broker positions to rebalance targets between cycles.
- **VIX tail signal + A3 paper pilot** (2026-07-18): VIX9D/VIX3M ≥ 1.10 auto-buys ~5%-of-book VIXY in A3 (paper), exits on signal clear. Guards in `execution/tail_leg.py`; history in `data/tail_leg_log.jsonl`.
- **Macro composite** (2026-07-18): 5-sensor regime alert (credit/dollar/VIX-TS/breadth/defense), alert-only — led SPY-200d by 34-56 days in 2018/2020/2022; exposure-scaling tested and rejected (`docs/research/MACRO_COMPOSITE_EVAL.md`).
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone.
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period.

## Strategy source files

`strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`.
