---
description: Multi-agent MR review — eval regression + security + code review in parallel
argument-hint: [base-branch] (optional, defaults to main)
---

# /review-mr — Tier 4: Pre-merge review

You are running the full pre-merge review for the current branch. This is the most expensive tier — multiple parallel agents, full eval suite, ~10-20 min wall time, real API tokens. Only run before merging to `main`.

## Prerequisites
- Backend running on `localhost:8000` (needed for the eval regression run).
- Branch is up-to-date with `$ARGUMENTS` (default: `main`).
- `pr-review-toolkit` plugin installed (otherwise fall back to `/code-review`).

## What to do

### 1. Set up the diff context (sequential, fast)
```
BASE=${ARGUMENTS:-main}
git fetch origin $BASE
git diff $BASE...HEAD --stat
git log $BASE..HEAD --oneline
```
Show the user what's about to be reviewed. If the diff is empty, stop.

### 2. Run all four reviewers in PARALLEL (use Agent tool, one message, multiple Agent calls)

Launch these as concurrent forks (no `subagent_type`, since they share context). Each goes to a different output file — do not read those files directly; wait for the completion notifications.

**Agent A — eval regression check:**
- Find the most recent baseline report in `tests/eval/reports/` from the base branch.
- Run `python3 tests/eval/runner.py` to produce a current report.
- Run `python3 tests/eval/runner.py --compare <baseline>.json <current>.json`.
- Report: any tests that newly fail, any timing regressions >50%, any score drops.

**Agent B — security review:**
- Invoke the `/security-review` skill on the current branch diff.
- Pay extra attention to: API key handling (`LIGHTON_API_KEY`, `ANTHROPIC_API_KEY`), generated code execution paths, file upload validation, CORS config, prompt injection vectors in user-supplied workflow descriptions.

**Agent C — code review:**
- If `pr-review-toolkit` is installed, invoke `/pr-review-toolkit:review-pr`.
- Otherwise fall back to `/code-review`.
- Focus areas: CLAUDE.md compliance, Pydantic model contract changes, prompt-file edits.

**Agent D — prompt-impact analyzer:**
- If files in `api/workflow/prompts/` changed: read each changed prompt, summarize what behavior shifts, and flag any consumer code (cells, planner, evaluator) that may need updating.
- If no prompt files changed, report "n/a" and exit.

### 3. Synthesize (sequential, after all four return)
Once all four agents return, write a consolidated report with:

- **Blockers** (must fix before merge): security findings, eval regressions, breaking model changes
- **Concerns** (should review): style issues, prompt drift, untested code paths
- **Notes** (informational): timing changes, refactoring observations
- **Verdict**: "ready to merge", "needs changes", or "blocked"

Format as markdown. Include direct quotes from the agents for findings.

### 4. Optional: post to MR
Only if the user explicitly asks ("post the review", "comment on the MR"), use `gh pr comment` to post the synthesized report. Never post automatically — review output may contain sensitive info or false positives.

## Notes
- This command costs real money (Claude API tokens × 4 agents + Paradigm API calls for evals). Tell the user the rough cost estimate before launching.
- If any pre-flight check fails (backend down, missing baseline, dirty tree), stop and report — don't try to recover automatically.
