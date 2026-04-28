# Data sources — observation and forward direction

Standing note. Not a roadmap, not an audit item. The observation is that
yfinance has been the single largest source of operational pain in this
system, and that pattern is worth naming so future-decisions can act on it.

## The framing

We've been treating yfinance as a reliable data feed. It isn't, and was
never intended to be. yfinance scrapes Yahoo Finance — a free consumer site
with no API contract, no SLA, no schema guarantee. Most of our pain has
come from expecting it to behave like a paid data API.

## Incident log (2026-04-20 → 2026-04-27)

Every cache-corruption / silent-data incident in the last ~2 weeks roots
to yfinance behavior. Parquet was just the medium that recorded it.

| Date | Symptom | yfinance behavior |
|---|---|---|
| 2026-04-20 | 91/451 S&P refresh | mid-batch ticker drop, no error |
| 2026-04-21 | BTC cache held $9-$29 values | returned wrong series under right ticker |
| 2026-04-22 | crypto cache became `[XLE, ^VIX]` | concurrent-call response cross-contamination |
| 2026-04-22 | vix.parquet held IWM-shaped values (~$276) | same contamination |
| 2026-04-22 | spy_filter held `[EFA, SPY]` | same contamination |
| 2026-04-26 | S&P cache landed at 488/501 stocks | 13 long-history tickers silently dropped on batch refresh |
| 2026-04-26 | 5 concurrent refreshes → 429s + SQLite corruption | rate-limit + yfinance internal cache fragility |
| 2026-04-27 | 4 caches written empty (0 rows) | DNS-fail returns column-correct, row-empty DataFrame |

Each one got a defensive patch (threading.Lock, atomic writes, plausibility
bands, retry+coverage gate, schema cross-check, 0-row guard). The system
is now meaningfully hardened — but it's hardening *around* an unreliable
source rather than fixing the source.

## Candidates worth evaluating (post-Fly)

1. **Alpaca market data API** — already authenticated, included with the
   broker account. Strong contract: explicit symbols in / explicit
   symbols out, no silent contamination. Coverage: stocks Alpaca trades,
   crypto pairs Alpaca trades. Gaps: `^VIX` (CBOE — not on Alpaca), some
   of the broader ETF universe may not have full history. Likely fits
   the live-decision path (filter checks, rebalance signals) cleanly;
   may not fully replace yfinance for 2010-onward backtest data.

2. **Polygon / Tiingo / EOD Historical** — paid feeds with proper
   time-series APIs and schema guarantees. ~$20-50/month at low tier.
   Cleanest fix, real money cost. Worth pricing if Alpaca's coverage
   doesn't fully close the gap.

3. **Hybrid** — Alpaca for live-decision data (filter checks +
   rebalance signal generation), keep yfinance for offline backtest /
   research where a corrupt cache produces "weird chart" not "wrong
   trade." Lowest-risk migration path.

## What this is not

- Not a parquet criticism. Parquet is fine. The cache-storage layer is
  not the source of pain; the source is what we feed into it.
- Not a "ditch yfinance" mandate. It's adequate for backtest / research
  where stakes are low and a re-run fixes things.
- Not pre-Fly work. The current defensive layer (locks, plausibility,
  atomic writes, 0-row guards) is sufficient for paper trading. Real
  money should not run on yfinance for the live decision path.

## Decision marker

When real-money phase begins (DEPLOYMENT_PLAN Phase 5), this evaluation
becomes load-bearing. Until then, this note exists so we don't keep
patching symptoms while forgetting we already diagnosed the cause.
