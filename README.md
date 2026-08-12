# FIRE - Quantitative Trading System

A personal quantitative trading research system. Momentum and trend factor strategies, paper-traded on Alpaca, built solo with Claude Code as the engineering partner. Spec'd as a partnership proposal in January 2020 (the original doc is in `References/`), built for real starting March 2026.

> **Disclaimer, read this first.** This is personal research running on paper accounts. Nothing here is investment advice. No performance claims are made or implied. Backtest results in this repo (and there are many) predict nothing - most of the strategies documented here were killed by their own validation numbers, which is rather the point.

## What this is

A two-account factor book, live on Alpaca paper since March 2026:

- **Account 1 - Momentum.** 15 stocks, sector momentum with an SPY 200-day filter and a volatility-scaling overlay. Rebalances every 21 trading days.
- **Account 2 - Trend + Low-Vol.** 30% multi-asset trend, 70% low-volatility equity. The defensive ballast.

Plus the machinery around it: a FastAPI backend, a React dashboard, cron-driven filter monitors, a two-tier drawdown monitor, a validation gate that blocks rebalances on unvalidated strategies, and a JSONL audit trail of every order.

## What makes it worth looking at

Not the strategies - momentum and trend-following are commodity. What's unusual here is that the failure record is published next to the wins:

- [HISTORY.md](HISTORY.md) - every resolved bug and decision delta, including the ones that cost money. Account 4 (crypto momentum) retired at -23.1% live after walk-forward validation showed the edge decaying. Account 3 retired for 0.88 correlation to Account 1. Both post-mortems are in there.
- [docs/research/EVENT_KILLTESTS_JUL2026.md](docs/research/EVENT_KILLTESTS_JUL2026.md) - four event-driven strategy ideas (buybacks, index deletions, spinoffs, insider clusters) kill-tested on fresh 2022-26 data. All four died. The test harnesses are in `scripts/` and reusable.
- [VALIDATION.md](VALIDATION.md) - the six-test statistical scorecard every strategy must pass before touching money, with quarterly re-validation enforced in code.
- [DATA_SOURCES.md](DATA_SOURCES.md) - an incident log of every data-corruption event, most of them traced to the same root cause.
- [STRATEGIES.md](STRATEGIES.md) - out-of-sample scorecards for everything, including the strategies that failed their gates.
- [CAPABILITIES.md](CAPABILITIES.md) - what the system can and cannot do, written for an outside reader.

## Honest performance

Out-of-sample backtest (validated, net of costs): Account 1 CAGR 33.0% (PASS), Account 2 CAGR 12.9% (MARGINAL - the honest number, with margin financing drag included).

Live is a different story: the paper book has so far lagged SPY. Part of that was bugs (documented in HISTORY.md), part was an un-levered design that was fixed in July 2026, and part may simply be that the edge is smaller live than in backtest. The next few rebalance cycles are the test. If you came here for a system that beats the market, this is not that - it's a system that measures itself honestly while trying to get there.

## What this is NOT

- Not a product. Not maintained for anyone else's use.
- No support, no roadmap for external users. Issues and PRs are welcome, but a response is not guaranteed.
- Not a signal service, not advice, not a track record.

## Quickstart for the curious

Requires Python 3.12 via [uv](https://docs.astral.sh/uv/), Node via nvm, and Alpaca paper API keys in `.env` (see `AlpacaBroker` in `execution/alpaca_broker.py` for the expected variable names).

```bash
./scripts/start.sh   # backend on :8001, dashboard on :5174
```

Read [CLAUDE.md](CLAUDE.md) for the full operational manual - architecture, schedules, risk controls, run commands. It's written for the AI partner that co-builds this, which makes it a fairly complete map for a human too.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md). Use it and learn from it - just not commercially.
