# Strategies — Scorecards, Universes & Filters

> **Operator sentiment (2026-05-26):** Numbers below are backtest-OOS, not realized live performance. Live execution drag is real (A4 ran +4.6% signal-only vs −7.3% live in its first 3 weeks). After ~one month of clean live data post-bug-fixes, the operator's read is that these strategies are **middle-of-the-road** — they work, they're disciplined, but they are not delivering what George was hoping for. **The response is to actively hunt for additive strategies, not coast.** Treat the scorecard as factual record of what's running today, not as a final book composition.

## OOS scorecard (live accounts)

Fresh-data OOS per the CAGR-first framework (test window ends 2026-04-20). Validation reports in `data/validation_reports/`; state in `data/risk_state/validation_state.json`. Full scorecard docs in `VALIDATION.md`.

Numbers below are post the C1+C2+C4+C6 fix pack (calendar/ppy convention, BTC MA warmup, live vol-scaling parity, transaction costs), C9 (crypto partial-bar signal contamination, 2026-05-06), C10 (Alpaca-bars migration for live crypto, 2026-05-06), and the 8-coin universe switch (2026-05-17, backtest now uses `LIVE_CRYPTO_UNIVERSE` matching Alpaca's tradeable set — see HISTORY.md C11). See `HISTORY.md` for what each fix changed. **C3 (S&P 500 survivorship bias)** is the one remaining open caveat — A1 standalone CAGR is ~1-2pp overstated; not fixed pre-real-money.

| Strategy | Status | CAGR | MaxDD | Calmar | MAR | Sortino | *Sharpe (info)* |
|---|---|---|---|---|---|---|---|
| **Crypto Momentum (Acct 4)** | PASS | **+38.6%** | **-12.6%** | **3.05** | 3.05 | — | *1.76* |
| **Stock Momentum + SPY (Acct 1)** ⚠ C3 | PASS | **+27.2%** | **-9.9%** | **2.76** | 2.76 | 2.10 | *2.04* |
| **Trend + Low-Vol (Acct 2)** | MARGINAL | **+11.0%** | **-7.3%** | **1.51** | 1.51 | — | *1.37* |
| *Reversal + Momentum (Acct 3)* — retired | RETIRED | *14.5%* | *-7.2%* | *2.03* | — | — | — |

A1 PASSes the CAGR ≥ 15% / Calmar ≥ 1.0 / OOS/IS ≥ 70% gates (revalidated 2026-07-13). **A4 RETIRED 2026-07-13** — walk-forward edge decay (newest window +9.6% CAGR, Calmar 0.87) + bug-era live drag never re-validated; canonical narrative in `HISTORY.md`. **A2 is MARGINAL** — backtest used to leverage the low-vol leg up to 1.5× in calm regimes that live could never realize; cap=1.0 alignment brings it to 11%. MARGINAL is allowed for paper per `execution/validation_gate.py`.

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
- **Vol-scaling overlay** (Moreira & Muir 2017): EWMA vol targeting on Account 2 (and Account 4 until its 2026-07-13 retirement).
- **Key insight**: Factor diversification (momentum + low-vol + reversal + multi-asset trend) provides far better risk-adjusted returns than diversifying within momentum alone.
- **Warmup trimming**: Equity curves and metrics exclude the flat warmup period.

## Strategy source files

`strategies/trend_following.py`, `strategies/momentum.py`, `strategies/stock_momentum.py`, `strategies/multi_asset_trend.py`, `strategies/low_volatility.py`, `strategies/mean_reversion.py`, `strategies/crypto_momentum.py`, `strategies/portfolio.py`.
