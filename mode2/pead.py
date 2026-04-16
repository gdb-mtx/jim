"""
PEAD (Post-Earnings Announcement Drift) analysis prompts and scoring.

The prompt IS the strategy. This module defines the structured analysis
framework that Claude uses to evaluate earnings reports and identify
PEAD opportunities.
"""

# The PEAD scoring prompt — structured for repeatable, JSON-output analysis.
# Used in two contexts:
# 1. In-conversation: George pastes transcript, Claude scores it
# 2. Programmatic: Fed to Claude API for batch analysis (future)
PEAD_SCORING_PROMPT = """You are analyzing an earnings call transcript to identify Post-Earnings Announcement Drift (PEAD) trading opportunities.

PEAD is the tendency for stocks to drift 3-8% over 60-90 days in the direction of an earnings surprise. The drift is strongest when the surprise reflects genuine business momentum, not one-time items.

## Company Context
- **Symbol:** {symbol}
- **Quarter:** Q{quarter} {year}
- **EPS Actual:** ${eps_actual}
- **EPS Estimate:** ${eps_estimate}
- **EPS Surprise:** {surprise_pct:+.1f}%
- **Current Price:** ${current_price}

## Your Analysis Tasks

### 1. Surprise Quality Score (1-5)
Score the QUALITY of the earnings surprise, not just the magnitude:
- **5 = Exceptional:** Revenue-driven beat with accelerating growth, expanding margins, AND guidance raise
- **4 = Strong:** Revenue beat with sustainable drivers, stable/improving margins
- **3 = Moderate:** Earnings beat but mixed signals (cost-cutting, one-time items, flat revenue)
- **2 = Weak:** Earnings beat driven by non-operational items (tax benefit, asset sale, accounting)
- **1 = Misleading:** Headline beat masks deterioration (declining revenue, margin compression, lowered guidance)

### 2. Guidance Assessment
- What is management guiding for next quarter and full year?
- Did guidance CHANGE vs prior expectations?
- Is the guidance conservative (sandbagging) or aggressive?
- Are analysts likely to revise estimates up or down?

### 3. Management Tone Analysis
- Confidence level: Are executives confident or hedging?
- Specificity: Do they give concrete details or vague generalities?
- Q&A behavior: Do they answer questions directly or deflect?
- Red flags: Any unusual language, defensiveness, or topic avoidance?

### 4. Revenue vs Earnings Quality
- Is the beat revenue-driven (sustainable) or cost-driven (temporary)?
- Organic growth vs acquisitions/divestitures?
- Is the revenue mix improving (higher-margin products/segments)?
- Any signs of channel stuffing or pull-forward demand?

### 5. Sector Context
- Is this company outperforming its sector peers?
- Are the tailwinds company-specific or industry-wide?
- If industry-wide, has the market already repriced the sector?

### 6. PEAD Trade Recommendation
Based on ALL the above analysis, provide a specific trading recommendation.

## Output Format (JSON)

Respond with ONLY this JSON structure — no other text:

```json
{{
    "symbol": "{symbol}",
    "analysis_date": "{analysis_date}",
    "surprise_quality_score": <1-5>,
    "surprise_quality_rationale": "<2-3 sentences>",
    "guidance_direction": "<raised|maintained|lowered|not_given>",
    "guidance_notes": "<2-3 sentences>",
    "management_tone": "<confident|neutral|cautious|defensive>",
    "management_tone_notes": "<2-3 sentences>",
    "revenue_quality": "<strong|moderate|weak>",
    "revenue_quality_notes": "<2-3 sentences>",
    "sector_context": "<outperforming|inline|underperforming>",
    "sector_notes": "<1-2 sentences>",
    "recommendation": {{
        "direction": "<long|short|skip>",
        "conviction": <1-5>,
        "entry_price": <target entry or null>,
        "stop_loss": <stop price>,
        "target_price": <target price>,
        "hold_days": <20-60>,
        "position_size_pct": <2-5>,
        "thesis": "<2-3 sentence thesis for the trade>"
    }},
    "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
    "catalyst_timeline": "<when will the next catalyst occur that could accelerate or invalidate the thesis>"
}}
```

## Transcript

{transcript}
"""

# Shorter prompt for in-conversation analysis (no JSON output requirement)
PEAD_QUICK_ANALYSIS_PROMPT = """Analyze this earnings report for PEAD (Post-Earnings Announcement Drift) opportunity:

**{symbol} Q{quarter} {year}** — EPS ${eps_actual} vs ${eps_estimate} ({surprise_pct:+.1f}% surprise)

Score these dimensions:
1. **Surprise Quality (1-5):** Revenue-driven (5) vs one-time items (1)
2. **Guidance:** Raised / maintained / lowered / not given
3. **Management Tone:** Confident / neutral / cautious / defensive
4. **Revenue Quality:** Strong organic growth vs cost-cutting
5. **PEAD Signal:** Long / Short / Skip, with conviction (1-5)

If recommending a trade:
- Entry zone, stop loss (-5% max), target (+8% max), hold period (20-60 days)
- Size: 3-5% of $50K portfolio
- Key thesis in 2-3 sentences
- Top 3 risks
"""


def format_pead_prompt(symbol: str, quarter: int, year: int,
                        eps_actual: float, eps_estimate: float,
                        surprise_pct: float, current_price: float,
                        transcript_text: str) -> str:
    """Format the PEAD scoring prompt with earnings data and transcript."""
    from datetime import datetime
    return PEAD_SCORING_PROMPT.format(
        symbol=symbol,
        quarter=quarter,
        year=year,
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        surprise_pct=surprise_pct,
        current_price=current_price,
        analysis_date=datetime.now().strftime("%Y-%m-%d"),
        transcript=transcript_text,
    )


def format_quick_prompt(symbol: str, quarter: int, year: int,
                         eps_actual: float, eps_estimate: float,
                         surprise_pct: float) -> str:
    """Format the quick analysis prompt for in-conversation use."""
    return PEAD_QUICK_ANALYSIS_PROMPT.format(
        symbol=symbol,
        quarter=quarter,
        year=year,
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        surprise_pct=surprise_pct,
    )
