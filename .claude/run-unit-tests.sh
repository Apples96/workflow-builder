#!/bin/bash
# Tier 1 — PostToolUse hook: lint + unit tests on Python edits.
# Skips non-Python files. Reports failures back to Claude so it loops back to fix.

INPUT=$(cat)

FILE=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ "$FILE" != *.py ]]; then
  exit 0
fi

# Step 1: ruff check on the specific file (fast — sub-second).
RUFF_OUTPUT=$(ruff check "$FILE" 2>&1)
RUFF_EXIT=$?

if [ $RUFF_EXIT -ne 0 ]; then
  ESCAPED=$(echo "$RUFF_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
  echo "{\"decision\": \"block\", \"reason\": \"ruff lint failed on $FILE — fix the issues below before continuing.\", \"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"additionalContext\": $ESCAPED}}"
  exit 1
fi

# Step 2: unit tests (fast — < 5s, no network).
TEST_OUTPUT=$(python3 -m pytest tests/ -m unit -x --tb=short 2>&1)
TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
  ESCAPED=$(echo "$TEST_OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
  echo "{\"decision\": \"block\", \"reason\": \"Unit tests failed after editing $FILE\", \"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"additionalContext\": $ESCAPED}}"
  exit 1
fi

exit 0
