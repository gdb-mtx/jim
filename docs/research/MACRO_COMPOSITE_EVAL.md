# Macro Composite — pre-registered evaluation (2026-07-18)

Gap 3's early-warning layer (AUDIT_FABLE §5.4). Spec was fixed in
`strategies/macro_composite.py` BEFORE the first evaluation run; this memo
records the one-shot result. No re-tuning against this history.

## Spec (pre-registered)

Five daily price-based sensors, 1 stress vote each — credit (HYG/IEF <
100d SMA), dollar (UUP > 100d SMA), VIX term structure (9D/3M ≥ 1.0),
breadth (% S&P 500 above own 200d < 40%), defensive rotation (XLU/SPY >
100d SMA). Vote→scalar map fixed: 0-1 → 1.0, 2 → 0.85, 3 → 0.70,
4 → 0.55, 5 → 0.40, applied T+1. Deliberately: no ML, no FRED (no
publication lag/revisions), no tunable weights. Data gaps degrade toward
1.0, never toward stress.

## Results (`scripts/macro_composite_eval.py`)

**Early warning: excellent — 3/3 crises, led the SPY-200d filter every
time.**

| Crisis | Composite first de-risk | SPY < 200d | Lead |
|---|---|---|---|
| 2018 Q4 | 2018-09-05 | 2018-10-11 | **36 days** |
| COVID | 2020-01-24 | 2020-02-27 | **34 days** |
| 2022 | **2021-11-26** (5 days after the top) | 2022-01-21 | **56 days** |

**Exposure scaling: rejected.** On the current book (A1+A2, 2026-07-18
configs): OOS Calmar 2.77 → 2.55, CAGR -2.4pp, MaxDD unchanged
(-8.7 → -8.5). Full sample: Calmar 1.64 → 1.40. Bull-cost concentrated in
false-positive years (2019: -8.5pp; 2024: -4.8pp). Cause: the book
already stacks three de-risk layers (SPY filter, per-name vol targeting,
book-level vol scaling) — drawdowns are already shallow, so the scalar's
marginal trimming lands on rallies, not crashes. On raw SPY the scalar
cuts MaxDD -55% → -48% but costs 1.6pp CAGR — same verdict, milder.

## Verdict

- **Shipped as alert-only** (2026-07-18): computed every 4h in the SPY
  filter cron; state fields `macro_votes`/`macro_scalar`/per-sensor;
  macOS notification when the vote count changes and either side is ≥ 2.
  Never multiplies live weights — that path is rejected by this eval and
  should not be revisited without a materially different book (e.g. one
  without the vol-scaling stack).
- **Downstream uses:** timing input for the VIXY tail leg (composite ≥ 3
  alongside VIX9D/VIX3M ≥ 1.10 is the "buy insurance now" configuration);
  context banner for rebalance days; the pre-committed prerequisite for
  any future ML regime work is hereby satisfied without ML.
- Survivorship note: breadth uses the current-constituent panel
  (back-extended), slightly rosy in-sample; irrelevant to the alert use.

## Today (2026-07-17 close)

1/5 votes (dollar). Scalar 1.0. Calm.
