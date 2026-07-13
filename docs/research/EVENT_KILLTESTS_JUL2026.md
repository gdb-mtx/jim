# Event-Sleeve Kill Tests — 2026-07-13

**What this is.** AUDIT_FABLE §5.1 recommended "A5-Events": one pooled
event-driven sleeve (buybacks + insider clusters + index deletions +
spinoffs) as the #1 breakthrough build. Before building the sleeve, each
stream got a same-day kill test on **2022–2026 data** — the period the
academic literature does not cover. This memo is the canonical record of
those verdicts and of two companion quantifications (VIX sleeve,
leveraged trend) run the same session.

**Method.** Shared harness pattern (`scripts/*_poc.py`): harvest events
from a primary source (EDGAR full-text search, SEC Form 4 structured
datasets, Wikipedia constituent-change table), event-study with fixed
entry/hold, abnormal return vs SPY **and** MDY, by-year and by-cap-bucket
breakdowns, kill criteria **locked in each script's docstring before the
first run**. Known biases run one direction: yfinance survivorship
removes delisted losers and overlapping windows inflate t — both favor
GO, so KILL verdicts are conservative.

## Verdicts

| Stream | Test | N | Mean | Median | Hit | t | Verdict |
|---|---|---|---|---|---|---|---|
| Buyback drift (mid-cap) | T+5 entry, 63d, vs SPY | 493 | **-2.10%** | -3.74% | 41% | -2.40 | **KILL** |
| Deletion reversion (S&P 500) | effective-date entry, 63d, vs MDY | 84 | +3.80% | -1.53% | 44% | 1.32 | **MARGINAL → not fundable** |
| Spinoff drift | first-bar+21 entry, 63d, vs MDY | 45 | +3.72% | -2.08% | 47% | 1.08 | **MARGINAL → not fundable** |
| Insider clusters ($200M–$5B) | T+1 entry, 126d, vs MDY | 791 | +1.04% | -4.55% | 42% | 0.59 | **KILL** |

Detail worth keeping:

- **Buybacks are inverted, not decayed.** Negative every year 2022–2026,
  and worsening with horizon (+0.08% @21d → -2.10% @63d). Post-2022 a
  repurchase announcement marks negative selection (companies defending
  sagging prices, 1% excise-tax era). The April-2026 GO verdict was built
  on pre-2019 literature; it does not survive contact with current data.
- **Deletions and spinoffs share one signature:** the *mechanical* flow
  is real (spinoff month-1 dump: day-one entry -3.9%; deletion forced
  selling visible), but the post-event drift is right-skew lottery —
  positive mean carried by a few huge bounces, **negative median, sub-50%
  hit rate, year-unstable** (deletions 2023: -16.4%, t=-4.1). At 12–20
  events/yr each, variance dominates; no systematic sleeve can be run on
  them.
- **Insider clusters — the strongest-documented stream — carries no
  drift either.** N=791 in the $200M–$5B band, 1,627 events total
  (300–440/yr, median $690K insider money per cluster — real conviction,
  measured, worthless). Negative vs SPY (-1.02%). The decisive internal:
  **dose-response is inverted** — 5-insider clusters (-3.00%) underperform
  3-insider clusters (+1.90%); a live signal would strengthen with
  conviction. Lakonishok-Lee (2001) does not survive 2022–2026. The one
  hot cell (micro<$200M: mean +7.6%, median **-8.7%**, hit 44%) is
  extreme lottery skew behind the worst survivorship and spreads — not
  tradeable at our breadth.
- **Meta-finding: the 2022+ public-event landscape is picked clean at
  the mean.** All four streams show the same signature — mechanical flow
  real, mean arbed, right-skew residue with negative medians. Pooling
  negative-median streams yields a negative-median pool, so **A5-Events
  is refuted as a concept on free public data**, not merely per-stream.
  Any revisit requires point-in-time data with delisted names (Norgate)
  and 100+ position breadth to harvest skew — a different machine.

## Companion quantifications (same session)

**VIX regime-switched sleeve (AUDIT_FABLE §5.2): dead as designed;
survives as a priced tail hedge.** On real SVXY/VIXY history 2011–2026,
every switched variant is uninvestable (best: +7.3% CAGR, -73% MaxDD).
But the 9D/3M signal itself is genuinely prescient: long-vol in
backwardation averaged **+14%/day on SPY's 20 worst days (positive 13–14
of 20; +34% on Volmageddon day)**. The honest product is insurance, not
a return stream: **VIXY only when VIX9D/VIX3M ≥ 1.10** (~5% of days),
costing ≈ -3.4% CAGR standalone (calm-year bleed -8% to -30% on trigger
years, 2020 payoff +112%). On a 5% book slice: ~0.2–1.5pp/yr premium for
+5–6pp book payoff in a crash year. Decision, not research. SVXY carry
leg: skip (post-2018 0.5x deleveraging left ~9% CAGR with -53% MaxDD and
a 2024 -26% bleed).

**Leveraged trend (AUDIT_FABLE §6): priced.** SPY-200d filter on SSO:
13.9% CAGR, -40.5% MaxDD, Calmar 0.34 (2006–2026). UPRO: 25.1%, -51.2%,
Calmar 0.49 — sample starts *after* the GFC. The 40%-CAGR path costs a
-50% drawdown; it would replace the book's Calmar-2.5+ identity with
Calmar ~0.4. Recommendation: pass.

**Crypto basis carry (AUDIT_FABLE §5.3): regime is OFF.** Deribit 30d
mean funding as of 2026-07-13: BTC **+2.2% annualized**, ETH ~0%. Carry
pays fees, nothing more, in a down-trend regime. Do not build execution
infrastructure now. **Trigger to revisit:** 30d mean annualized funding
> ~8–10%. One-command probe (no key):

```
uv run python3 - <<'EOF'
import requests, statistics
from datetime import datetime, timezone
now = int(datetime.now(timezone.utc).timestamp()*1000); d30 = now - 30*86400*1000
for ins in ["BTC-PERPETUAL","ETH-PERPETUAL"]:
    h = requests.get("https://www.deribit.com/api/v2/public/get_funding_rate_history",
        params={"instrument_name": ins, "start_timestamp": d30, "end_timestamp": now},
        timeout=15).json()["result"]
    print(ins, f"{statistics.mean(x['interest_8h'] for x in h)*3*365:+.1%} annualized (30d)")
EOF
```

Check monthly (or when BTC re-crosses its 125d SMA — funding turns
positive in up-trends).

## What this does to the build-out ranking

Dead or deprioritized: buybacks (dead), deletions/spinoffs (not
fundable), switched VIX sleeve (dead as designed), leveraged trend
(priced, pass), basis carry (regime-gated, monitor only).

Dead as of this memo: **all four A5-Events streams** (buybacks,
deletions, spinoffs, insider clusters).

Still standing, in order:

1. **cap=1.5 vol-scaling sprint** — unchanged, mechanical, ~+2pp book
   CAGR, 3–5 days (HUNT_APR2026 scoping). Now the single
   highest-confidence build in the backlog.
2. **VIXY tail leg** — George's buy/don't-buy decision at 5% of book.
3. **Macro composite** (AUDIT_FABLE §5.4) — unchanged, ~1 week; the
   VIX-ratio work here feeds it directly.
4. **Norgate data (~$30/mo)** — now a *precondition* for any further
   equity research: all four kill tests hit the yfinance survivorship
   wall, and closing C3 comes free with it.
5. **Basis carry** — parked behind the funding trigger above; the only
   non-price stream left with a live mechanism.

The strategic read: for a solo operator in 2026, free-public-data
anomaly harvesting is over. What remains is (a) regime-gated risk
premia (carry, vol), (b) honest leverage engineering (cap=1.5),
(c) data-walled pockets (point-in-time small-cap work behind Norgate),
and (d) the discipline layer already built — which is what killed four
dead strategies in one day for $0 instead of funding them.
