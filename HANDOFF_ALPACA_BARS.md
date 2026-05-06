# Handoff: migrate live crypto signal computation from yfinance → Alpaca bars

This is a self-contained brief for a fresh Claude session. The current
session has been investigating yfinance fragility on the live A4 path
and has agreed that the right structural fix is to move *live* crypto
signal computation off yfinance and onto Alpaca's own crypto bars
endpoint. Backtest historical data stays on yfinance (Alpaca's history
doesn't go back far enough).

## Why this matters

Two recurring failure classes have bitten the live A4 daily rebalance:

1. **C9 (fixed 2026-05-06)**: yfinance returns a partial "today" bar
   mid-day whose close is the current scratch price, not a settled day-
   close. Live signal computation read this as if it were a settled
   bar, producing different rankings at 06:05 UTC vs. 23:55 UTC even
   with no real change in market structure. Patched by dropping today's
   partial bar in `CryptoMomentum.generate_signals` so we use
   yesterday's settled close.

2. **C10 (open 2026-05-06)**: yfinance does NOT publish a settled crypto
   daily bar at exactly UTC midnight — there's a 1-12 hour delay between
   bar close and the settled value being available in their API. At our
   00:05 UTC fire time, yesterday's settled bar typically isn't visible
   yet. So even with C9 fixed, the cache sometimes captures
   "two-days-ago-settled + today's partial" with yesterday entirely
   missing. Result: strategy uses two-days-ago close as "latest" — an
   extra day of staleness vs. backtest.

The full diagnosis is in `HISTORY.md` (search for C9, C10) and
`DATA_SOURCES.md` (which documents yfinance as the root cause of nearly
every cache-corruption incident in this project).

The fix is *not* to chase more yfinance workarounds. It's to use
Alpaca's own bars endpoint for live, since:

- We already authenticate to Alpaca for trading — same API key, no
  separate sign-up
- It's the same source the broker uses internally → settlement aligns
  with what we'll execute against (no third-party-vs-broker mismatch)
- Bars include explicit settlement timing, no partial-bar guessing
- Generous rate limits (1-2 calls per fire is well within free tier)
- No third-party caching layer drift

The catch: Alpaca's crypto data only goes back to ~2021. Backtest needs
to ~2018. So **keep yfinance for backtest historical, use Alpaca for
live**.

## Open questions to resolve in your session (verify before deciding)

1. **Alpaca historical depth on our 9-coin universe.** Hit
   `/v1beta3/crypto/us/bars` for each of `BTC/USD, ETH/USD, SOL/USD,
   BNB/USD, ADA/USD, AVAX/USD, LINK/USD, DOT/USD, XRP/USD` with
   `start=2020-01-01` and report the actual earliest bar per coin. If
   any coin has substantially less history than yfinance for the same
   ticker, that's an architectural constraint to flag.

2. **Alpaca crypto bar timing semantics.** Confirm: does Alpaca's daily
   bar settle at UTC midnight or at some other boundary? Their docs
   should be explicit. The strategy's 21d momentum is sensitive to the
   bar boundary.

3. **Endpoint shape.** Confirm the response format is amenable to a
   drop-in compatible wrapper that returns the same DataFrame shape as
   `download_crypto_prices` (DatetimeIndex, one column per coin,
   ticker symbols matching what `CRYPTO_UNIVERSE` uses — note yfinance
   uses `BTC-USD`, Alpaca uses `BTC/USD`; the wrapper should normalize
   to whichever the strategy expects, probably keep yfinance-style
   `BTC-USD` since that's what the strategy already consumes).

If any of these surface a real blocker, **stop and report back** before
implementing — don't try to work around a fundamental constraint.

## Scope

**In scope:**
- New module: `data/alpaca_crypto_bars.py` — thin wrapper around Alpaca's
  crypto bars endpoint. Returns the same DataFrame shape as
  `download_crypto_prices()` for drop-in compatibility.
- Modify: `strategies/crypto_momentum.py` to optionally read live data
  from Alpaca. The cleanest approach is probably *injection*: keep
  `generate_signals(prices)` unchanged but have the live caller pass in
  Alpaca-sourced prices instead of yfinance-sourced. No conditional
  logic in the strategy itself.
- Modify: `scripts/daily_crypto_rebalance.py` to fetch prices from
  Alpaca for live signal computation.
- Modify: `scripts/filter_check.py` (BTC scope only) — BTC trend filter
  should also use Alpaca bars for consistency.

**Out of scope (do NOT touch):**
- `backtesting/*` — uses yfinance, stays on yfinance.
- `data/crypto.py` — yfinance fetch logic stays as-is for backtest use.
- `scripts/run_validation.py` — uses historical data, stays on yfinance.
- Equity strategies (A1, A2) — different concern, different data layer.
- The frontend — no UI changes needed for this work.

## Implementation outline

1. Read `execution/alpaca_broker.py` for the existing API client and auth
   pattern. Reuse the same client init for the new bars module.
2. Write `data/alpaca_crypto_bars.py`:
   - `def get_crypto_bars(symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame`
   - Returns a DataFrame with DatetimeIndex (tz-naive UTC, matching
     the existing yfinance shape) and columns named `BTC-USD`-style
     (i.e., yfinance-compatible) — *not* `BTC/USD`.
   - Internally translates `BTC-USD` → `BTC/USD` for the API call.
   - Use `Bar.t` for the bar timestamp and `Bar.c` for close.
   - Daily bars: `timeframe="1Day"`.
3. Cache layer: probably skip a persistent cache for live use — fetch
   fresh on every fire. The whole point is to bypass cache-staleness
   issues. Alpaca's API is fast enough that 1-2 calls per fire is cheap.
   Document this choice explicitly in the module docstring.
4. In `daily_crypto_rebalance.py`, swap `download_crypto_prices()` for
   `get_crypto_bars()` on the live signal-computation path. The strategy
   itself doesn't change — it still calls `generate_signals(prices)`.
5. Same swap for the BTC trend filter inputs (the strategy injects BTC
   via `set_btc()`).
6. In `scripts/filter_check.py`, swap the BTC price source to Alpaca for
   the trend-filter computation.

## Verification before merging

1. **Dry-run**: `uv run python3 scripts/daily_crypto_rebalance.py --dry-run`
   should produce the same target weights as the current yfinance path
   (assuming yfinance has settled bars at run time). If they diverge,
   investigate before proceeding.

2. **Single paper fire**: trigger a real rebalance via the script.
   Verify journal entry looks normal, no errors, target weights match
   the dry-run output.

3. **Re-run validation**: `uv run python3 scripts/run_validation.py --account 4`.
   The validation tests run on historical (yfinance) data so they
   *shouldn't* change — but rerun to confirm the validation gate still
   passes for A4 with the modified live path.

4. **2-3 days of paper observation**: leave it running through 2-3 daily
   fires. Compare each fire's signal against what yfinance *would have*
   said at fire time (if you can reproduce that — it's lossy because
   yfinance state changes). The point is to confirm no surprises.

5. **Update content-staleness check**: the dashboard's
   `data_freshness` endpoint currently checks the yfinance crypto cache.
   Once live no longer reads from `crypto_prices.parquet`, the staleness
   check there is decoration only (still useful for backtest dependency,
   but not actionable for live). Either remove `BTC prices` and
   `Crypto universe` rows or relabel them as "backtest-only".

## What this closes

- C10 (yfinance settled-bar publishing delay) — structurally resolved.
- The whole "yfinance returned a row, therefore it's a closed bar"
  assumption class — eliminated for live.
- Live↔backtest semantic parity on bar-close prices for the 21d
  momentum signal — improved (will still have yfinance-vs-Alpaca minor
  divergence on the most recent few bars in backtest, but that's a
  much smaller effect than partial-bar contamination).

## What this does NOT close

- Backtest historical data still comes from yfinance. If yfinance
  permanently drops or corrupts pre-2021 data, backtest is at risk.
  Long-term: investigate Alpaca historical, Polygon, or a paid
  provider for backtest data. Tracked separately in `DATA_SOURCES.md`.
- The cloud migration is a separate piece of work. This change is
  designed to land *before* the cloud migration so the migration
  doesn't have to debut both new hosting AND a new data layer at
  once.

## Reference

- Current session's work and reasoning: see commits `725352d` (C9
  partial-bar fix) and the corresponding `HISTORY.md` entries.
- The `data_freshness` endpoint added a content-staleness check in this
  same session; that check is data-source-agnostic and survives the
  migration unchanged.
- `DATA_SOURCES.md` has the full historical incident log for yfinance.
- `CLAUDE.md` "Test live↔backtest semantic parity" guardrail (added
  this session) is the lesson generalization — apply that lens when
  validating the new path.

## Estimated effort

- Discovery + Alpaca depth verification: 30-60 min
- Module implementation: 1-2 hours
- Call-site swaps: 30-60 min
- Verification (dry-run + single fire + validation re-run): 30-60 min
- Documentation updates (HISTORY.md C10 → resolved, CLAUDE.md
  references): 15 min

Total: ~3-5 hours of focused work for a session that doesn't get sucked
into rabbit holes.

## Reset triggers (per CLAUDE.md)

If George says "reset stance" / "smallest version" / "do you really need
all this?" — drop what's being built, restate the actual problem in one
sentence, propose the leanest possible response. The leanest version of
this work is "swap one source for another in three call sites" — don't
expand into a generic data-abstraction layer or pluggable sources system
unless explicitly asked.
