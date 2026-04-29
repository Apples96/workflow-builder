#!/bin/bash
# Tier 2 — Stop hook: full verification before Claude marks work complete.
# Runs ruff on the whole codebase, an import smoke test, and the unit suite.
# Returns "block" with the failures so Claude loops back to fix.

# Skip if Stop hook is being triggered recursively (avoid infinite loops).
INPUT=$(cat)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active', False))" 2>/dev/null)
if [ "$STOP_HOOK_ACTIVE" = "True" ]; then
  exit 0
fi

FAILURES=""

# Check 1: ruff on the whole codebase (api/ + tests/). Fast.
RUFF_OUT=$(ruff check api/ tests/ 2>&1)
if [ $? -ne 0 ]; then
  FAILURES="${FAILURES}=== ruff failures ===\n${RUFF_OUT}\n\n"
fi

# Check 2: import smoke — does the FastAPI app still load cleanly?
IMPORT_OUT=$(python3 -c "from api.main import app; print('OK')" 2>&1)
if [ $? -ne 0 ] || [[ "$IMPORT_OUT" != *"OK"* ]]; then
  FAILURES="${FAILURES}=== import smoke failed (api.main:app) ===\n${IMPORT_OUT}\n\n"
fi

# Check 3: full unit test suite.
TEST_OUT=$(python3 -m pytest tests/ -m unit --tb=short -q 2>&1)
if [ $? -ne 0 ]; then
  FAILURES="${FAILURES}=== unit tests failed ===\n${TEST_OUT}\n\n"
fi

if [ -n "$FAILURES" ]; then
  ESCAPED=$(printf "%b" "$FAILURES" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
  echo "{\"decision\": \"block\", \"reason\": \"Pre-completion checks failed. Fix the issues below before stopping.\", \"hookSpecificOutput\": {\"hookEventName\": \"Stop\", \"additionalContext\": $ESCAPED}}"
  exit 1
fi

exit 0
