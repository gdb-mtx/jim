# Elite Quant Shops — Tribal Knowledge, Public Findings, and What Survives a $50K Alpaca-Spot Constraint

**Date:** 2026-04-23
**Context:** Account 5 hunt following kills of crypto reversal and rate-vol TLT reversal (see HUNT_APR2026.md). Four parallel scouts were commissioned to mine public knowledge of elite quant firms for vectors a solo builder with an AI partner could realistically capture in a 3-6 month window, before those firms fully integrate LLMs themselves.

---

## Summary: what survives our constraints

| Firm Archetype | Their actual edge | What transfers to us | Verdict for A5 |
|---|---|---|---|
| **Jane Street** | ETF market-making: continuous AP-level arb on NAV / underlying basket / cross-listed ETFs + block liquidity provision | The *residual* echo of forced index-fund flows (reconstitution drift) at daily resolution | **PASS** — Greenwood & Sammon (NBER 2022) shows the index-add drift has decayed to statistical zero post-2013. 3-6% CAGR best case. |
| **DE Shaw / Two Sigma** | Bamberger-lineage stat arb + ~$100M/yr in alt data (credit card, satellite, corporate registration) + ML feature pipelines at PhD-army scale | *Philosophy*: ensemble discipline + orthogonal factor decomposition. Specific factors (Piotroski, Sloan, Novy-Marx) are mostly priced in. | **HOLD → likely KILL** — expected 9-11% CAGR, factor-duplicative with A2's low-vol leg (0.45-0.65 correlation). |
| **Renaissance / Medallion** | ~4,000+ weak signals combined through proprietary overlay + tick-level pattern matching + 40 years of proprietary data | The *philosophy*: many weak signals > one hero signal. Calendar anomalies + cross-asset lead-lag + microstructure on daily resolution. | **HOLD → GO on POC** — realistic 12-18% CAGR. The philosophically right direction. |
| **AI-Native (solo-builder advantage)** | — | LLM-based multi-document synthesis on central-bank communications (humans can't scale; BoW methods lack context) | **HOLD with Day-3 look-ahead gate** — the one genuinely novel edge we have a temporary window to capture. |

---

## Jane Street — the stack we can't access vs. the residual we might

**What they actually do** (per Matt Levine / Flirting With Models / Hoffstein interviews): JS is the authorized participant (AP) on nearly every US ETF, running a continuous three-way arb between (1) ETF market price, (2) underlying basket NAV, and (3) correlated baskets / futures / options. They're paid the creation/redemption fee + crossing bid/ask on mechanical forced flow (index funds rebalancing, AP arb during stress, block trades to ETF issuers). They also do correlated-basket arb (SPY vs e-mini, HYG vs CDX).

**None of that is replicable at $50K on Alpaca spot.** We can't become an AP, can't arb NAV intraday, can't short futures or ETFs.

**The residual**: forced index-fund flows create price drift in stocks added to / dropped from major indexes. This is the "downstream echo" after JS / Citadel / Virtu have taken the AP-level profit. Documented:
- [Chen, Noronha, Singal 2004 — "The Price Response to S&P 500 Index Additions and Deletions"](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00673.x) — original result, ~8% announcement-to-effective drift.
- [Petajisto 2011 — "The Index Premium and Its Hidden Cost for Index Funds"](https://www.petajisto.net/papers/petajisto%202011%20jempfin.pdf) — ~7% annualized from diversified reconstitution portfolio.
- **[Greenwood & Sammon 2022 — "The Disappearing Index Effect" (NBER WP 30748)](https://www.nber.org/papers/w30748)** — **load-bearing paper**: documents decay from ~8% (1990s) to statistically indistinguishable from zero (post-2013), on average.

**Lesson for us**: well-documented published anomalies decay aggressively once the frontrunners have enough capital. The "Jane Street echo" strategies are real in textbooks and dead in live markets.

## DE Shaw / Two Sigma — factor lineage + ensemble discipline

**Origin**: Gerald Bamberger's pairs-trading program at Morgan Stanley, 1980s → Nunzio Tartaglia's APT group → David Shaw founded DE Shaw in 1988 → DE Shaw alumni founded Two Sigma in 2001. The lineage is pure stat arb: mean-reversion + factor decomposition.

**What they actually do now**: multi-strategy, but the quant-equity books still run on (a) factor composites (value + momentum + quality + low-vol + profitability), (b) alt-data-driven signals (credit card panel data, satellite-measured store foot traffic, corporate registration filings for supply-chain inference), (c) ML-driven feature engineering on all of the above.

**What transfers to us**: the *philosophy* of orthogonal factor decomposition and ensemble discipline. The *specific factors* have decayed:
- Piotroski F-Score: long-short turned **negative** 2010-2020 per [Portfolio123 analysis](https://blog.portfolio123.com/why-piotroskis-f-score-no-longer-works/).
- Sloan accruals: attenuated since 2002 publication.
- Net share issuance: decayed ~30%.
- Only [Novy-Marx gross profitability (2013)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1598056) has held up decently.
- [Quality Minus Junk (Asness-Frazzini-Pedersen, AQR)](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk) — long-only quintile adaptation possible with free AQR dataset.

**Critical for us**: A2's low-vol leg already harvests most of the "quality premium" — a factor-composite A5 would be 0.45-0.65 correlated with A2 and thus factor-duplicative.

## Renaissance Technologies — the philosophy that survives, the specifics that don't

**Primary source**: [Gregory Zuckerman, *The Man Who Solved the Market* (2019)](https://www.penguinrandomhouse.com/books/576550/the-man-who-solved-the-market-by-gregory-zuckerman/). Chapters 7-9 detail Berlekamp + Laufer building the signal-combination methodology that became Medallion. Simons' public [MIT Sloan talk (2010)](https://www.youtube.com/watch?v=QNznD9hMEh0) is the other canonical source. Key direct quote: *"we search for anomalies that are not easily explainable... some have no apparent economic basis."*

**The three things we know publicly about Medallion**:
1. ~4,000+ weak signals combined through a proprietary overlay. No single signal needs to be strong.
2. Extreme short holding periods — seconds to days — most of which is inaccessible at daily bars.
3. Ruthless statistical validation — "we don't override the model."

**What actually transfers at daily resolution on a $50K book**:
- **Weak-signal ensemble philosophy** (the real transferable idea)
- **Calendar anomalies**: turn-of-month (Ariel 1987, Ogden 1990), pre-FOMC drift ([Lucca & Moench 2015, *JF*](https://www.newyorkfed.org/research/staff_reports/sr512) — documented +0.49% SPY excess in 24h pre-FOMC, still alive in post-publication samples), post-earnings drift (let Mode 2 own this).
- **Cross-asset lead-lag**: HYG 3d return → cyclicals, DXY 5d → inverse multinationals, TLT 3d → defensive names.
- **Cross-sectional reversal + low-IVOL**: stock-level signals that still print in fresh data, though weaker than publication-era strength.

**Decay warning**: turn-of-month was ~0.15%/event (1987-2005), ~0.05%/event (2010-present). Pre-FOMC drift halved since publication. The individual signals are weak now — the ENSEMBLE is the idea.

## AI-native — the only genuinely new edge

**What elite shops are doing with LLMs as of 2026**:
- [BloombergGPT (Wu et al. 2023)](https://arxiv.org/abs/2303.17564) — domain-tuned on financial text.
- [BIS Central Bank Language Models, 2024](https://www.bis.org/publ/work1215.pdf) — hawkish/dovish classification on central bank speeches.
- [IMF WP 2025/109](https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025109-print-pdf.pdf) — large-scale LLM analysis of central bank communication.
- [MDPI 2025 — "Hawkish or Dovish?" agentic Fed MPR parser](https://www.mdpi.com/2227-7390/13/20/3255).

**Where LLMs consistently fail in published work**: single-name stock picking / filtering. (Our own HUNT_APR2026 Breakthrough #1 killed this on 2026-04-17 with -1.68%/month excess. Consistent with the literature.)

**Where the solo-builder wedge might exist**: multi-document macro synthesis. Reading the full FOMC statement + press conference transcript + minutes + 2 speeches as one coherent context to extract a hawkishness score is exactly what dictionary methods (Loughran-McDonald 2011, Husted-Rogers-Sun keyword counts) structurally cannot do, and institutional quants built their pipelines pre-GPT-3.5.

### Critical methodology finding: LLM look-ahead bias

This is the single most important deliverable of the whole scout round, applicable to **any** future AI-based backtest we run.

- [Glasserman & Lin 2023 (arXiv 2309.17322)](https://arxiv.org/abs/2309.17322) — quantified look-ahead bias in GPT sentiment analysis on pre-cutoff financial news.
- [Gao, Jiang, Yan — December 2025 (arXiv 2512.23847)](https://arxiv.org/html/2512.23847v1) — developed the **Lookahead Propensity (LAP)** metric. Finding: a positive LAP-to-forecast-accuracy correlation is a smoking gun for contaminated backtests.
- [arXiv 2512.06607, December 2025](https://arxiv.org/html/2512.06607v1) — logit-adjustment mitigation technique.

**The concrete problem**: when Claude scores "FOMC March 2020 hawkishness," Claude knows COVID crashed the market days later. It has also read retrospective academic analyses of that meeting in training. Naive backtest → inflated Sharpe.

**The mandatory discipline going forward**: any LLM-scored backtest must include a cross-validation step using a pre-2022-cutoff open-weight model (Mistral-7B-Instruct or similar, runnable via Ollama). Required: Spearman rank correlation ≥ 0.85 between Claude's scores and the blind model's scores on the historical subset where Claude could have hindsight. If correlation drops on crisis events, the vector is un-backtestable honestly.

This is the FIRE-project equivalent of AUDIT_MONTH2 for AI-alpha research: a discipline constraint on methodology, not a specific strategy.

---

## Meta-takeaways

1. **Factor-diversification space is largely picked over at our scale.** Three of four scouts return HOLD/PASS. Not a failure of creativity — a real structural constraint.

2. **The RenTech philosophy (weak signals combined > hero signal) is the most durable transfer.** Not because any single signal still has strong edge, but because ensemble discipline protects against the overfitting / decay that kills individual-signal strategies.

3. **Overlay > new account.** Scout 3's meta-point: the weak-signal ensemble may be more valuable applied as an overlay to A1 (adding orthogonal ranks to the existing momentum rank) than as a standalone A5. Reframes the hunt: the A5 slot may not be where the most leverage lives. Same goes for the FOMC LLM overlay — it modulates exposure on A1+A2 rather than creating a new account.

4. **The "Super AI window" is real but narrow.** It's a multi-document synthesis edge on macro text, not a stock-picking edge. And it's gated by the look-ahead bias problem — we can't even backtest honestly without a cross-validation methodology in place.

5. **Documented anomalies decay. This is a law, not an accident.** Jane Street's flow residuals, DE Shaw's Piotroski, RenTech's calendar anomalies — all have attenuated by 30-70% since original publication. Any new A5 candidate must show it still works in post-2015 data, not publication-era data.

---

## Sources (consolidated)

### Jane Street / ETF mechanics
- Chen, Noronha, Singal (2004), "The Price Response to S&P 500 Index Additions and Deletions," *JF* — https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00673.x
- Petajisto (2011), "The Index Premium and Its Hidden Cost for Index Funds," *JEF* — https://www.petajisto.net/papers/petajisto%202011%20jempfin.pdf
- Greenwood & Sammon (2022), "The Disappearing Index Effect," NBER WP 30748 — https://www.nber.org/papers/w30748

### DE Shaw / Two Sigma / factor ensemble
- Novy-Marx (2013), "The Other Side of Value" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1598056
- Pontiff & Woodgate (2008), "Share Issuance and Cross-sectional Returns," *JF* — https://econpapers.repec.org/RePEc:bla:jfinan:v:63:y:2008:i:2:p:921-945
- Asness, Frazzini, Pedersen — "Quality Minus Junk" (AQR) — https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk
- AQR Public Datasets — https://www.aqr.com/Insights/Datasets
- "Why Piotroski's F-Score No Longer Works" (Portfolio123) — https://blog.portfolio123.com/why-piotroskis-f-score-no-longer-works/
- Two Sigma, "A Machine Learning Approach to Regime Modeling" — https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/

### RenTech / weak-signal ensemble
- Zuckerman, *The Man Who Solved the Market* (2019) — https://www.penguinrandomhouse.com/books/576550/the-man-who-solved-the-market-by-gregory-zuckerman/
- Lucca & Moench (2015), "The Pre-FOMC Announcement Drift," *JF* — https://www.newyorkfed.org/research/staff_reports/sr512
- Simons, MIT Sloan talk (2010) — https://www.youtube.com/watch?v=QNznD9hMEh0
- Gatev, Goetzmann, Rouwenhorst (2006), "Pairs Trading," *RFS* — https://www.nber.org/papers/w7032
- George & Hwang (2004), "The 52-Week High and Momentum Investing," *JF* — https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x
- Ang, Hodrick, Xing, Zhang (2006), "The Cross-Section of Volatility and Expected Returns," *JF* — https://www.nber.org/papers/w10852

### AI-native / LLM-in-quant
- BloombergGPT (Wu et al. 2023, arXiv 2303.17564) — https://arxiv.org/abs/2303.17564
- BIS Central Bank Language Models (2024) — https://www.bis.org/publ/work1215.pdf
- IMF WP 2025/109 — https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025109-print-pdf.pdf
- Husted, Rogers, Sun — Monetary Policy Uncertainty (IFDP 1215) — https://www.federalreserve.gov/econres/ifdp/files/ifdp1215.pdf

### LLM look-ahead bias (methodology)
- Glasserman & Lin (2023, arXiv 2309.17322) — https://arxiv.org/abs/2309.17322
- Gao, Jiang, Yan (Dec 2025, arXiv 2512.23847) — LAP metric — https://arxiv.org/html/2512.23847v1
- arXiv 2512.06607 (Dec 2025) — mitigation — https://arxiv.org/html/2512.06607v1
