#!/bin/zsh
# One command for the whole update: collect new reviews -> tag them -> rebuild the dashboard.
# Run by hand:   scripts/run_update.sh
# Run by the Mac scheduler every two days (see README, "Automatic updates").
# Keys come from ~/.zshrc (ANTHROPIC_API_KEY, APIFY_TOKEN); they are never in this file.

cd "$(dirname "$0")/.." || exit 1
source ~/.zshrc
PY=~/.venvs/walking-pad-insights/bin/python
LOG=logs/update.log
mkdir -p logs

{
  echo "=== $(date '+%Y-%m-%d %H:%M') update started"
  $PY src/collect_trustpilot.py --weeks 2 --max-charge 0.15 &&   # hard Apify cap per run
  $PY src/analyze.py --max-cost 0.10 &&                        # hard Claude cap per run
  $PY src/triage_agent.py --limit 10 --max-cost 0.05 &&        # new 1-2★ reviews: cause, owner, draft reply
  $PY src/build_report.py
  rc=$?
  if [ $rc -eq 0 ]; then echo "=== OK"; else echo "=== FAILED (exit $rc)"; fi
} >> "$LOG" 2>&1

# A macOS notification so a failed run is not silently missed.
if grep -q "=== FAILED" <(tail -1 "$LOG"); then
  osascript -e 'display notification "Update failed, see logs/update.log" with title "Walking pad insights"'
else
  osascript -e 'display notification "Dashboard updated" with title "Walking pad insights"'
fi
