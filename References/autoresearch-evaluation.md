# Autoresearch for FIRE — Evaluation & Implementation Plan

**Date**: 2026-03-20
**Context**: Evaluating Karpathy's Autoresearch framework for automated trading strategy discovery

## What Is Autoresearch?

Released March 7, 2026 by Andrej Karpathy. A ~630-line Python tool implementing an autonomous experiment loop for ML research.

**Core loop:**
1. AI agent reads high-level instructions from `program.md` (human-written)
2. Agent modifies `train.py` with a proposed improvement
3. Training runs for exactly 5 minutes (fixed time budget)
4. Performance measured by a single metric (`val_bpb`)
5. If metric improves → accept. If not → revert.
6. Repeat autonomously (~12 experiments/hour, ~100 overnight)

**Key results**: 700 experiments over 2 days → 20 useful optimizations → 11% speedup in GPT-2 training.

**Key insight**: Separation of concerns — humans write the "research program" (what to explore), AI executes the experiments (how to explore). `program.md` is "research organization code."

**Source**: https://github.com/karpathy/autoresearch

---

## Mapping to FIRE

| Autoresearch Component | FIRE Equivalent |
|---|---|
| `program.md` (research instructions) | `strategy_program.md` (strategy research directives) |
| `train.py` (code agent modifies) | A strategy file (e.g., `strategies/momentum.py`) |
| `val_bpb` (single eval metric) | Sharpe ratio on walk-forward OOS data |
| 5-minute fixed time budget | ~30-60 second vectorbt backtest |
| Accept/reject based on metric | Accept if OOS Sharpe > baseline AND passes robustness checks |
| Experiment log | JSONL experiment journal |

**Speed advantage**: At ~60s per backtest, we'd get ~60 experiments/hour, ~500 overnight — 5x more than LLM experiments.

---

## Why FIRE Is a Natural Fit

1. **Faster iteration**: Backtests take 30-60s vs 5 min for LLM training
2. **Clear scalar metric**: Sharpe ratio is well-defined and comparable
3. **Rich modification space**: Lookback periods, universes, filters, weights, rebalance frequency, vol-scaling params
4. **Existing validation infrastructure**: `backtesting/validation.py` has walk-forward, Monte Carlo, regime testing
5. **Clean strategy interface**: `strategies/base.py` provides well-defined boundaries for modification

---

## Critical Risks & Mitigations

### 1. Overfitting (THE primary risk)
- 500 experiments = 500 chances to find spurious patterns
- **Mitigation**: Walk-forward OOS evaluation only. Require improvement across ALL regime windows (2008, 2020, 2022, 2024-25). Monte Carlo p-value < 0.05.

### 2. Multiple Comparisons
- Massive multiple hypothesis testing problem
- **Mitigation**: Bonferroni/BH correction on Sharpe improvements. Require economically meaningful delta (>0.1 Sharpe). Deflated Sharpe Ratio (Bailey & de Prado 2014).

### 3. P-hacking by Proxy
- The AI agent is effectively doing automated p-hacking
- **Mitigation**: Constrain modification space per `program.md`. Require the agent to state its hypothesis before running. Human review of accepted changes.

### 4. Survivorship Bias
- S&P 500 universe has known bias
- **Mitigation**: Keep universe fixed; don't let agent cherry-pick tickers.

### 5. Transaction Costs
- Agent may find high-turnover strategies that die on costs
- **Mitigation**: Include realistic slippage (5bps) in backtest. Penalize turnover in accept criteria. Cap annual turnover at 200%.

---

## Example `strategy_program.md`

```markdown
# AutoStrategy Research Program

## Objective
Improve the Stock Momentum strategy (Account 1) OOS Sharpe ratio.

## Constraints
- Do NOT change the stock universe (S&P 500)
- Do NOT change the rebalance frequency (monthly)
- Maintain 1-day signal lag (no look-ahead)
- Must pass walk-forward validation (5 folds, 2005-2025)
- Must survive all 4 regime windows
- Transaction cost: 5bps per trade assumed
- Maximum portfolio turnover: 200% annual

## Search Space
- Momentum lookback: 1-12 months
- Number of holdings: 10-50
- VIX filter thresholds: 25-50
- SPY MA period: 100-300 days
- Signal weighting: equal vs momentum-ranked vs volatility-inverse
- Sector concentration limits: 20-50%

## Accept Criteria
- OOS Sharpe improvement > 0.10 over baseline (1.38)
- OOS MaxDD no worse than -15%
- Monte Carlo p-value < 0.05
- Positive return in at least 3 of 4 regime windows
```

---

## The AutoStrategy Experiment Loop

```python
# Pseudocode for autostrategy.py (~200 lines)

while True:
    # 1. Agent reads strategy_program.md
    program = read("strategy_program.md")

    # 2. Agent proposes a modification to the strategy
    hypothesis, code_diff = agent.propose_modification(program, experiment_history)

    # 3. Apply modification to strategy file
    apply_diff(strategy_file, code_diff)

    # 4. Run vectorbt backtest with walk-forward validation (~30-60s)
    results = run_walkforward_backtest(strategy_file, n_folds=5)

    # 5. Evaluate against accept criteria
    accepted = (
        results.oos_sharpe > baseline_sharpe + 0.10
        and results.oos_max_dd > -0.15
        and results.monte_carlo_pvalue < 0.05
        and results.regime_wins >= 3
        and results.annual_turnover < 2.0
    )

    # 6. Accept or reject
    if accepted:
        baseline_sharpe = results.oos_sharpe
        log_accepted(hypothesis, code_diff, results)
    else:
        revert(strategy_file, code_diff)
        log_rejected(hypothesis, code_diff, results)

    # 7. Log everything
    append_to_journal(experiment_entry)
```

---

## Implementation Phases

### Phase 1 — Single-strategy loop (1-2 days)
- Build `autostrategy.py` (~200 lines): the experiment loop
- Wire to Stock Momentum (Account 1, most room for improvement at 1.38 Sharpe)
- Use Claude API as the agent brain
- Log all experiments to JSONL

### Phase 2 — Robustness layer (1 day)
- Integrate walk-forward + Monte Carlo as gating criteria
- Add Deflated Sharpe Ratio for multiple comparison correction
- Add turnover/cost penalties
- Add regime window testing as gate

### Phase 3 — Multi-strategy exploration (ongoing)
- Run overnight on different strategies/accounts
- Let agent propose entirely new factor combinations
- Human reviews top candidates each morning
- Best candidates enter paper trading pipeline

---

## What This Won't Replace

- **Economic intuition**: The *why* a strategy works still matters. Unexplainable strategies are likely overfit.
- **Regime awareness**: Markets change structurally. Historical optimization may not generalize.
- **Risk management**: Accept/reject criteria are guardrails. Agent should never touch `execution/risk_manager.py`.
- **Paper trading validation**: Any accepted strategy still needs 3+ months paper validation before live money.

---

## Recommendation

**Try it.** Two promising starting points:

1. **Account 2 (Trend + Low-Vol, 1.36 Sharpe)** — lowest Sharpe among equity accounts, most room for parameter optimization (vol-scaling targets, trend lookbacks, low-vol/trend blend ratio).
2. **New factor discovery** — use the framework to explore entirely new uncorrelated factors that could become a 5th account. Finding one more strategy with Sharpe > 1.3 and low correlation to existing accounts would meaningfully improve the combined portfolio.

Account 1 (1.38 Sharpe, 17.6% return) and Account 3 (1.54 Sharpe) are already strong performers. Account 4 (Crypto, 1.62 Sharpe) has the best backtest but operates on a different cycle — currently in cash due to BTC being below its 200d MA trend filter, which is the strategy working as designed.

The FIRE project already has all the building blocks. The main engineering work is the experiment loop (~200 lines) and crafting good `program.md` directives. The Deflated Sharpe Ratio and walk-forward requirements should keep overfitting in check.

Priority: After the current 3-month paper trading validation completes. This is a Phase 7+ activity.
