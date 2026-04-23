#!/usr/bin/env bash
# Pre-travel: refresh filter_watch_thresholds.json from today's live filter
# state, commit, and push. The GitHub Actions watcher then alerts on
# crossings against fresh MAs while the laptop is offline.
#
# Usage: scripts/travel_prep.sh
# Requires: clean working tree on `main` (refuses otherwise — explicit > clever).

set -euo pipefail

cd "$(dirname "$0")/.."

# --- Safety: clean tree on main ---
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "ERROR: not on main (current: $branch). Switch to main first." >&2
  exit 1
fi

# Allow only the threshold file itself to be dirty (we'll rewrite it anyway).
dirty="$(git status --porcelain | grep -v 'scripts/filter_watch_thresholds.json' || true)"
if [[ -n "$dirty" ]]; then
  echo "ERROR: working tree has unrelated uncommitted changes:" >&2
  echo "$dirty" >&2
  echo "Commit or stash them first." >&2
  exit 1
fi

# --- Refresh thresholds from data/risk_state/filter_state.json ---
python3 <<'PY'
import json
src = json.load(open("data/risk_state/filter_state.json"))
dst_path = "scripts/filter_watch_thresholds.json"
dst = json.load(open(dst_path))
dst["btc_125_ma"] = src["btc_ma125"]
dst["spy_200_ma"] = src["spy_ma200"]
json.dump(dst, open(dst_path, "w"), indent=2)
print(f"  btc_125_ma -> {dst['btc_125_ma']}")
print(f"  spy_200_ma -> {dst['spy_200_ma']}")
PY

# --- Show diff for awareness, then commit + push ---
echo
echo "=== diff ==="
git --no-pager diff scripts/filter_watch_thresholds.json || true
echo

if git diff --quiet scripts/filter_watch_thresholds.json; then
  echo "Thresholds unchanged from current values; nothing to commit."
  exit 0
fi

git add scripts/filter_watch_thresholds.json
git commit -m "travel prep: refresh filter thresholds"
git push origin main
echo
echo "Done. Watcher will use the new thresholds on its next run (within 30 min)."
