# FIRE — Quantitative Trading System

Multi-strategy systematic trading book operating across Alpaca paper accounts. Factor-diversified equity (momentum, trend + low-vol) plus crypto momentum rotation. Paper-first, validation-gated, audit-trailed.

## Status (2026-05-26)

Mechanics are solid. Strategies are middle-of-the-road — paper performance roughly matches backtest in most months (with notable A4 live execution drag), but the book is not delivering what we hoped for. Two months elapsed, ~one month of clean data post-bug-fixes. **No active strategy hunt.** A1+A2+A4 keep running. Vectors in `docs/research/` (yield, ML regime, VIX term-structure) remain unimplemented and unowned. Not shutting down; not expanding. Revisit if/when a specific hypothesis hits.

## Where to start

- **[CAPABILITIES.md](CAPABILITIES.md)** — system overview, current scorecard, honest limits, peer comparison.
- **[CLAUDE.md](CLAUDE.md)** — operational manual: architecture, schedules, risk controls, run commands.
- **[BOOK_SHAPE.md](BOOK_SHAPE.md)** — forward direction (what the book is, what it's missing, what's next).

## Running it

```
./scripts/start.sh   # backend on :8001, dashboard on :5174
```

Full setup and ops detail in [CLAUDE.md](CLAUDE.md) → "Running the Project".
