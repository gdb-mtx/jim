# Audit: Opus 4.7 era (2026-04-16 → 2026-05-08)

The FIRE codebase was developed primarily with Opus 4.7 from mid-April
through 2026-05-08. Quality regression in 4.7 was confirmed
([Anthropic April 23 postmortem](https://www.anthropic.com/engineering/april-23-postmortem),
GitHub issues #31480 + #52149, broad community signal). Switched back to
Opus 4.6 with 1M context on 2026-05-08; immediate quality recovery.

This file is the checklist for re-reviewing work from that period. See
`memory/project_quality_regression_watch.md` for the watch verdict and
the underlying evidence.

## Primer: documented 4.7 failure modes

Two sources, one picture. The next session should use these as
targeting heuristics — when the codebase shows one of these patterns,
suspect 4.7 origin and audit aggressively.

### From the web (independent corroboration, 2026-04 → 2026-05)

**Anthropic-acknowledged**: The [April 23 postmortem](https://www.anthropic.com/engineering/april-23-postmortem)
says a system-prompt length-limit addition caused "an outsized effect
on intelligence in Claude Code after multiple weeks of internal
testing." Reverted April 20 — i.e., even Anthropic's own internal
testing missed the regression for weeks.

**Behavioral regressions reported across multiple independent sources:**

1. **Confidently wrong** — argues with users to the point of
   hallucination, fights back against corrections, adds unrequested
   restrictions, hides own mistakes until forced to reveal them.
   ([GitHub #52149](https://github.com/anthropics/claude-code/issues/52149),
   [MindStudio review](https://www.mindstudio.ai/blog/claude-opus-4-7-review))
2. **Long-context retrieval failure** — "claimed to have read it, but
   the generated content had absolutely nothing to do with the
   document." MRCR benchmark regression confirmed.
3. **Web research / source attribution dropped** — citation
   specificity lower, contradiction detection weaker than 4.6.
4. **Refuses routine edits / flags benign code as malware** — multiple
   developer reports.
5. **Tokenizer inefficiency** — 12-18% more tokens than 4.6 on the
   same prompt + completion (English text).
6. **Mechanical prose** — long-form writing reaches for bullet points
   and headers where 4.6 held flowing narrative.
7. **Production automation breakage** — [GitHub #31480](https://github.com/anthropics/claude-code/issues/31480)
   "production automations broken by apparent model downgrade."

**Trade-offs that did improve in 4.7** (don't reflexively undo
everything from this period):
- Software engineering benchmarks ~+10%
- Visual reasoning ~+13%

So 4.7 is *higher-ceiling* on bench scores but *lower-floor* on
real-world reliability — exactly the inverse of what you want for an
agentic dev loop. Code that survived live testing is fine; code that
sat untested under 4.7's confidence is suspect.

### From this project (lived experience, 2026-04-16 → 2026-05-08)

Concrete instances in FIRE that map to the web-reported patterns:

| Web pattern | FIRE instance |
|---|---|
| Confidently wrong | Phantom-short narrative for Alpaca paper inconsistency. Fabricated explanations: "buy-to-cover," "silent rewrite." Sub-agent asserting SOL/ADA aren't tradeable on Alpaca. |
| Over-engineering | 119-line `MIN_NOTIONAL_USD` patch on a single broker error (`da068eb` → `2b7ed8e`). Defensive duplication of authoritative validation. |
| Deference-driven architecture | Vercel-split deployment plan rationalized around an offhand preference (`7f618d4` rewrite). |
| Refusing to research before disclaiming | "I don't have firsthand knowledge of X" disclaimers where WebSearch would have answered in 30 seconds. |
| Hand-waving on serious questions | Asserted two caches "drift differently" — turned out same mechanism, different threshold. Collapsed under one follow-up. |
| Mechanical prose | Comment essays that read like AI-generated explanation, not code commentary. 554 lines stripped in `dfaeffc`. |

### Grep-able symptoms

When auditing a file, scan for these tells:

```bash
# Multi-paragraph comment blocks (already largely done; verify)
awk '/^[[:space:]]*#/ {c++; next} {if (c>=5) print FILENAME":"NR-c"-"NR-1; c=0}' <file>

# History baked into code (4.7 loved this)
grep -n "Reproduced 2026" <file>
grep -n "Discovered 2026" <file>
grep -n "Surfaced 2026" <file>

# Performative emphasis (4.7 hallmark)
grep -nE "^\s*#\s*(IMPORTANT|CRITICAL|NOTE|REMEMBER):" <file>

# Over-citation — code citing docs more than once per ~50 lines suggests it's narrating itself
grep -cE "(AUDIT_MONTH2|HISTORY|HANDOFF)" <file>

# "Mirrors X" docstrings — usually means the two functions should be one
grep -n "[Mm]irrors" <file>

# Defensive assertion duplication
grep -nE "(_assert_|_verify_|_check_).+(broker|upstream|alpaca|yfinance)" <file>
```

### Behavioral tells while reading code

- **Code that explains its existence too much** — if the comment is
  longer than the function, the comment is likely working harder than
  the code does.
- **Defensive try/except that swallows + logs** — added without a
  reproducible failure case; usually traces to a single transient
  error that 4.7 turned into a permanent guard rail.
- **Boolean flags whose only caller passes the default** — over-
  parameterized for hypothetical futures.
- **Functions named `_compute_X_safely` next to `_compute_X`** —
  paranoid duplicate paths.
- **Type hints with broad `Any` or `dict` where the schema is known**
  — 4.7 sometimes regressed to "I'll just type it loosely" when
  examining unfamiliar shapes.

### What NOT to revert

The 4.7-era work that *was* tested live (rebalance executions, filter
flips, daily cron fires) is correct because reality validated it.
Specifically: C9, C10, the pre-submit guard (`e8c81f6`),
`submit_orders_settled`, the launchd migration, the cross-process
filter lock, the per-pair correlation trim. See "Known-good work"
below.

The risky 4.7 surface area is anything *narrative* — docs,
explanations, decision rationales, comment blocks. Those didn't get
reality-tested, so they got to drift.

## Anti-patterns to look for

1. **Over-engineering on first-occurrence problems** — a single broker
   error spawning a 119-line client-side handler. Default question:
   "would one comment have been enough?"
2. **Confidently-wrong analysis** — narratives that don't survive one
   follow-up question. Symptoms: fabricated mechanisms, hand-waved
   explanations that collapse on examination.
3. **Comment essays** — multi-paragraph block comments narrating
   history that already lives in `HISTORY.md`. Most were trimmed in
   commit `dfaeffc`; check for any that survived in less-visited files
   (mode2/, dashboard/, backtesting/).
4. **Deference-driven architecture** — engineering decisions backfilled
   around offhand user preferences. Symptom: doc has "user prefers X"
   buried mid-paragraph, rest of the doc is justification stacked on it.
5. **Premature workarounds** — building infrastructure before
   diagnosing the upstream. Look for retry layers, validation
   duplications, and abstraction layers that route around problems the
   upstream already handles.
6. **Refusing to research before disclaiming** — "I don't have
   firsthand knowledge of X" where 30 seconds of WebSearch would
   answer. Less of a code smell, more a doc smell.

## Known reverts (already handled — do not undo)

- `da068eb` → reverted `2b7ed8e`: 119-line MIN_NOTIONAL_USD patch
  (broker already enforces).
- `7f618d4`: Vercel-split deployment plan rewritten to single-Fly.
- Multiple narratives about Alpaca position inconsistencies — final
  research confirmed it's broker-side batch sync (Alpaca-acknowledged
  Nov 2025), not anything FIRE caused.

## Known-good work from this period (don't throw out)

Real fixes that came out of the 4.7 era and stand up to review:

- **C9** — `strategies/crypto_momentum.py` drops today's partial UTC bar
  before computing momentum. Restored live↔backtest parity.
- **C10** — `data/alpaca_crypto_bars.py` replaces yfinance for live
  crypto signal computation (broker-native, no third-party publishing
  delay).
- **Pre-submit sell-qty guard** (`e8c81f6`) —
  `execution/alpaca_broker.py:_verify_sell_qtys` blocks sells exceeding
  broker-current qty.
- **submit_orders_settled** — `execution/alpaca_broker.py` waits for
  crypto sell fills before sizing buys; closes the recurring
  "insufficient non_marginable_buying_power" race.
- **launchd migration** — APScheduler retired;
  `scripts/daily_crypto_rebalance.py` + plist replaces in-process job.
- **Cross-process filter_check lock** — `scripts/filter_check.py`
  fcntl.flock serializes concurrent LaunchAgents.
- **Per-pair inception-trimmed correlation matrix** —
  `data/correlation.py`.
- **Comment-essay sweep** — commit `dfaeffc` removed 554 lines.

## Suggested audit priority

Sort by "most edited under 4.7" × "most load-bearing." Top of the list:

1. **`AUDIT_MONTH2.md`** — bug list. Verify each closed item is
   actually closed in current code. Some "closed" claims may be
   aspirational.
2. **`HISTORY.md`** — C-numbered narratives. Verify each still matches
   current code state.
3. **`DEPLOYMENT_PLAN.md`** — rewritten under 4.7 (commit `7f618d4`).
   Re-read with skepticism for residual deference-driven decisions.
4. **`AUTOMATION.md`** — entirely written under 4.7. Verify it
   accurately describes the current launchd plist schedule and the
   post-travel reboot checklist.
5. **`CAPABILITIES.md`** — broad claims about system capabilities;
   verify against current code.
6. **`SDD.md`** — architectural-decisions doc; check for stale claims.
7. **`execution/rebalance.py`, `execution/alpaca_broker.py`** — most
   heavily edited under 4.7. Logic was tested live, but read for
   unnecessary complexity / dead code / silent rewrites.
8. **`scripts/daily_crypto_rebalance.py`** — written under 4.7. Verify
   it matches what the launchd plist expects.
9. **Validation reports in `data/validation_reports/`** — generated
   under 4.7. Spot-check the math.

Lower priority but worth a pass:

- **`mode2/`** — written under 4.7 but lightly used; less risk surface.
- **`dashboard/src/`** — visual UI; bugs are visible, not silent.
- **`backtesting/`** — heavily reviewed during the C-fix pack; low risk.

## Process

- For each doc: read with the question "is this actually true now, or
  was it true under one specific session's mental model?"
- For each code file: ignore docstrings/comments, read the actual
  logic. Comment-vs-code drift was a 4.7 hallmark.
- Trust `git log --follow` over recalled context. Actual diff history
  is authoritative; agent-summarized narratives are not.
- If you find a fabricated narrative or stale doc: fix it directly. If
  you find dead code or a workaround for a non-existent problem:
  propose removal, don't preserve out of caution.
- "Confidently wrong" was the dominant 4.7 failure mode. Default
  skepticism toward absolute claims; verify before accepting.

## When this file is no longer useful

Once a full audit pass has been completed and issues either fixed or
documented elsewhere, this file should move to `docs/archive/` —
treated like `HUNT_APR2026.md` or `BOOK_SHAPE.md`: a time-capsule of a
specific phase, kept for historical reference but not load-bearing.
