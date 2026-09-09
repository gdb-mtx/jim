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
| 2026-05-06 | A4 live signal stale by 1 day vs backtest (C9/C10) | partial-bar contamination + 1-12h settled-bar publishing delay |
| 2026-07-21 | rebalance-day previews "hung"; frontend 20s timeout masked it | rate-limited S&P refresh at ~50s/batch in the request path |
| 2026-08-08 | refresh-cache "stuck" ~25 min; second click doubled it | Saturday rate-limit ~90s/batch × 24h-TTL expiry landing in-request |
| 2026-08-10 | etf_prices truncated to 903 rows / crypto to 8 coins from 2025 | not yfinance's fault — shared caches writable by short-lookback callers (fixed: canonical floor starts) |
| 2026-08-11 | Combined-tab chart frozen; server reload wedged | uncached SPY download on every 30s poll → session rate-limited into indefinite hangs (blocks, doesn't raise) |
| 2026-09-08 | sp500_prices truncated to 673 rows (2024+); validation "insufficient history" | not yfinance's fault — macro composite's `start="2024-01-01"` refresh had no canonical floor (fixed: `SP500_CACHE_FLOOR` + truncation check on read, HISTORY.md 2026-09-09) |

## 2026-08-11 — Hot-path audit (class-level fix)

After the 08-11 incident, all 54 yfinance call sites were enumerated and
classified. Current state, kept true by construction:

- `api/` contains zero direct yfinance calls.
- Every request-reachable path is cache-fronted, and the slow caches are
  warmed from cron (spy_filter force-refreshed 4h; sp500_prices warmed
  non-forced on the SPY cron leg) so TTLs never expire into a user request.
- Remaining live calls are cron or manual research scripts only — their
  failure mode is a late cron, never a frozen dashboard.
- Cache writes always download from canonical floor starts (2005 equities /
  2020 crypto, full universe), so no caller can truncate a shared cache.

Each one got a defensive patch (threading.Lock, atomic writes, plausibility
bands, retry+coverage gate, schema cross-check, 0-row guard). The system
is now meaningfully hardened — but it's hardening *around* an unreliable
source rather than fixing the source.

## 2026-08-13 — Backtest crypto caches migrated to Alpaca appends

The 05-06 migration (below) fixed the live path but left the backtest
crypto caches on yfinance full re-downloads — which meant a nightly
false-alarm window: after 00:00 UTC, yfinance serves "two-days-ago +
today's partial" with yesterday missing (C10 pattern) for up to 12h,
the freshness pill went red, and the refresh button couldn't fix it.
On 08-13 Alpaca had the settled bar hours before yfinance published it.

New refresh shape in `data/crypto.py` (the "$0 stack" append economics
below, realized): banked yfinance history stays; every bar inside a
coin's Alpaca listing range is (re)written from Alpaca on each refresh
(`combine_first`, self-healing); caches store settled bars only. BNB
(no Alpaca listing) appends best-effort from yfinance and never blocks.
yfinance is load-bearing only for bootstrap (cache loss → pre-Alpaca
history re-download). Alpaca listing floors are ragged (ADA relisted
2026-02, XRP 2024-01, DOT 2023-08) — `combine_first` handles this
per-coin with no special cases. Full narrative: HISTORY.md 2026-08-13.

Remaining yfinance dependencies: equity caches (S&P 500, ETF universe,
SPY filter, VIX — the Phase-5 question) + BNB appends + crypto bootstrap.

## 2026-05-06 — Live crypto signal computation migrated to Alpaca

Hybrid path (option 3 below) implemented for the crypto leg ahead of the
broader Phase-5 evaluation:

- New `data/alpaca_crypto_bars.py` — broker-native daily bars for live use.
- Backtest crypto path stays on yfinance (Alpaca's history doesn't reach
  the project's 2018 BTC / 2020 universe historical floor).
- Live call sites swapped: `execution/rebalance.py` (crypto signal +
  portfolio paths), `strategies/portfolio_config.py` (BTC trend filter),
  `scripts/filter_check.py` (BTC scope), `api/routes/portfolio.py`
  (`/api/portfolio/filters`).
- BNB dropped from live universe (regulatory non-listing on Alpaca; see
  HISTORY.md C11). Backtest universe unchanged.
- C10 (yfinance settled-bar publishing delay) structurally resolved.

Equities (A1/A2) and the SPY trend filter remain on yfinance for now —
same hybrid principle applies, but no live↔backtest gap was observed for
those paths. Migration of the equity-data path stays a Phase-5 question.

## Candidates worth evaluating (post-Fly)

1. **Alpaca market data API** — already authenticated, included with the
   broker account. Strong contract: explicit symbols in / explicit
   symbols out, no silent contamination. Coverage: stocks Alpaca trades,
   crypto pairs Alpaca trades. Gaps: `^VIX` (CBOE — not on Alpaca), some
   of the broader ETF universe may not have full history. Likely fits
   the live-decision path (filter checks, rebalance signals) cleanly;
   may not fully replace yfinance for 2010-onward backtest data.
   **Free-tier caveat (2026-08-11):** bars are IEX-feed only, so closes
   can diverge a few cents from official consolidated closes on quiet
   names. Before cutover, run both sources for a full rebalance cycle
   and diff the signal output (ranks, not prices — rank-stable = safe).

2. **Polygon / Tiingo / EOD Historical** — paid feeds with proper
   time-series APIs and schema guarantees. ~$20-50/month at low tier.
   Cleanest fix, real money cost. Worth pricing if Alpaca's coverage
   doesn't fully close the gap.

3. **Hybrid** — Alpaca for live-decision data (filter checks +
   rebalance signal generation), keep yfinance for offline backtest /
   research where a corrupt cache produces "weird chart" not "wrong
   trade." Lowest-risk migration path.

### The $0 stack (2026-08-11 addition)

The deep history (2005+ equities, 2020+ crypto) is already banked in our
parquets — a replacement source only has to *append* daily bars, which
changes the economics: the full migration is possible at zero dollars.

- **Equity daily bars:** Alpaca free tier (IEX caveat above), or one of
  the consolidated-close free options below.
- **VIX / VIX9D / VIX3M:** CBOE's own free historical CSVs
  (cdn.cboe.com). This is an *upgrade* over yfinance — Yahoo republishes
  CBOE, so the CSVs are the primary source. Stable URLs, no key. Closes
  the doc's `^VIX` gap for free.
- **Consolidated market-wide closes (append path):** Stooq free bulk EOD
  (whole US market, no API key), or Polygon free tier's grouped-daily
  endpoint — every US ticker's official close in one API call/day (free
  tier's 2-year history cap is irrelevant for appends).
- Paid tier (#2) becomes optional rather than the "cleanest fix."

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
