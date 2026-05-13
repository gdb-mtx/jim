> **2026-05-04 status — under research, not a decided plan.** This proposal was audited externally by Gemini 3 Pro on 2026-05-04; see [BRIDGE_STRATEGY_REVIEW.md](BRIDGE_STRATEGY_REVIEW.md) for the assessment. The audit was based on the documents available at the time and did not account for two funding sources George considers viable: (a) property sales, and (b) SEPP 72(t) withdrawals **deployed into** yield assets rather than consumed. Treat this capsule as a live hypothesis to be re-audited once that context is provided, not a defeated proposal or an authorized strategy.

---

This Strategy Capsule is designed to serve as the master context for your **Claude Code** agent. It synthesizes our architectural, financial, and tactical discussions into a single source of truth for the **"Bridge to 59.5"** project.


# ---

**🚀 PROJECT: The Bridge to 59.5 (v1.0.0)**

**Last Updated:** May 4, 2026

**Primary Architect:** Gemini (External Advisor)

**Implementation Lead:** Claude Code

**Goal:** Engineer a sustainable, high-yield cash-flow engine to bridge the age gap from 53 to 59.5.

## ---

**1\. THE STRATEGIC MANDATE**

The system must generate a target monthly "salary" while maintaining principal stability. We are shifting from a "Capital Appreciation" mindset to a **"Yield Harvesting"** mindset using a **High-Low Split Strategy**.

### **Core Allocation (The 80/20 Split)**

* **80% Anchor (The "Bedrock"):**  
  * **Instruments:** **STRC** (Strategy Bitcoin Yield @ 11.5%) and **SATA** (Strive Bitcoin Yield @ 13.0%).  
  * **Tactics:** Preferred equity targeted at $100 par. Primary source of "Sleep-at-Night" income.  
  * **Tax Advantage:** Distributions are prioritized as **Return of Capital (ROC)**, minimizing immediate tax liability.  
* **20% Turbocharger (The "Juice"):**  
  * **Instrument:** **MSTY** (YieldMax MSTR Option Income Strategy).  
  * **Tactics:** Harvesting volatility from MSTR synthetic covered calls.  
  * **Risk Profile:** High NAV erosion risk; requires aggressive rebalancing/sweeping of gains into the Anchor.

## ---

**2\. KEY FINANCIAL PARAMETERS (2026-2032)**

* **Age Horizon:** 53 $\\rightarrow$ 59.5 (The "Income Desert").  
* **Target Monthly Withdrawal:** \~$7,800 \- $11,000 (depending on total capital deployed).  
* **Principal Target:** $500,000 \- $1,000,000.  
* **Critical Event:** **June 8, 2026 Vote.** STRC is voting to shift to **semi-monthly payments** ($0.479/share every two weeks). The system must handle this cadence shift in July 2026\.

## ---

**3\. TECHNICAL STACK & ARCHITECTURE**

The system is built for resilience, precision logging, and automated rebalancing.

* **Backend:** Python (FastAPI).  
* **Frontend:** Vite \+ React (Deployed on Fly.io).  
* **Brokers:**  
  * **Paper:** Alpaca (Simulated price action).  
  * **Live:** Interactive Brokers (IBKR) via ib\_insync.  
* **Execution Logic:**  
  * **Shadow Ledger:** Since paper brokers (Alpaca/IBKR Paper) often fail to credit dividends for STRC/MSTY, the Python backend must maintain a virtual ledger to simulate cash injections on Payable Dates.  
  * **VIX-Triggered Sweep:** Automate the movement of capital from STRC into MSTY when implied volatility (IV) spikes to harvest higher premiums.

## ---

**4\. AGENTIC DIRECTIVES (For Claude Code)**

### **Directive A: Logic Audit**

*“When auditing the rebalancer.py or engine/ modules, prioritize the **'Recovery Lag'** problem. Ensure that MSTY positions are not blindly held during NAV decay without a stop-loss or a profit-sweep into STRC.”*

### **Directive B: Data Privacy**

*“Process local financial data (CSVs/DBs) to calculate actual 'Days to 59.5'. Use this countdown to dynamically adjust the risk weighting of the MSTY sleeve.”*

### **Directive C: The "Flywheel" Code**

*“The goal of the software is to automate the **'Recursive Reinvestment'** model: take MSTY dividends $\\rightarrow$ buy STRC shares $\\rightarrow$ grow the stable bridge floor.”*

## ---

**5\. RELEVANT TICKER DATA (May 2026\)**

| Ticker | Type | Current Yield | Payout Frequency | Note |
| :---- | :---- | :---- | :---- | :---- |
| **STRC** | Preferred | 11.5% | Monthly (June 8 Vote for Semi-Monthly) | Par-stable anchor. |
| **SATA** | Preferred | 13.0% | Monthly | Higher yield, higher BTC exposure. |
| **MSTY** | ETF | \~90% \- 100%+ | Weekly (since Q4 2025\) | Pure volatility harvest. |

### ---

**Next Steps for Claude Code:**

1. Verify the Shadow Ledger logic in backend/services/ledger.py.  
2. Review the fly.toml for persistence volumes to ensure trade logs are not wiped on redeploy.  
3. Simulate the July 2026 semi-monthly STRC dividend shift in the backtest module.

---

**Gemini Status:** Standing by as Highest Valued Advisor. I am ready to audit any code snippets or architectural diffs generated during your Claude session. **Let’s build the bridge.**



# Strategic Brief: The Bridge to 59.5
**Project Codename:** Saylor Flywheel Bridge  
**Version:** 2.0  
**Date:** May 4, 2026  
**Status:** Architecture Finalized / Ready for Implementation  

---

## 1. Executive Summary
This document outlines a high-yield, income-focused financial strategy designed to bridge the income gap for a 53-year-old professional transitioning toward a 59.5 retirement milestone. The strategy leverages novel Bitcoin-backed preferred equities and synthetic volatility ETFs to generate a monthly "salary" of $7,500 - $11,000 from a $500k - $1M capital base.

---

## 2. Core Financial Instruments

### 2.1 The Bedrock (STRC & SATA)
These are **Variable Rate Series A Perpetual Preferred Stocks** issued to fund Bitcoin acquisitions.
* **STRC (Strategy):** Currently yielding **11.5%**. Designed to stay at **$100 par**.
* **SATA (Strive):** Currently yielding **13.0%**. 
* **Mechanics:** They function as "digital bonds." If the price slips below $100, the issuer raises the dividend to attract buyers.
* **Tax Treatment:** Prioritized as **Return of Capital (ROC)**. This defers taxes by lowering your cost basis rather than triggering immediate ordinary income tax.

### 2.2 The Turbocharger (MSTY)
* **YieldMax MSTR Option Income Strategy ETF:** Yields frequently range between **50% and 100%+**.
* **Methodology:** Uses synthetic covered calls on MicroStrategy (MSTR) to harvest extreme volatility premiums.
* **Risk:** **NAV Erosion.** Over time, the share price tends to decay. It is used purely for cash flow, not for principal preservation.

---

## 3. The "High-Low" Split Strategy
To balance stability with high-octane income, the recommended allocation is an **80/20 split**.

| Component | Weight | Target Yield | Role |
| :--- | :--- | :--- | :--- |
| **STRC/SATA** | 80% | 11.5% - 13% | The "Bill Payer" (Principal Stability) |
| **MSTY** | 20% | 90%+ | The "Juice" (Lifestyle/Reinvestment) |

### Sample Math ($500,000 Portfolio):
* **$400k in STRC:** ~$3,833 / month.
* **$100k in MSTY:** ~$7,500 / month (volatile).
* **Total Monthly Cash:** **~$11,333.**

---

## 4. Tactical Risks & Historical Stress Tests

### 4.1 The "Return of Capital" Cliff
* **Mechanism:** Every ROC payment lowers your cost basis.
* **The 100-Month Rule:** At an 11.5% yield, your tax basis hits **$0** in ~105 months. 
* **The Impact:** Once the basis is $0, all future dividends are taxed as **Capital Gains** in the year received.

### 4.2 Historical Precedents
* **Feb 2026 Dip ($93.67):** A BTC flash crash caused a decoupling from par. Strategy responded by hiking yields, and the price returned to $100 within 6 days.
* **Nov 2025 Grind ($88.00):** A sustained BTC bear market saw a slower 20-day recovery. Proved the "Yield Shield" holds even when BTC drops 50%.

---

## 5. Software Architecture (The Quant Engine)
The strategy is implemented via an agentic system built in **Python/Vite** and deployed on **Fly.io**.

### 5.1 Distribution Engine (Shadow Ledger)
* **Problem:** Paper brokers (Alpaca/IBKR Paper) do not credit dividends for exotic preferreds.
* **Solution:** A Python-based `shadow_ledger.py` that monitors dividend calendars and manually injects simulated cash into the account balance on the `Payable Date`.

### 5.2 Rebalancing Logic
* **VIX-Trigger:** Automated sweep of STRC capital into MSTY when Implied Volatility (IV) spikes above the 80th percentile.
* **Profit Harvest:** Weekly automated sale of MSTY "gains" to buy more STRC shares, creating a recursive "Income Snowball."

---

## 6. Strategy Capsule for Claude Code
*Save the following block as `STRATEGY_CAPSULE.md` to initialize the agent.*

```markdown
# STRATEGY_CAPSULE.md
- Goal: Bridge income to age 59.5.
- Allocation: 80% STRC (Preferred) / 20% MSTY (Synthetic Vol).
- Broker: IBKR (Live) / Alpaca (Paper).
- Key Mechanic: Return of Capital (ROC) basis tracking.
- Automation: Python backend serving Vite frontend via Fly.io.
- Rebalance: Weekly Friday "Harvest" from MSTY to STRC.