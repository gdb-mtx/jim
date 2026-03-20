# Autoresearch for FIRE — Factor Discovery Framework

**Date**: 2026-03-20
**Context**: Adapting [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) for autonomous discovery of a 5th uncorrelated trading factor
**Goal**: Find a genuinely new factor for Account 5, exploiting 2 remaining Alpaca paper trading slots

---

## What Is Autoresearch?

Released March 7, 2026 by Andrej Karpathy. An autonomous experiment loop where an AI agent modifies code, runs time-boxed experiments, keeps improvements, reverts failures, and loops forever. The human "programs the research org" via `program.md`.

**Core architecture (3 files):**
| File | Who edits | Purpose |
|------|-----------|---------|
| `prepare.py` | Nobody | Fixed: data prep, tokenizer, evaluation harness |
| `train.py` | Agent | The one file it hacks on (model, optimizer, hyperparams) |
| `program.md` | Human | Research instructions, constraints, acceptance criteria |

**Key results**: 700 experiments in 2 days → 20 optimizations → 11% speedup. Shopify CEO ran it overnight → 37 experiments → 19% gain.

**Key design**: One file to modify. One metric to optimize (`val_bpb`). Fixed time budget (5 min). Accept/reject via git commit/reset. `results.tsv` tracks everything. Agent runs autonomously until interrupted.

**Source**: https://github.com/karpathy/autoresearch

---

## Why a 5th Factor?

Our current 4 accounts all exploit variations of momentum and trend:

| Account | Factor | Captures |
|---------|--------|----------|
| 1 | Stock Momentum + SPY Filter | Winners keep winning |
| 2 | Trend + Low-Vol (vol-scaled) | Crisis alpha + defensive |
| 3 | Reversal + Momentum Blend | Overreaction bounce |
| 4 | Crypto Momentum + BTC Filter | Alt-asset herding |

Cross-account equity correlations: 0.56-0.66. Crypto-equity: 0.12-0.18.

**The math of diversification**: A 5th factor with low correlation (<0.30) to existing accounts would push the combined Sharpe higher even if its standalone Sharpe is mediocre (0.90). Optimizing Account 2 from 1.36 to 1.46 Sharpe is nice but adding a genuinely uncorrelated stream is worth far more to the portfolio.

**Infrastructure headroom**: 2 remaining paper trading slots on second Alpaca account (3 slots per account × 2 accounts = 6 total, 4 used).

---

## Mapping to FIRE

| Autoresearch | FIRE Factor Discovery |
|---|---|
| `prepare.py` (fixed data/eval) | `research/evaluate.py` (data loading, backtest, composite scoring, correlation to Accounts 1-4) |
| `train.py` (agent modifies) | `research/strategy.py` (signal generation, universe, filters, weighting) |
| `program.md` (human programs) | `research/program.md` (factor exploration guidance, hard gates, acceptance criteria) |
| `val_bpb` (single metric) | Composite score: `sharpe × (1 - max_corr_to_existing)` |
| 5-min time budget | ~30-60s backtest (vectorized pandas on S&P 500) |
| `results.tsv` | Same — tab-separated experiment log |
| Git commit/reset | Same — advance branch on improvement, reset on failure |

**Speed advantage**: ~60-120 experiments/hour (vs Karpathy's ~12). Overnight = 500-1000 experiments.

---

## Composite Scoring Metric

Karpathy uses `val_bpb` (lower = better, single number). We need a composite that rewards both standalone quality AND diversification value:

```
score = sharpe × (1 - max_correlation_to_existing_accounts)
```

**Why this works**: A strategy with 1.20 Sharpe but 0.60 correlation scores `1.20 × 0.40 = 0.48`. A strategy with 0.95 Sharpe but 0.20 correlation scores `0.95 × 0.80 = 0.76`. The lower-Sharpe strategy wins because it adds more to the combined portfolio.

**Hard gates (auto-reject regardless of score):**
- Sharpe < 0.80 → reject
- Max correlation to any Account 1-4 > 0.40 → reject
- Max drawdown worse than -30% → reject
- Walk-forward median OOS Sharpe < 0.50 → reject

---

## Candidate Factors — Ranked by Diversification Potential

| Factor | Expected Corr to Momentum | Academic Support | Data Source | Priority |
|--------|--------------------------|-----------------|-------------|----------|
| **Value (HML)** | **-0.17 to -0.57** (negative!) | Fama-French 1993, 30+ years | yfinance P/B, earnings | **#1 — Best diversifier** |
| **Quality (ROE + D/E)** | Low to negative (post-2020) | Asness et al. 2013, Novy-Marx 2013 | yfinance financials | **#2 — Defensive** |
| **BAB (low beta)** | Low positive (~0.15) | Frazzini & Pedersen 2014 | yfinance beta | **#3 — Independent alpha** |
| **Dividend carry** | ~0.00 (uncorrelated) | Koijen, Moskowitz, Pedersen 2013 | yfinance dividends | **#4 — Easy data** |
| **Size (SMB)** | Low (~0.10-0.20) | Fama-French 1993 (weakening) | yfinance market cap | Lower — effect fading |
| **Seasonality** | Independent | Well-documented but shrinking | Calendar logic | Lower — small effect |
| **Sentiment (VIX)** | Already used as filter | Mixed | FRED, CBOE | Avoid — overlaps existing |

### Why Value First

The **negative correlation to momentum** is the killer feature. Accounts 1, 3, and 4 all exploit momentum in some form. Value buys beaten-down stocks that momentum sells — it's the classic anti-momentum factor. Asness, Moskowitz & Pedersen (2013) document this negative correlation across asset classes and decades.

### Key Academic References

- **Fama & French (1993)** — "Common risk factors in the returns on stocks and bonds" (value + size factors)
- **Asness, Moskowitz & Pedersen (2013)** — "Value and Momentum Everywhere" (negative value-momentum correlation, the key insight)
- **Novy-Marx (2013)** — "The other side of value: The gross profitability premium" (quality/profitability factor)
- **Frazzini & Pedersen (2014)** — "Betting against beta" (BAB factor, long low-beta, short high-beta)
- **Koijen, Moskowitz & Pedersen (2013)** — "Carry" (dividend/yield factors across asset classes)
- **Kenneth French Data Library** — Monthly factor returns for backtesting comparison: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

---

## Critical Risks & Mitigations

### 1. Overfitting (THE primary risk)
- 500+ experiments = 500+ chances to find spurious patterns
- **Mitigation**: Walk-forward OOS evaluation only. Require improvement across ALL regime windows (2008, 2020, 2022, 2024-25). Monte Carlo p-value < 0.05.

### 2. Multiple Comparisons
- Massive multiple hypothesis testing problem
- **Mitigation**: Bonferroni/BH correction on Sharpe improvements. Require economically meaningful delta (>0.1 Sharpe). Deflated Sharpe Ratio (Bailey & de Prado 2014).

### 3. P-hacking by Proxy
- The AI agent is effectively doing automated p-hacking
- **Mitigation**: Constrain modification space per `program.md`. Require the agent to state its hypothesis before running. Human review of accepted changes.

### 4. Survivorship Bias
- S&P 500 universe uses current constituents
- **Mitigation**: Keep universe fixed; don't let agent cherry-pick tickers. Note bias in results.

### 5. Transaction Costs
- Agent may find high-turnover strategies that die on costs
- **Mitigation**: Include realistic slippage (5bps) in backtest. Penalize turnover in accept criteria. Cap annual turnover at 200%.

### 6. Fundamental Data Quality
- yfinance fundamental data (P/B, ROE, D/E) is spottier than price data
- **Mitigation**: Cache aggressively, fill forward missing values, require minimum coverage (80% of universe). Cross-validate key metrics against French Data Library factor returns.

---

## What `research/program.md` Contains

Based on the actual structure of Karpathy's `program.md` (setup → constraints → loop → never stop):

```markdown
# Factor Discovery Research Program

## Setup

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar20`).
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**:
   - `research/evaluate.py` — fixed evaluation harness. Do not modify.
   - `research/strategy.py` — the file you modify. Signal generation, universe, filters.
   - The existing strategies in `strategies/` — what you're diversifying AGAINST.
4. **Verify data exists**: Check that `data/cache/` contains price and fundamental parquets.
   If not, tell the human to run `uv run data/fundamentals.py`.
5. **Initialize results.tsv**: Create with header row. Baseline recorded after first run.
6. **Confirm and go**.

## Goal

Get the highest COMPOSITE SCORE:

    score = sharpe × (1 - max_correlation_to_existing_accounts)

Hard gates (auto-reject):
- Sharpe < 0.80
- Max correlation to any Account 1-4 > 0.40
- Max drawdown worse than -30%
- Walk-forward median OOS Sharpe < 0.50

## What you CAN modify

- `research/strategy.py` — everything: signal logic, factor definitions, lookback periods,
  top-N selection, rebalance frequency, weighting scheme, regime filters, vol-scaling params.

## What you CANNOT modify

- `research/evaluate.py` — the scoring function is ground truth.
- Any file in `strategies/` or `data/` — those are the existing system.
- Cannot install new packages.

## Exploration guidance

Start with the highest-prior factors (negative momentum correlation in literature):

1. **Value** (earnings yield, P/B, P/E, EBITDA/EV) — start here.
   Expected -0.30 to -0.50 correlation to momentum. Best diversifier.
2. **Quality** (ROE > 15%, D/E < 1.0, earnings stability) — defensive.
3. **Betting Against Beta** (long low-beta stocks) — independent alpha source.
4. **Dividend carry** (trailing 12-month yield ranking) — nearly zero momentum corr.
5. **Combinations** — value+quality blend, value+BAB, multi-factor composites.

For each factor family: try the simplest version first, measure, then iterate
(different lookbacks, universes, filters, weightings). If a factor family shows
max_corr > 0.40 after 5+ attempts, MOVE ON to the next family.

## Simplicity criterion

All else being equal, simpler is better. A small improvement that adds ugly
complexity is not worth it. Removing something and getting equal or better
results is a great outcome. A 0.005 score improvement from deleting code? Keep.

## The experiment loop

LOOP FOREVER:

1. Look at results.tsv — what's worked, what hasn't
2. Choose next experiment (new factor, parameter tweak, or combination)
3. Edit research/strategy.py
4. git commit -m "experiment: <description>"
5. Run: uv run research/evaluate.py > run.log 2>&1
6. Read: grep "^score:\|^sharpe:\|^max_corr:\|^max_dd:" run.log
7. If grep empty → crashed. Run tail -n 50 run.log, attempt fix.
8. Log to results.tsv (commit, score, sharpe, max_corr, max_dd, status, description)
9. If score improved → keep commit (advance branch)
10. If score equal or worse → git reset back

NEVER STOP. The human might be asleep. Run until manually interrupted.
If you run out of ideas, re-read the factor literature, try combining
previous near-misses, try more radical factor definitions.

## Data available in evaluate.py

- S&P 500 prices (451 stocks, 2005-present, cached parquet)
- Fundamental data: P/B, P/E, ROE, D/E, beta, dividend yield, earnings yield, market cap
- VIX data (for regime filters)
- SPY prices (for trend filter)
- Pre-computed daily returns for Accounts 1-4 (for correlation measurement)
```

---

## What `research/evaluate.py` Contains (Fixed Harness)

```python
# The "prepare.py" equivalent — agent cannot touch this

def evaluate_strategy():
    # 1. Load cached data (S&P 500 prices + fundamentals)
    prices = load_sp500_prices()
    fundamentals = load_fundamentals()  # P/B, ROE, D/E, beta, yield
    vix = load_vix()

    # 2. Import strategy.py's generate_signals()
    from research.strategy import generate_signals
    signals = generate_signals(prices, fundamentals, vix)

    # 3. Run backtest (vectorized: signals.shift(1) * returns)
    returns = compute_returns(prices, signals)

    # 4. Compute metrics
    sharpe = compute_sharpe(returns)
    max_dd = compute_max_drawdown(returns)
    wf_result = walk_forward(prices, fundamentals, vix, generate_signals)

    # 5. Load pre-computed Account 1-4 returns (baselines/)
    acct_returns = load_baseline_returns()

    # 6. Compute pairwise correlations to all 4 accounts
    correlations = {f"corr_acct{i}": returns.corr(r) for i, r in acct_returns.items()}
    max_corr = max(correlations.values())

    # 7. Composite score
    score = sharpe * (1 - max_corr)

    # 8. Apply hard gates
    if sharpe < 0.80 or max_corr > 0.40 or max_dd < -0.30 or not wf_result["pass"]:
        score = 0.0  # Auto-reject

    # 9. Print grep-able results
    print(f"score:      {score:.6f}")
    print(f"sharpe:     {sharpe:.6f}")
    print(f"max_corr:   {max_corr:.6f}")
    print(f"max_dd:     {max_dd:.6f}")
    print(f"wf_pass:    {wf_result['pass']}")
    for k, v in correlations.items():
        print(f"{k}:  {v:.4f}")
```

---

## What `research/strategy.py` Starts As (Seed)

Ships with a naive value baseline the agent immediately improves:

```python
def generate_signals(prices, fundamentals, vix):
    """Naive value: rank by trailing earnings yield, equal-weight top 50."""
    ey = fundamentals["earnings_yield"]
    ranks = ey.rank(axis=1, ascending=False)
    selected = ranks <= 50
    weights = selected.astype(float).div(selected.sum(axis=1), axis=0)
    return weights
```

---

## Expected Overnight Discovery Arc

| Experiments | Phase | What the agent tries |
|---|---|---|
| 1-15 | Pure value variants | P/B, P/E, earnings yield, EBITDA/EV, different top-N |
| 16-30 | Add quality filters | ROE > 15%, D/E < 1.0, composite scores |
| 31-40 | Alternative factors | Pure quality, pure BAB (low-beta), dividend yield |
| 41-60 | Optimize winner | Lookback periods, top-N, rebalance frequency |
| 61-80 | Combinations | Value+quality blend, value+BAB, multi-factor |
| 80-100+ | Fine-tuning | Regime filters, vol-scaling, sector neutralization |

### Example `results.tsv` After Overnight

```
commit	score	sharpe	max_corr	max_dd	status	description
a1b2c3d	0.000	0.72	0.22	-0.19	reject	baseline naive value (earnings yield top 50)
b2c3d4e	0.000	0.91	0.45	-0.16	reject	value P/B top 50 (corr too high to acct2)
c3d4e5f	0.548	0.88	0.38	-0.21	keep	value earnings yield + momentum quality filter
d4e5f6g	0.592	0.95	0.37	-0.18	keep	value EY + quality (ROE>15%) composite
e5f6g7h	0.000	0.93	0.44	-0.15	reject	quality only (ROE+DE, corr 0.44 to acct2)
f6g7h8i	0.612	1.02	0.40	-0.17	reject	value-quality 60/40 (corr at boundary)
g7h8i9j	0.654	1.05	0.36	-0.19	keep	value-quality + sector neutralize
h8i9j0k	0.682	1.10	0.38	-0.22	keep	value-quality, 30 stocks, quarterly rebal
```

---

## What Needs Building (4 Files + Baselines)

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `data/fundamentals.py` | ~150 | Fundamental data pipeline: yfinance batch download of P/B, ROE, D/E, beta, dividend yield, earnings yield for S&P 500. Parquet cache with quarterly refresh. |
| `research/evaluate.py` | ~200 | Fixed evaluation harness: load data, import strategy, backtest, compute composite score + correlations, print grep-able output. |
| `research/strategy.py` | ~30 | Seed strategy (naive value). Agent modifies this file only. |
| `research/program.md` | ~80 | Agent instructions per the template above. |
| `research/baselines/` | generated | Pre-computed daily returns for Accounts 1-4 (parquet). Generated once from existing strategies. |

---

## Deployment Path

1. **Autoresearch overnight** → Best `strategy.py` with highest composite score
2. **Human review** → Read `results.tsv`, inspect winning code, check economic intuition
3. **Full validation** → Run through existing 3-tier validation (`backtesting/validation.py`)
4. **Integration** → Promote to `strategies/value.py` (or whatever factor won), add to `portfolio.py` registry
5. **Paper trade** → Deploy to remaining Alpaca paper slot, configure as Account 5
6. **Monitor** → 3+ months alongside existing 4 accounts, measure live correlation

---

## What This Won't Replace

- **Economic intuition**: The *why* a strategy works still matters. Unexplainable strategies are likely overfit.
- **Regime awareness**: Markets change structurally. Historical optimization may not generalize.
- **Risk management**: Agent never touches `execution/risk_manager.py`.
- **Paper trading validation**: Any accepted strategy still needs 3+ months before live money.

---

## Future Extensions of the Autoresearch Pattern

- **Multi-agent parallel**: Run 2-3 agents on different factor families (value, quality, BAB) with separate branches
- **Cross-domain**: Apply same loop to crypto factor discovery (DeFi yield, on-chain metrics)
- **Meta-optimization**: Tune existing Account 2 blend (Trend + Low-Vol weights, vol-scaling params)
- **HMM regime filter**: Use autoresearch to optimize a probabilistic regime detector as portfolio overlay
