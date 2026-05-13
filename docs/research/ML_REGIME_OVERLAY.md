# ML Regime Overlay — Scoping Doc (2026-05-13)

**Goal:** Evaluate whether a neural network (LSTM or similar) trained on multi-asset features can serve as a book-level regime detector that coordinates de-risking across accounts BEFORE individual trend filters trigger. This addresses BOOK_SHAPE Gap 3 (regime adaptivity).

**Origin:** @RohOnChain article on X (2026-05-06, ~1M views) describing an LSTM-based directional prediction framework. George flagged it as a research vector. The article's framework is technically sound on the hard parts (stationarity, walk-forward validation, early stopping) but aspirational on results (no actual backtest numbers reported). Our interest is not in the article's "complete trading system" framing — we have strategies. We need a smarter regime signal.

**Relationship to BOOK_SHAPE:** Gap 3 names three candidate approaches, ranked by risk:
1. **Price-based macro composite** (WALCL/DXY/M2/VIX term structure) — deterministic, ~1 week, MEDIUM-HIGH confidence. **This should be built first.**
2. **ML regime overlay** (this doc) — LSTM on multi-asset features, ~2-3 weeks, MEDIUM confidence. **Build only if #1 proves insufficient.**
3. **AI FOMC overlay** — LLM text analysis. **SKIP per two prior AI-alpha kills.**

The ML overlay is the natural escalation from the price-based composite. Same features as inputs, but learns non-linear regime transitions that simple thresholds can't capture.

**Prior caution:** FIRE has two AI-alpha kills (Breakthrough #1: Claude-as-stock-filter at -1.68%/month; Mode 2 PEAD on mega-cap banks). An LSTM is fundamentally different from LLM text filtering — it's applied math, not language interpretation — but the pattern of "this time the technology is different" is exactly the optimism bias the discipline layer resists. Pre-committed kill conditions are non-negotiable.

---

## What this is NOT

This is NOT a standalone trading strategy. Not an Account 5 candidate. Not trying to predict price or pick stocks. It's an **overlay signal** — a scalar between 0.0 and 1.0 that tells the entire book how much risk to take right now. It would sit alongside the existing SPY 200d and BTC 125d filters in `strategies/portfolio_config.py`, not replace them.

Think of it as vol-scaling's smarter cousin: vol-scaling adjusts exposure based on recent realized volatility. An ML overlay would adjust exposure based on learned regime patterns across multiple data streams simultaneously.

---

## Why the existing filters are limited

The current system has per-account static filters:
- **SPY 200d MA** → A1/A2 (Faber 2007). Reduces exposure by 50% when SPY < 200d.
- **BTC 125d SMA** → A4. Binary cash when BTC < 125d.

**What they can't do:**
- **Anticipate.** In 2022, SPY's 200d filter triggered months after the top. A1/A2 were already deep into drawdowns by the time the filter fired.
- **Coordinate.** Each filter operates independently. No mechanism says "all three accounts should de-risk simultaneously because the macro environment is deteriorating."
- **Capture non-linear interactions.** VIX term structure inverting + credit spreads widening + yield curve flattening might collectively signal regime change before any single variable crosses a threshold. A linear composite can catch this; a neural network can catch it AND learn the non-linear interaction effects.
- **Adapt to regime-dependent thresholds.** The "right" level to de-risk depends on context. 200d MA is a fixed rule applied identically in 2015 (low vol, trending) and 2022 (high vol, reversing). The optimal threshold is different in those regimes.

**What the filter monitor already showed us:** Daily filter reaction = Sharpe 1.27 vs monthly lag = Sharpe 0.79 (CLAUDE.md). Speed matters. If an ML overlay could trigger de-risking even 2-3 weeks before the 200d MA crosses, the book-level drawdown reduction could be significant.

---

## The @RohOnChain framework — what's technically sound

The article gets five things right that most ML-in-trading content gets wrong:

**1. Predict direction, not price.** Price series are non-stationary. Direction (binary: will risk-adjusted return be positive?) is approximately stationary. Training a network on a non-stationary target is guaranteed to fail because the conditional expectation E[Y|X] shifts across regimes. The article explains this clearly with the mathematical proof: the optimal predictor under squared error is the conditional mean, and that mean is only stable if the data generating distribution is stable.

**2. Stationarity testing on all features.** Every input must pass the Augmented Dickey-Fuller test (p < 0.05). Features that fail get first-differenced or normalized by rolling standard deviation. This is the single most important step and the one most ML practitioners skip. Our existing data pipeline already computes many of these features (returns, vol ratios, momentum) — we just don't ADF-test them.

**3. Walk-forward validation, not random split.** Train on period A, validate on period B, test on period C — all sequential. Roll forward and repeat. The concatenated OOS predictions give an honest performance estimate. This is exactly our Test 2 (rolling OOS) and Test 6 (walk-forward refit) from the validation framework — same concept, different implementation.

**4. Early stopping on validation loss.** Monitor validation loss each epoch. When it starts rising while training loss continues falling, stop and save the best weights. This is the primary defense against overfitting. Combined with walk-forward validation, it gives two independent layers of protection.

**5. Honest expected accuracy: 52-57%.** Not promising 80% win rates. The math on how a consistent 54% directional edge compounds across hundreds of trades is real. At 54% accuracy with a 1:1 win/loss ratio, Kelly says bet 8% of capital per signal. Half-Kelly (4%) across 252 trading days compounds into meaningful annual returns. The edge is in consistency and scale, not in any individual prediction.

---

## What's wrong or missing in the article

**1. No actual results.** Zero backtest performance reported. No Sharpe, no accuracy, no equity curve. "Two Sigma does this" is an authority appeal, not evidence. Medallion's 66% annual return came from tick-level execution on thousands of instruments with proprietary data, not from an LSTM on yfinance daily bars. The gap between the framework described and what actually works at scale is enormous.

**2. Daily SPY direction is a crowded signal.** Every quant fund with a data science team has tried LSTM on daily equity features. The signal-to-noise ratio at this frequency is low because the competition is fierce. Where ML directional signals have more residual edge:
- **Less-liquid markets:** crypto, prediction markets, emerging market equities
- **Proprietary features:** order flow, dark pool prints, options positioning — data most retail can't access
- **Multi-asset regime detection:** using features across asset classes to detect regime transitions (our use case)

**3. Position sizing via Kelly.** The article recommends full Kelly with a 2% hard cap. Per our research session today: Kelly requires reliable expected-return estimates that an LSTM probability output doesn't provide with sufficient precision. The right sizing for an ML signal is vol-scaling (use the signal for direction/timing, use EWMA vol for sizing) — not Kelly on raw model outputs.

**4. No discussion of regime-dependent model degradation.** The article mentions "retrain every 90 days" but doesn't address the deeper problem: the conditional expectation learned in one regime may be anti-predictive in the next. A model trained on 2019-2020 data (trending bull + COVID crash + V-recovery) learns a specific pattern of vol-compression → breakout that does NOT generalize to 2022 (sustained grinding bear with no V-recovery). Walk-forward helps but doesn't solve this — the model's architecture itself may be wrong for certain regime types.

**5. Feature set is equity-only and basic.** Returns, vol ratios, volume z-scores, SMA ratios. For a regime overlay, the interesting features are cross-asset: VIX term structure, credit spreads (HYG-IEF), yield curve slope, DXY, MOVE index, BTC correlation to SPY. The article's features would detect equity-specific patterns; regime transitions are multi-asset phenomena.

---

## How it would work in FIRE

### Architecture: overlay signal, not strategy

```
Existing: strategy weights × SPY filter × BTC filter × vol scalar = final weights
Proposed: strategy weights × SPY filter × BTC filter × vol scalar × ML regime scalar = final weights
```

The ML regime scalar would be a float in [0.3, 1.0] (never fully exit — that's the catastrophe halt's job). It would be computed daily from multi-asset features and applied uniformly across all accounts.

### Feature candidates (multi-asset, all available via yfinance/FRED)

**Market stress features:**
- VIX level (rolling z-score)
- VIX term structure: VIX9D / VIX3M ratio (backwardation = stress)
- MOVE index (rate vol, rolling percentile — same stationarity treatment as RATE_VOL_SCOPE)
- Credit spread: HYG total return minus IEF total return (widening = risk-off)
- DXY (dollar strength, rolling z-score)

**Trend/momentum features:**
- SPY 5d/20d/60d returns (multi-timeframe momentum)
- BTC 5d/20d returns
- TLT 5d/20d returns (bond momentum)
- GLD 5d/20d returns (safe-haven flow)
- Cross-asset momentum dispersion (standard deviation of returns across SPY/TLT/GLD/BTC/DXY)

**Yield curve / macro features:**
- 10Y-2Y Treasury spread (from FRED, ^TNX - ^IRX proxy)
- M2 money supply growth rate (monthly, FRED)
- High-yield spread (HYG yield - Treasury yield)

**Volume/flow features:**
- SPY volume z-score (20d rolling)
- VIX/VIX3M ratio rate of change
- Put/call ratio if available

All features would be stationarity-tested (ADF) and normalized (rolling z-score or first-difference) before input to the model.

### Target variable

NOT "will SPY go up tomorrow." Instead: **"will the FIRE book experience a drawdown exceeding X% in the next N days?"**

Possible formulations:
- Binary: did the combined book return fall below -2% over the next 10 trading days? (crisis early warning)
- Continuous: what is the expected max drawdown over the next 20 trading days? (risk forecast)
- Classification: regime label (risk-on / risk-off / crisis) based on realized vol + return + correlation clustering

The binary crisis-warning formulation is simplest and most directly actionable. It maps cleanly to a scalar: P(drawdown > 2% in 10d) → regime scalar = 1.0 - min(P, 0.7).

### Model architecture

LSTM is a reasonable starting point for sequential financial data. The article's architecture (2-layer LSTM, 64 hidden units, dropout 0.2, BCE loss) is a standard baseline. Alternatives worth testing:
- **Temporal Convolutional Network (TCN):** often matches or beats LSTM on financial time series with faster training
- **Simple GRU:** lighter than LSTM, similar performance on shorter sequences
- **Gradient boosted trees (XGBoost/LightGBM):** non-sequential but often competitive for daily-frequency regime detection because the features already encode the temporal structure (multi-window returns, vol ratios)

Start with XGBoost (fastest iteration, no GPU needed, feature importance is interpretable) and only escalate to LSTM if XGBoost's walk-forward performance is promising but limited by inability to capture sequence effects.

---

## Implementation plan (only after price-based composite is built and tested)

### Prerequisite: price-based macro composite (BOOK_SHAPE Tier 1)

Before any ML work, build the deterministic version first:
1. Download VIX term structure, credit spreads, yield curve from FRED/yfinance
2. Build a simple composite score: weighted sum of z-scored features
3. Backtest as a book-level scalar on the combined A1+A2+A4 returns (2010-2026)
4. If the composite meaningfully reduces MaxDD without destroying CAGR, it may be sufficient — no ML needed

**Kill gate for ML:** If the price-based composite reduces combined book MaxDD by >30% with <5% CAGR drag, the ML overlay adds complexity without proportional benefit. Document and skip.

### Phase 1: Feature engineering + baseline (2-3 days)

1. Build `data/regime_features.py` — download and cache all feature candidates, ADF-test each, normalize
2. Construct target variable from historical combined book returns
3. Train XGBoost classifier with walk-forward validation (2010-2022 train, rolling 1-year windows)
4. Report: accuracy, AUC-ROC, feature importance, number of "de-risk" signals per year

**Kill gate (Phase 1):** If walk-forward AUC-ROC < 0.55 (barely better than random), stop. The features don't contain a learnable regime signal at daily frequency.

### Phase 2: Model selection + signal integration (2-3 days, only if Phase 1 passes)

1. Compare XGBoost to LSTM and TCN on same features/target
2. Build `strategies/regime_overlay.py` — converts model output to a scalar in [0.3, 1.0]
3. Backtest the scalar as a book-level multiplier on combined returns (2010-2026)
4. Compare: book with ML overlay vs book with SPY 200d only vs book with price-based composite

**Kill gate (Phase 2):** If the ML overlay doesn't meaningfully beat the price-based composite (>10% MaxDD improvement), the added complexity and model risk aren't justified.

### Phase 3: Robust validation (2-3 days, only if Phase 2 passes)

1. Walk-forward refit: retrain every 6 months, evaluate on next 6 months
2. Parameter stability: does the model's accuracy persist across 2010-2015, 2015-2020, 2020-2025?
3. Regime analysis: does it actually fire BEFORE the 200d MA crosses? If it only confirms the MA signal, it adds nothing
4. Run through the existing 6-test validation framework (adapted for overlay, not standalone strategy)
5. Measure live-simulation: what would the combined book look like with the overlay applied?

**Pass criteria:** Walk-forward accuracy > 56%, MaxDD improvement > 20% vs current filters, fires at least 5 trading days before SPY 200d MA cross in >50% of historical regime changes.

---

## The honest case against doing this

**1. Complexity budget.** FIRE is a solo-operator system. Every ML model is a new surface to monitor, retrain, debug, and explain. A simple 200d MA is transparent, battle-tested, and requires zero maintenance. An LSTM needs periodic retraining, feature drift monitoring, and model versioning. The maintenance burden is ongoing, not one-time.

**2. Two prior AI-alpha kills.** Yes, LSTM ≠ LLM. But the meta-pattern — "sophisticated technology applied to financial data underperforms simple rules in our system" — has a 0-for-2 track record. The burden of proof is on the ML approach.

**3. Overfitting risk is extreme in regime detection.** There are maybe 5-8 genuine regime transitions in 16 years of data (2008, 2011, 2015, 2018, 2020, 2022, plus a few minor ones). Training a neural network on 5-8 positive examples is a recipe for memorization, not generalization. XGBoost with strong regularization is more appropriate for this sample size.

**4. The 200d MA is hard to beat.** Faber (2007) showed that a simple MA rule captures most of the drawdown reduction available from tactical asset allocation. Adding complexity on top of a rule that already works "pretty well" has diminishing returns. The ML overlay needs to be meaningfully better, not just marginally better.

**5. The real bottleneck might not be the signal.** A4's 12pp execution drag isn't a signal problem — it's an execution problem. If the binding constraint is execution quality rather than signal quality, building a better regime detector doesn't address the actual bottleneck.

---

## The honest case FOR doing this (after the prerequisite)

**1. The 200d MA is provably late.** In every historical regime change, the 200d MA confirms the transition weeks to months after it begins. Even a modest 2-3 week early warning across all accounts simultaneously would meaningfully reduce the first-draw-down-before-filter-triggers problem that BOOK_SHAPE identifies.

**2. Multi-asset features contain regime information that single-asset filters miss.** VIX term structure inverting + credit spreads widening + dollar strengthening is a recognizable pre-crisis pattern. No single variable crosses a threshold, but the combination is informative. This is exactly the pattern recognition neural networks excel at.

**3. The overlay framing limits downside.** This isn't predicting stock prices or picking stocks (where ML reliably fails at retail scale). It's answering one binary question: "is the macro environment deteriorating?" That question has a clearer signal-to-noise ratio than "which stock goes up."

**4. The infrastructure investment is reusable.** Features like VIX term structure, credit spreads, and yield curve slope are useful for the price-based composite too. Building the feature pipeline serves both approaches. If the ML overlay fails, the features remain valuable for the deterministic composite.

**5. Crypto application is less competed.** The article's author works in crypto/prediction markets. Crypto regime detection (BTC dominance shifts, exchange flow anomalies, funding rate patterns) has fewer institutional competitors than equity. An ML regime filter specifically for A4 could be higher-EV than a book-level equity overlay.

---

## Open questions

1. **Is 16 years of daily data enough to train a regime detector?** Only 5-8 genuine regime transitions exist in the sample. Even with walk-forward validation, the positive-class sample size may be too small for reliable learning. Data augmentation (synthetic regime transitions) is theoretically possible but introduces model risk.

2. **Should the overlay be trained on the book's own returns or on market features only?** Training on the book's returns introduces circularity (the overlay learns to predict the strategy's performance, not the market regime). Training on market features only is cleaner but may miss strategy-specific vulnerabilities.

3. **What's the right retraining cadence?** The article suggests 90 days for crypto. For a daily equity regime signal, 6-month retraining with walk-forward validation seems more appropriate (slower regime transitions, more data needed per window). But A4 crypto might benefit from faster retraining.

4. **XGBoost vs LSTM vs ensemble?** XGBoost is better for small-sample regime detection (regularization controls overfitting more directly). LSTM is better if sequential patterns genuinely matter (multi-week buildup of stress indicators). An ensemble (XGBoost provides base, LSTM provides sequential refinement) might outperform both but doubles complexity.

5. **How does this interact with vol-scaling?** Vol-scaling already de-risks when realized vol is high. An ML overlay that fires on the same vol signal is redundant. The overlay needs to add information BEYOND what vol-scaling already captures — specifically, anticipatory signals (VIX term structure, credit spreads) that precede the vol spike.

---

## References

- @RohOnChain, "How to Use Neural Networks to Win Every Trade Before It Even Starts" (X article, 2026-05-06, ~1M views)
- Moreira & Muir (2017), "Volatility-Managed Portfolios" — the vol-scaling framework this would complement
- Faber (2007), "A Quantitative Approach to Tactical Asset Allocation" — the 200d MA benchmark to beat
- Barroso & Santa-Clara (2015), "Momentum Has Its Moments" — vol-scaling for momentum
- Gu, Kelly, Xiu (2020), "Empirical Asset Pricing via Machine Learning" — comprehensive comparison of ML methods for financial prediction; tree-based methods competitive with deep learning
- BOOK_SHAPE.md Gap 3 — the strategic rationale for regime adaptivity
- RATE_VOL_SCOPE.md — related: MOVE-conditional signal, percentile-based thresholds, stationarity treatment

---

## Sequence summary

1. **First:** Build price-based macro composite (WALCL/DXY/M2/VIX term structure) — ~1 week, deterministic, no ML
2. **If that's insufficient:** Phase 1 ML feature engineering + XGBoost baseline — 2-3 days, with kill gate at AUC-ROC < 0.55
3. **If that passes:** Phase 2 model comparison + signal integration — 2-3 days, with kill gate at <10% MaxDD improvement over composite
4. **If that passes:** Phase 3 robust validation — 2-3 days, same 6-test framework adapted for overlay
5. **If all pass:** Paper-trade as book-level scalar for 3-6 months before applying to live accounts

Total: ~2-3 weeks of work spread across 4 phases with 3 kill gates. Zero work wasted — each phase produces reusable infrastructure (features, validation, monitoring) regardless of whether the ML model clears its gates.
