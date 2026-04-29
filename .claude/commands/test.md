---
description: Pre-MR test gate — runs the full local check suite before pushing
argument-hint: [tags] (optional comma-separated eval tags, e.g. "extraction,fr")
---

# /test — Tier 3: Pre-MR verification

You are running the pre-MR test gate. This sits between the per-edit hook (already passing if we got here) and the MR review tier. The goal: catch anything that needs the full suite before the user pushes.

## What to run, in order

Run these as a sequence, stopping at the first failure and reporting back. Do **not** parallelize — failures earlier in the chain make later ones meaningless.

### 1. Diff scope (always)
```
git diff --name-only main...HEAD
git status --short
```
Report what changed: backend (`api/`), frontend (`index.html`), tests, prompts, or config. This determines which evals to run later.

### 2. Full lint + type checks (always, ~5s)
```
ruff check api/ tests/
```
If this fails, stop and surface the diagnostics. The PostToolUse hook should have caught most of these — anything new here means an Edit was bypassed (e.g. via Bash heredoc).

### 3. Full unit suite (always, ~5s)
```
python3 -m pytest tests/ -m unit --tb=short
```
60 tests, no network. Stop on failure.

### 4. Backend smoke (always, ~3s)
```
python3 -c "from api.main import app; print('app routes:', len(app.routes))"
```
Catches import errors, top-level exceptions, missing modules — the most common "looks done but is broken" class of bug.

### 5. Frontend smoke if `index.html` changed (~2s)
```
python3 -c "from html.parser import HTMLParser; HTMLParser().feed(open('index.html').read()); print('html parses ok')"
python3 -m pytest tests/test_smoke_frontend.py -v
```

### 6. Eval suite — diff-aware selection
Decide which evals to run based on what changed:

- **Only `index.html` or docs changed**: skip evals entirely. Report "no eval coverage needed."
- **Backend code changed (`api/`)**: run a representative subset — pick 2-3 tests covering different patterns:
  ```
  python3 tests/eval/runner.py --filter single-doc-extraction
  python3 tests/eval/runner.py --filter cross-doc-comparison
  ```
- **Prompt files changed (`api/workflow/prompts/*.md`)**: run all evals — prompt changes have wide blast radius:
  ```
  python3 tests/eval/runner.py
  ```
- **User passed `$ARGUMENTS` (tags)**: filter by those tags:
  ```
  python3 tests/eval/runner.py --tags $ARGUMENTS
  ```

Each eval test takes 3-8 min. Tell the user the estimated wall time before starting and ask them to confirm if it's >10 min total.

**Backend must be running** on `localhost:8000` for evals. Check with `curl -s localhost:8000/health` first; if down, tell the user to start it (`cd api && uvicorn main:app --reload`) and stop.

### 7. Final report
After all selected checks pass, post a one-block summary:
- ✓ what ran (lint, unit, smoke, evals selected)
- timings
- any warnings worth flagging
- recommendation: "ready to push" or "blockers: ..."

## Argument handling
- `$ARGUMENTS` empty → use diff-aware selection (default)
- `$ARGUMENTS` is a comma-separated list (e.g. `extraction,fr`) → pass as `--tags`
- `$ARGUMENTS` is `quick` → skip evals entirely (lint + unit + smoke only)
- `$ARGUMENTS` is `full` → run all evals regardless of diff
