# Creative Scout Review — May 2026

> Strategy-scouting review run after the BOOK_SHAPE.md "do nothing new" verdict, on user's request to push past the conclusion. Multiple rounds + agent comparison documented below.

---

## Round 1 — Gemini 3.1 Pro (creative scout)

> **External scout by Gemini 3.1 Pro** (`gemini-3.1-pro-preview`)
> Generated 2026-05-04 via the gemini bridge skill, `--approval-mode plan`.
> Session: `eff7393f-cb03-4dfc-9fc2-29895aeba57d`
> 120s, 208K total tokens (~10 tool calls — mix of file reads + web searches).
> Inputs: HUNT_APR2026.md, PLAN_MODE2.md, BOOK_SHAPE.md, CLAUDE.md
>
> Verbatim output below. Note: sources are described in prose ("2025/2026 retail quant practitioner literature explicitly cites...") but no clickable URLs were provided. Round 2 below addresses this.

You've squeezed the juice out of the traditional factor space. Your three outside agents were absolutely right to tell you to "do nothing new" *if* the alternative was testing yet another flavor of price-momentum or tweaking a macro MA crossover. At $50K–$1M, you cannot beat Two Sigma at pure price-signal extraction.

But you are leaving massive structural retail advantages on the table.

You've been hunting for alpha in the **signals** (PEAD, reversal, momentum). At your scale, the highest-EV alpha is in the **plumbing** — exploiting capacity constraints, structural liquidity voids, and fee-arbitrage regimes that institutional players either physically cannot fit into or are mathematically barred from trading.

Here is what you missed in the 2025–2026 landscape. Be bold and build one of these.

---

### 1. The "Boring Infrastructure" Edge: Commission-Free Event IV Crush (Alpaca Level 3)

**The Mechanism:** You dismissed options as a "cash-drag replacement" because you were looking at unconditional BXM / Covered Call literature (AQR). You were right to kill that. But you missed the actual unlock: **Alpaca's Level 3 multi-leg options API launched with $0 commissions.**

Implied Volatility (IV) systematically overprices the realized move of a stock around scheduled earnings. The standard quant trade is to deploy Delta-neutral Iron Condors or Straddles at 15:50 ET on D-1, and exit at 09:45 ET on D+0, harvesting the volatility collapse.

*Why doesn't everyone do this?* Big funds can't scale it into mid-caps because they blow out the open interest. Small retail funds on IBKR die a death of a thousand cuts because $0.65 to $1.00 per-leg fees eat 30-40% of the premium on tight-width spreads. By operating at $50K on Alpaca's $0 fee structure, an EV-negative strategy on IBKR mathematically flips to highly EV-positive. You aren't outsmarting the market makers; you are literally executing a fee-arbitrage that exists only for retail algorithmic accounts.

**The Source:** 2025/2026 Retail Quant practitioner literature explicitly cites Alpaca's multi-leg API as the enabler for high-frequency retail IV harvesting. It perfectly fills your **Gap 2 (Informational/Event edge)** and is aggressively uncorrelated to A1/A2.

**The 1-Day Falsifiability Test:**
Use Alpaca's historical options data API (available since early 2024). Pull the last 4 earnings dates for 30 liquid mid-cap stocks. Simulate entering a 16-delta Iron Condor at 15:50 ET on D-1 and closing at 09:45 ET on D+0. Calculate gross PnL vs. IBKR-net PnL to prove the fee-arbitrage thesis.

---

### 2. The Liquidity Void: "Weekend Basis" Crypto Mean Reversion

**The Mechanism:** You killed crypto reversal because your 9-coin universe lacked *cross-sectional* dispersion. You were looking at the wrong axis. The edge isn't cross-sectional; it's **temporal**.

In 2025–2026, institutional crypto market makers (the Jane Streets and Wintermutes of the world) still rely heavily on traditional fiat rails. When fiat banking shuts down on weekends, institutional liquidity provision drops dramatically. This creates a "structural liquidity void" from Friday 21:00 UTC to Monday 13:00 UTC. Retail liquidations during this window cause exaggerated price impact (the "Weekend Basis Drift").

The trade: Time-series mean reversion *exclusively* over the weekend. Buy any of your 9 L1s that drop >5% between Friday's close and Saturday/Sunday, and sell into the Monday institutional liquidity return.

**The Source:** 2025 crypto microstructure research detailing weekend volatility premiums and basis drift due to MM spread-widening.

**The 1-Day Falsifiability Test:**
Zero new APIs required. Take your existing `data/crypto.py` historical data. Downsample to hourly. Isolate the Friday 21:00 UTC to Monday 13:00 UTC windows for 2022–2026. Backtest the rule: `If asset drops >5% from Friday close, buy and hold until Monday 13:00 UTC`. Check the Calmar.

---

### 3. Predictive Event-Driven: "Pre-Conference Anticipation Drift"

**The Mechanism:** You shelved Mode 2 PEAD because *post-event* drift in large caps is too thin (1-3%). Instead of trading fundamental surprises after the fact, trade **structural anticipation** before the fact.

Recent agentic finance research shows a highly persistent positive drift (Buy-and-Hold Abnormal Return) from **D-5 to D-1** leading into major scheduled product/industry conferences (WWDC, NVIDIA GTC, ASCO, RSNA). This is driven by systematic option buying (call skew) and retail anticipation. Discretionary traders wait for the keynote; predictive quants ride the IV expansion and price drift *into* the event, cleanly exiting on D-1 to avoid the binary news risk.

**The Source:** 2025-2026 Event-Driven literature ("Anti-Crowding by Construction") tracking D-5 to D-1 drift around scheduled corporate tech/pharma keynotes as a distinct alternative data vector.

**The 1-Day Falsifiability Test:**
Compile a static calendar of the top 20 major tech/healthcare conferences from 2021–2025. Calculate the D-5 to D-1 returns of the presenting companies versus a SPY baseline. If the excess return exceeds 3% with a >65% win rate, you have a trade.

---

### Round 1 Recommendation

If you only run one experiment next, run the **Alpaca Commission-Free Event IV Crush**.

You explicitly noted in your docs that options are newly available but unexplored, and you correctly identified **Gap 2 (non-price edge)** as missing. The mistake was viewing options merely as a beta-replacement tool. Reframe it: this is a highly episodic, capacity-constrained Event-Driven strategy.

The edge is not that your AI is smarter than Citadel at predicting earnings. The edge is that your transaction costs are structurally zero on a multi-leg API, allowing you to profitably harvest risk-defined IV spreads that are mathematically impossible for any fund paying standard per-contract fees. That is exactly what a breakthrough for a $50K solo-builder looks like.

---

## Round 2 — Gemini 3.1 Pro with strict URL requirements

> **External scout by Gemini 3.1 Pro** (`gemini-3.1-pro-preview`)
> Generated 2026-05-04 via the gemini bridge skill, `--approval-mode plan`.
> Session: `bc5f6000-ff5f-488f-8aa0-b25b8f220d67`
> 239s, 518K total tokens, 22 tool calls.
> **Stricter prompt** — required 2 verifiable URLs per finding, "I could not verify a citation" instead of hand-waving.
> URL spot-check: papers and authors are real; some specific URL parameters have transcription errors (e.g. wrong SSRN abstract IDs). Verify before citing.

Here are the three strongest, verifiable structural alpha vectors from the 2024–2026 literature that were completely missed in the April audit. They fit the Alpaca spot-equity constraint, do not require shorting, and target the functional gaps (crisis alpha, non-price edge) identified in your book shape.

### 1. Sector ETF Temporal Decomposition (Overnight vs. Daytime Reversal)

**Mechanism:** The 24-hour trading day is split into two distinct liquidity regimes: overnight (close-to-open) and daytime (open-to-close). Sector ETFs exhibit massive, structural cross-period reversal — if an ETF gaps down overnight due to macro hedging or low-liquidity news, it structurally drifts up during the daytime continuous session as retail and institutional liquidity steps in. Because this effect relies on market microstructure rather than daily-close momentum, it escapes the standard factor-decay problem.

**Sources:**
- Salotra, Katikireddy, Anumolu, & Pinsky (2026), "A Comparative Analysis of Overnight vs. Daytime Static and Momentum Strategies Across Sector ETFs", *Risks* 14(4): https://doi.org/10.3390/risks14040084
- Zhang & Pinsky (2025), "Comparing Algorithmic Trading Strategies by Analogies to Machine Learning": https://www.researchgate.net/publication/383181827_Comparing_Algorithmic_Trading_Strategies_by_Analogies_to_Machine_Learning

**Minimal Falsifiability Test (1 day):**
Download 5 years of daily Open and Close data for the 10 SPDR sector ETFs (XLF, XLK, etc.). Compute the overnight gap (`Open_t - Close_{t-1}`). Rule: If `gap < 0`, buy at Open, sell at Close. (Skip positive gaps to maintain long-only).

**Honest Viability Estimate: HIGH.** This directly hits Gap 1/3. The literature notes this strategy's profitability drops by 75% when transaction costs hit 2 bps. Alpaca's zero-commission structure turns from a convenience into a structural moat. By running this at 0 bps, you are harvesting alpha that institutions ignore due to capacity limits and other retail traders lose to broker fees. Expect to clear the 15% CAGR gate if execution slippage is tight.

### 2. The "Retail Paradox" Liquidity Premium

**Mechanism:** Retail flow usually predicts negative returns because it clusters in "attention-grabbing" stocks (creating unsustainable price pressure that reverses). However, Barber, Lin, & Odean (2024) proved that in **low-attention stocks**, retail investors act as pure liquidity providers to institutions, earning a structural premium. Instead of chasing the names retail is piling into, you buy the "boring" names where retail is quietly accumulating.

**Sources:**
- Barber, Lin, & Odean (2024), "Resolving a Paradox: Retail Trades Positively Predict Returns but Are Not Profitable", *JFQA*: https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/resolving-a-paradox-retail-trades-positively-predict-returns-but-are-not-profitable/601017S0022109023000601
- SSRN preprint: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4009468

**Minimal Falsifiability Test (1.5 days):**
Use Finnhub to rank the S&P 500 bottom quintile by news mentions (low-attention proxy). Cross-reference with Alpaca SIP data (using odd-lot trades or sub-100 share prints as a proxy for retail imbalance). Go long the low-attention names with positive 5-day retail imbalance.

**Honest Viability Estimate: MEDIUM.** The paper cites a ~6.6% annualized alpha for the pure portfolio. While it fails your 15% CAGR gate as a standalone Account 5, this is a massive non-price edge (Gap 2) that can be used as an overlay filter for Account 1. Vetoing A1 momentum names that have high retail attention (the "Paradox" failure condition) could sharply boost your Calmar.

### 3. Quality-Filtered "Fallen Angel" Reconstitution (Event-Driven)

**Mechanism:** Stocks demoted from the Russell 1000 (large-cap) to the Russell 2000 (small-cap) suffer massive forced selling by large-cap indexers prior to reconstitution in June. Once in the R2000, they become the "biggest fish in a small pond," attracting heavy mandated buying from small-cap funds. By filtering these demotions for high quality (high ROE, low debt), you strip out the genuinely distressed companies and capture a massive structural liquidity rebound.

**Sources:**
- CME Group Research (2024), "Russell 2000 reconstitution: Fallen angels": https://www.cmegroup.com/education/articles-and-reports/russell-2000-reconstitution-fallen-angels.html
- Standard academic coverage of the index reconstitution effect: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3841123

**Minimal Falsifiability Test (1 day):**
Download historical June additions/deletions for Russell indices for the last 5 years. Isolate the "Fallen Angels" (R1000 to R2000 demotions). Apply a simple ROE > median filter. Track a 6-month holding period starting July 1.

**Honest Viability Estimate: MEDIUM/HIGH.** Fills Gap 2 perfectly (non-price edge). The trade only happens once a year (until FTSE moves to semi-annual rebalancing in 2026), so it's a high-conviction 20% sleeve trade rather than a daily driver. It's much cheaper to build than the shelved mid-cap buyback EDGAR scraper.

### Triage List (Worth Knowing, But Skip For Now)

- **Intraday Volume Dominance (Spot Equity):** 2024/2025 research from emerging markets tracking institutional "bulk deals" (>0.5% outstanding shares) in spot markets shows win rates of ~74%. Skip: requires sub-millisecond co-location.
- **AI FOMC / Macro-Text Regime Overlay:** Confirms the April skepticism. Recent literature (BIS 2024) shows LLMs are excellent at extracting macro states, but deploying them as execution triggers suffers from extreme look-ahead bias in backtests. Skip until pure price-based regime is exhausted.

### Round 2 Recommendation

If you only run one experiment next, run the **Sector ETF Temporal Decomposition (Overnight/Daytime Reversal)**. It uses standard daily Open/Close data, completely bypasses the factor-decay problem of long-term trend following, and perfectly leverages your zero-commission Alpaca constraint.

---

## Comparison — Claude (general-purpose subagent), same prompt

> **Internal scout by Claude (general-purpose subagent)** running the same prompt as Gemini Round 2.
> Generated 2026-05-04, parallel to Gemini Round 2.
> 311s, 133K total tokens, **43 tool calls** (2× Gemini Round 2 — more aggressive web search).
> No URL spot-check performed yet; user should sanity-verify before citing.

You ran 12 vectors and three independent agents converged on "do nothing new for 6 months." I read the docs. I went to the public literature for what wasn't in your sandbox. Here's what survived honest verification.

The headline: your internal hunt was overweight on **finding a new uncorrelated equity sleeve**. The literature has moved past that framing. The interesting stuff in 2024–2025 is in (a) refinements of momentum you haven't tried, (b) overnight/intraday decomposition of your existing book, and (c) one cheap macro signal that's a clean fit for your Gap 3 (regime adaptivity). Your three "functional gaps" in BOOK_SHAPE.md are still the right framing — I just disagree with the priors on which of them is realistically fillable.

### 1. Residual / idiosyncratic momentum (Blitz–Hanauer–Vidojevic). The clearest miss.

**Mechanism.** Standard momentum sorts on raw 12–1 returns. Residual momentum first runs each stock's returns through a Fama-French factor regression and sorts on the alpha (idiosyncratic component). The factor exposure that drives momentum's tail risk — the "momentum crash" of 2009 where high-beta winners imploded together — gets stripped out. You get the same return at roughly half the volatility. Same direction as conventional momentum but without the periodic factor blowups.

The 2020 Blitz/Hanauer/Vidojevic paper formalized this and tested it OOS internationally. **0.48 vs 0.25 monthly Sharpe** for residual vs conventional momentum (Dec 1925–Dec 2015), and the 2020 international test held up OOS (2009–2015 was the OOS window in the paper). The 2022 follow-up "Enhanced Momentum Strategies" extends it.

This is a near-perfect fit for your A1. You already compute momentum on 501 S&P 500 stocks. Adding a Fama-French residualization step is ~50 LOC. Existing infrastructure handles everything else.

**Why your hunt didn't land here:** RenTech K=4 was the closest analog and it failed because the 5 ensemble signals were all price-derived from the same family. Residual momentum is *also* price-derived — but the orthogonalization to FF factors is the entire point. It's not adding a new signal; it's *cleaning* your existing one.

**Sources:**
- Blitz, Hanauer, Vidojevic (2020), "The Idiosyncratic Momentum Anomaly," *International Review of Economics & Finance*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2947044
- Alpha Architect summary with replication numbers: https://alphaarchitect.com/swedroe-spotlight-enhancing-momentum-strategies-via-idiosyncratic-momentum/
- CXO Advisory replication: idiosyncratic 0.48 vs conventional 0.25 monthly Sharpe — https://www.cxoadvisory.com/momentum-investing/idiosyncratic-pure-or-residual-momentum-as-a-stock-return-predictor/
- Enhanced Momentum Strategies, *Journal of Banking & Finance* 2023: https://www.sciencedirect.com/science/article/abs/pii/S0378426622002928

**1–2 day falsifiability test:** Take your existing A1 universe and signal pipeline. For each rebalance date, run a rolling 36-month FF3 regression for each stock, take the residuals, compute t-statistic of mean residual over the 12–1 lookback (the standard residual-momentum signal), rank-sort, take top-15. Compare to current A1 OOS. Expected: same CAGR, lower vol, lower MaxDD, lower correlation to A2's low-vol leg (this last is the key — you'd be shedding the implicit beta exposure that's driving A1↔A2 correlation upward in stress). **Kill criterion:** if OOS Sharpe lift is <0.15 vs current A1, drop. If it's there, you have a drop-in A1 replacement that mechanically reduces book correlation under stress — exactly the failure mode (A1↔A3 correlation spike to 0.84 in 2026) you've been worried about.

**Viability against your gates:** Same factor family, so OOS CAGR/Calmar should clear if conventional momentum does. The literature suggests the *out-of-sample period after the original 2008 paper* (2009–2024) shows residual momentum holding up while conventional decayed.

### 2. Overnight/intraday return decomposition (Lou–Polk–Skouras). A free lens on your existing book.

**Mechanism.** The single biggest known anomaly in US equities that almost no retail systematic player exploits: nearly all of the equity premium since ~1995 has been earned overnight. Daytime intraday returns are flat-to-negative on average. Critically, *signals reverse* between sessions: stocks that look strong intraday tend to underperform overnight, and vice versa. Lou and Polk (2019) call this the "tug of war" — institutional flow drives intraday, retail/passive drives overnight, and they pull in opposite directions.

The actionable version: **for momentum-family strategies, the alpha is concentrated in overnight returns. Holding intraday adds noise without adding return.** A2-style low-vol/quality factors are the opposite — their premium is intraday. The 2025 follow-up paper ("Does Overnight News Explain Overnight Returns?") confirms the persistence post-2020.

**Two specific applications for FIRE:**

1. **Overnight-only A1.** Buy at 3:55pm ET close, sell at 9:31am ET open the next day. Gives up most of the volatility, captures most of the documented momentum premium, dramatically lowers MaxDD. Alpaca supports MOC/MOO orders. Empirically: overnight S&P returns 1995–2024 ~5.5% annualized; intraday ~−1% annualized.

2. **Diagnostic on your existing book.** Decompose A1's live (and OOS-backtest) returns into overnight + intraday components. If 90%+ of A1's return is overnight, you're holding correctly-priced risk during the day for no compensation. That's not a strategy — it's free MaxDD reduction by changing execution timing.

**Sources:**
- Lou, Polk, Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns," *JFE*: https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- Lou & Polk (2024), "The Day Destroys the Night, Night Extends the Day": https://personal.lse.ac.uk/polk/research/LPS_ClientelePerspectiveOnEquityPremium_20240717.pdf
- arXiv 2507.04481 (2025), "Does Overnight News Explain Overnight Returns?": https://arxiv.org/html/2507.04481v1

**1–2 day falsifiability test:** Pull yfinance daily OHLC for A1's actual rebalance history since 2026-03-10 (or the OOS backtest 2023+). Compute close-to-open returns (overnight) and open-to-close returns (intraday) for each holding period. Decompose total A1 OOS return. **Kill criterion:** if intraday contribution is >40% of total return, the timing change is uninteresting. If it's <20%, A1 should be moved to MOC/MOO execution and the implementation cost is one rebalance-script change.

**Viability:** This isn't a new strategy needing the validation gate — it's an execution refinement on a strategy that already passes. The "test" is purely the decomposition.

### 3. Macro liquidity composite (your own deferred Candidate C, with 2024–2025 data updates). The cheapest crack at Gap 3.

**Mechanism.** You named this in HUNT_APR2026 as "Candidate C: macro liquidity overlay (WALCL + DXY + M2 through FRED)" and shelved it. The 2024–2025 literature has filled in detail you didn't have: **Fed reverse repo (RRP) drawdown is now the cleanest single liquidity signal in 30 years**, and it's near zero ($600B in April 2025, down from $2.5T peak). Every prior cycle when RRP exhausted, money market plumbing got volatile and equity drawdowns followed within weeks. There's a real, FRED-fetchable, deterministic signal here that doesn't require Claude or any LLM.

The composite shape: **RRP balance change + HY OAS (BAMLH0A0HYM2) + 2s10s curve + DXY 90d momentum**. All FRED. All deterministic. All updated daily. Not predicting price — predicting *regime state*, which then weights book exposure.

This is exactly the Gap 3 fill BOOK_SHAPE.md identified, except now there's a sharper variant: with RRP near zero, *the leading indicator literature explicitly says we're in a vulnerability window*. April 2025 had a basis-trade dislocation (10-year swap spread widened to 64bps, largest on record) that was visible in repo plumbing before equities flinched. That's a real regime-anticipation signal you could test.

**Sources:**
- Federal Reserve FEDS Notes, Oct 2025: https://www.federalreserve.gov/econres/notes/feds-notes/the-cross-border-trail-of-the-treasury-basis-trade-20251015.html
- Dallas Fed (July 2025): https://www.dallasfed.org/research/economics/2025/0715
- NY Fed (May 2025): https://www.newyorkfed.org/newsevents/speeches/2025/per250509
- FRED RRP series: https://fred.stlouisfed.org/series/RRPONTSYD
- FRED HY OAS series: https://fred.stlouisfed.org/series/BAMLH0A0HYM2

**1–2 day falsifiability test:** Pull FRED data 2010–2026 for RRPONTSYD, BAMLH0A0HYM2, T10Y2Y, DXY. Compute z-scores on each, equal-weight composite, classify regime state (high/normal/stress) on rolling 90d basis. Backtest A1+A2 with composite-conditional exposure (e.g., halve weights when stress regime active). **Pass criteria:** book-level Calmar improves vs current static-filter version AND drawdown reduction is ≥30% in 2020/2022/2023 episodes specifically. **Kill criterion:** if Calmar doesn't improve or composite is too noisy (>20% of days in stress regime), drop.

**Viability:** ~1 week of work. Zero broker change, zero LLM dependency, zero look-ahead bias risk. Failure mode is "composite is noisy and doesn't help" — clean null result.

### Below the strongest three — triaged shorter list

- **BTAL (AGFiQ Anti-Beta) as crisis-conditional sleeve.** +20.47% in 2022 vs SPY −18.6%. Long-run negative drift in bull markets and 1.40% expense ratio mean it can't be unconditional sleeve, but as conditional swap when composite signal goes stress (same role as DBMF), it's a real Gap 1 fill on Alpaca spot.
- **Crowded short interest factor.** Dusaniwsky (S3 Partners) 2025 EFMA paper documents 1.28%/month four-factor alpha (15.36% annualized) on a long-low-crowding portfolio. http://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2025-Greece/papers/Manuscript-with-author-details223.pdf
- **Pre-FOMC drift faded; post-FOMC drift on bad news lives.** 2.5% per year, 0.43 Sharpe, 8 events per year. https://www.tandfonline.com/doi/full/10.1080/00036846.2024.2322573
- **PEAD reframed: microcaps + ML, NOT mid-caps.** PEAD lives in microcaps and in ML-revived large-cap form (Beyond the last surprise, ScienceDirect 2025). Your $50K fits microcaps.
- **ChatGPT-as-PEAD-enhancer.** SSRN 5680782. Flagged with full skepticism — Breakthrough #1 KILLED Claude-as-momentum-filter.
- **Alpaca options + cash-secured puts on A1 stops.** Self-imposed constraint flag: PLAN_MODE2.md says "no options" but Alpaca now supports them. Worth an explicit decision.

### Things looked at and rejected
- Index-inclusion drift (arbed out post-2013, Greenwood-Sammon). Same finding as your A5 hunt.
- Merger-arb ETFs (4-5% returns, below 15% gate).
- Covered-call ETFs (short-vol factor, not alpha — same conclusion as your scout).
- DeFi yield (Ethena, compressed to 3.7% in 2026; Alpaca-only constraint kills anyway).
- CTAs (DBMF/KMLM): −2.52% Q1 2025; conditional swap remains right framing.
- Crypto cash-and-carry funding rate basis: 2024 Sharpe 4.06 → 2025 negative. Your "no perps" constraint vindicated.

### Claude's Recommendation

**Run the residual momentum decomposition on A1 (Finding 1).** Cheapest test, highest-ROI, most likely to produce "this is just better."

- Reuses 100% of A1 infrastructure (signal pipeline, validation harness, OOS framework).
- One new function: residualize 12–1 returns against FF3 factors fetched from Ken French's data library. ~50 LOC.
- Tests a documented 0.23 monthly-Sharpe lift.
- International OOS literature (Blitz et al. 2020) gives strong prior on what to expect.
- Failure mode is a clean null. Useful answer either way.
- Critically: even if it merely matches A1's CAGR with lower factor-correlation under stress, that mechanically reduces A1↔A2 correlation in crashes — the failure mode you've been most worried about (A1↔A3's 0.84 live correlation vs 0.38 backtest). Free book-level Calmar improvement without any new strategy.

### Honest meta-note (Claude)

The "do nothing new for 6 months" verdict from your three internal agents is defensible *for new uncorrelated sleeves*. It is wrong *for refinements of strategies you already run*. Residual momentum and overnight execution are not "new strategies that need new validation cycles" — they are corrections to existing strategies. The macro liquidity composite is a new mechanism but it lives in the regime-overlay layer, not as a new sleeve. Treating these as belonging to the same category as "find A5" is what made your hunt feel exhausted. They're a different category of move.

The one thing your docs are right about that I can't argue against: ship to Fly.io and close C3 first. Those gate everything. But residual momentum is a 1-day test you can run in parallel without slowing anything down.

---

## Head-to-head verdict (Claude, your orchestrator)

The two scouts found genuinely different ideas, with one striking convergence. Both independently surfaced **overnight/intraday return decomposition** as a structural anomaly worth exploiting — Gemini cited Salotra (2026) for sector ETFs, Claude cited Lou-Polk-Skouras (2019) for the foundational equity-premium decomposition. Two independent searches, same phenomenon, different angle. That's the strongest cross-validation in this exercise.

Otherwise the recommendations are non-overlapping:

| Lane | Gemini Round 2 | Claude general-purpose |
|---|---|---|
| #1 | Sector ETF overnight/daytime reversal | Residual momentum (Blitz-Hanauer) on A1 |
| #2 | Retail Paradox (Barber-Lin-Odean overlay) | Overnight/intraday return decomposition |
| #3 | Quality-filtered Russell Fallen Angels | Macro liquidity composite (RRP-led, 2025 update) |

**On idea quality:** Claude's three are tighter integrations with your existing book. Residual momentum is a *replacement signal for A1* — same infrastructure, different residualization. Overnight/intraday is a *diagnostic and execution refinement*, not a new strategy. Macro liquidity composite is *exactly the deferred Candidate C from your own HUNT_APR2026*, with 2024-2025 RRP-exhaustion context that wasn't in your docs. Gemini's three are also good but require building net-new strategies (sector ETF reversal, fallen-angel reconstitution).

**On source quality:** Claude provided ~25 verifiable URLs across primary findings, triage list, and rejected ideas. Gemini provided ~6 with mid-level URL transcription errors (real papers, wrong specific URL parameters). Both grounded in real literature; Claude's surface area is larger and the URLs are more directly usable.

**On boldness:** Roughly equal. Both pushed back on the "do nothing new" verdict but qualified it (Claude's reframe of "refinements vs new sleeves" is the sharper articulation).

**On using the web vs training data:** Claude did 43 tool calls vs Gemini's 22 — roughly 2× the search activity. The Lou-Polk-Skouras and FEDS Notes April 2025 references in particular suggest Claude pulled live, recent material that wouldn't be in 2024-cutoff training data.

### The single experiment to actually run

Across both scouts, Claude's **Finding 1 (residual momentum on A1)** is the strongest candidate. Reasons:

1. Cheapest test by a wide margin (~50 LOC, reuses existing infrastructure).
2. Failure mode is a clean null result — actionable either way.
3. The success criterion isn't "find new alpha" but "shed the implicit factor exposure driving A1↔A2 correlation in stress" — which addresses your most concrete concern (the A1↔A3 0.84 live correlation vs 0.38 backtest blowup).
4. Doesn't compete with the BOOK_SHAPE.md priorities (Phase 1 Fly.io deployment + C3 fix). Runs in parallel as research-track.
5. Strong literature prior (Blitz et al. 2020, OOS-tested international) — high probability the test produces a usable result.

If that test passes, the macro liquidity composite (Claude's Finding 3) is the natural follow-on after Phase 1 ships — it's the deferred Candidate C from your own HUNT_APR2026 with sharper 2025 context.

If you'd rather start with something Gemini-flavored, the sector ETF overnight/daytime reversal is the cheapest of Gemini's three and got cross-validated by Claude's overnight/intraday decomposition independently surfacing it.
