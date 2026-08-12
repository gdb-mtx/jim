# PUBLIC_PLAN.md — Taking FIRE public

> **Decision (2026-08-12, George):** Make this repo public **in place** — same URL, same
> history — under **PolyForm Noncommercial 1.0.0** (same license as FIREMaster). No
> public/private repo split: unlike FIREMaster, there is no business layer here to
> protect (no marketing strategy, no pricing, no scripted answers), the strategies are
> commodity, and the honesty artifacts (HISTORY.md, kill-tests, incident logs,
> validation gates) are the entire point of publishing. The split trigger, if ever:
> real-money content entering the tree at Phase 5 (capital amounts, tax positioning,
> broker structure beyond `.env`).
>
> **Framing:** not a promoted launch. A standing receipt for the "engineer who shows
> the engine" pattern — second public repo alongside FIREMaster. Feeds the newsletter
> (Pillar 1) with the honest essay ("built a trading system with Claude Code; it
> doesn't beat SPY; publishing anyway") and pre-seeds the r/ClaudeAI room and the
> September HN play with checkable history. Repo must be public and *settled* before
> those rooms resume — an established artifact, not a launch prop.
>
> This file itself ships in the public history — it is written accordingly, and it is
> itself a receipt.

## Session recon already done (2026-08-12 — do not re-derive)

- Repo is currently **PRIVATE** (`gh repo view`: fire, gdb-mtx/fire).
- **`.env` was never committed** — no add/delete anywhere in history. Shallow history
  grep for Alpaca keys: clean. A full gitleaks pass is still REQUIRED (step 2).
- **298 tracked files.** Operational state (rebalance logs, snapshots, api_server logs,
  filter/risk state) is already untracked/gitignored — verified.
- **THE blocker: `data/mode2/transcripts/` — 50+ earnings-call transcripts scraped from
  Insider Monkey, tracked and in history.** Republishing them publicly is a copyright
  violation. They must be stripped from ALL history (filter-repo), not just deleted.
- `data/mode2/mode1_filter/scores/*.json` + `transcript_index.json` + PEAD reports are
  tracked — REVIEW: if scores/index embed transcript excerpts beyond fair-use quoting,
  strip them alongside the transcripts.
- `data/validation_reports/*.md` are tracked — paper-account numbers, harmless,
  **keep**: they are receipts.
- `References/Proprietary Quantitative Trading Partnership Proposal.md` — the 2020
  spec. **DECIDED (George, 2026-08-12): keep it** — great artifact ("spec'd 2020,
  built 2026") — **but strip the names of potential collaborators referenced in it.
  Names of people who inspired it stay.** The names appear in prior history too, so
  after editing, filter the file's old versions from history (filter-repo
  `--path <file> --invert-paths` then re-add the cleaned version, or
  `--replace-text` with a names file) in the same rewrite as the transcripts.
- The Ernie Chan books + *Trading in Risk Dimensions* PDFs live in `References/` **on
  disk only** — verified never tracked and absent from all history (no `*.pdf` ever
  added). Now belt-and-suspenders gitignored (`References/*.pdf`) so no future
  `git add -A` can publish them. Step 7's fresh-clone check should confirm the clone
  contains zero PDFs.

## Execution checklist (fresh session)

Order matters: history rewrite happens while the repo is still private.

1. **Back up transcripts, then strip them from history.**
   - `cp -r data/mode2/transcripts /tmp/transcripts_backup` (they stay on disk,
     untracked, so Mode 2 keeps working).
   - `git filter-repo --invert-paths --path data/mode2/transcripts/` (plus scores/index
     if the review in recon says so). NOTE: filter-repo requires a fresh clone or
     `--force`, drops the `origin` remote (re-add it), and rewrites all SHAs.
   - Restore the transcripts dir into the working tree; add
     `data/mode2/transcripts/` to `.gitignore`; commit.
   - Force-push (`git push --force origin main`). Private repo, sole developer — safe.
     Any other checkout of this repo on any machine must be re-cloned.
   - HISTORY/docs reference old commit SHAs (e.g. `9240e2a`, `3acc646`) — they will no
     longer resolve after the rewrite. Acceptable: they date-anchor to HISTORY.md
     entries, which is the canonical record. Do NOT chase/rewrite doc SHAs.

2. **Full-history secrets scan.** `gitleaks git .` (install via brew). Also manual
   sweeps: `git grep` all history for `gdborshukov`, `ALPACA`, `APCA-`, account IDs,
   any `sk-`/`key`-shaped strings. Anything found → filter-repo it out, re-scan until
   clean. Zero findings is the gate for step 6.

3. **License.** Add `LICENSE.md` = PolyForm Noncommercial 1.0.0 (copy the text from
   FIREMaster's public repo for consistency; check how it handled copyright line).

4. **README rewrite for strangers.** Current README is operator-facing. Public README
   needs: what this is (personal quant research system, paper trading, built solo with
   Claude Code); what makes it unusual (the honesty artifacts — validation gates,
   kill-tests, retirement post-mortems, incident logs — link HISTORY.md,
   EVENT_KILLTESTS, DATA_SOURCES.md, VALIDATION.md); what it is NOT (not a product, not
   maintained for others, no support, PRs/issues welcome but response not guaranteed);
   honest performance statement (validated OOS numbers AND the live-vs-SPY lag — do not
   flatter); quickstart for the curious. **Required disclaimer, prominent:** personal
   research, paper trading, not investment advice, no performance claims, past results
   (especially backtests) do not predict anything.

5. **Public-eyes docs pass.** Read with a stranger's eyes; edit lightly, don't
   sanitize the honesty:
   - `CLAUDE.md` — FIREMaster/bridge-plan references are fine at the level already
     public in the newsletter (laid off at 53, bridge to 59.5); trim anything beyond
     that. Absolute paths (`/Users/george/...`) are fine to keep (docs, not secrets).
   - `References/` proposal — apply the decided name-scrub (see recon: collaborators
     out, inspirations stay), history-filtered in step 1's rewrite.
   - `AUTOMATION.md`, `DEPLOYMENT_PLAN.md` — quick skim for anything
     account-identifying (Alpaca account numbers, emails). Cron/TCC/laptop war stories
     STAY — they're the good stuff.
   - `.claude/` — check if tracked; if settings contain anything local, untrack.

6. **George's final read, then flip.** George reviews the diff of steps 3-5 and the
   README. Then: `gh repo edit --visibility public`. Set repo description ("Personal
   quantitative trading research system — momentum/trend factor book, honest
   validation, built with Claude Code") + topics (quantitative-trading, claude-code,
   alpaca, backtesting).

7. **Post-flip verification.** Fresh `git clone` from GitHub:
   `git log --all --oneline -- data/mode2/transcripts/` must be EMPTY; gitleaks the
   fresh clone; confirm LICENSE renders on the repo page; click through README links.

8. **Aftermath (no promotion, per decision).** No posts, no rooms. The two permitted
   surfaces: newsletter essay when George wants it (Pillar 1, "it doesn't beat SPY"
   angle), and passive availability for the r/ClaudeAI / HN rooms whenever the paused
   sequence resumes. Update FIREMasterPrivate/strategy/MARKETING_PLAN.md with a
   one-line "second public repo live" note so the room playbooks know it exists.

## Execution deltas (2026-08-12 session — recorded as receipts)

1. **Scores/index review (step 1):** kept. Rationales embed only fair-use-length
   quotes (max ~15 words); index/urls files contain no transcript content.
2. **References proposal:** contained NO collaborator names in any committed version
   (verified across all history — the recon's memory was of the unpublished 2020
   original). What it DID contain: personal Google Drive links to the Ernie Chan
   book PDFs. Links stripped, old versions filtered from history.
3. **gitleaks:** clean (285 commits). Manual sweep's only hit: the SEC-required
   contact email in EDGAR User-Agent headers — kept (compliance, not a secret).
4. **Recon miss found in step 5:** `docs/archive/BRIDGE_STRATEGY_REVIEW.md` carried
   the full personal financial picture (NW to the dollar, property names, IRA split,
   runway). Filtered from all history; kept on disk untracked. Property names and
   cash-event figures also scrubbed from PLAN_MODE2.md / STRATEGY_CAPSULE.md
   (history `--replace-text`) and CLAUDE.md trimmed to newsletter level.
5. **Force-push does not purge GitHub:** old pre-rewrite commits remained fetchable
   by SHA on github.com (verified live). Fix: recreate the repo fresh — and George
   renamed it in the same move. **Public name: `jim`** (the system never delivered
   FIRE; Jim Simons' system worked). Local directories stay `FIRE`. The travel
   watcher's Actions secrets must be re-created in the new repo.

## Kickoff prompt for the fresh session

> Read PUBLIC_PLAN.md at the repo root and execute it top to bottom. The recon section
> is current as of 2026-08-12 — trust it, don't re-derive. Stop for my input at: the
> scores/index copyright review call (step 1), anything gitleaks finds (step 2), the
> References proposal name-scrub review (step 5 — collaborator names out,
> inspiration names stay; show me the edited version), and the final pre-flip read
> (step 6). The visibility flip itself happens only after my explicit go.

## Open items riding along (not part of this plan, don't lose them)

- **Aug 20 (Wed... Thu):** 21-trading-day rebalance. George resets paper balances to
  70/30 (A1 ≈ $143K / A2 ≈ $61K) in the Alpaca dashboard that MORNING, then normal
  rebalance at ~3 PM ET. New sizing (signal-book scalar, target 0.18) applies
  automatically. A1 revalidated PASS 33.0%; A2 MARGINAL 12.9% (honest, financing
  included) with the Q4 Calmar < 1.0 kill/swap trigger standing.
- Fly.io: parked by George (real money he's not ready to commit).
- Next big open engineering item: none blocking. Platform hardened 2026-08-08..12
  (see DATA_SOURCES.md audit section + HISTORY.md).
