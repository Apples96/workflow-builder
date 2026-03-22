#!/bin/bash
# Post-edit hook: run unit tests and report failures back to Claude.
# Only runs when a .py file was edited.

# Read stdin (hook input JSON)
INPUT=$(cat)

# Extract file path from hook input
FILE=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

# Skip non-Python files
if [[ "$FILE" != *.py ]]; then
  exit 0
fi

# Run unit tests
OUTPUT=$(python3 -m pytest tests/ -m unit -x --tb=short 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  # Tests failed — tell Claude about it via JSON output
  # Escape the output for JSON
  ESCAPED=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
  echo "{\"decision\": \"block\", \"reason\": \"Unit tests failed after editing $FILE\", \"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"additionalContext\": $ESCAPED}}"
  exit 1
fi

exit 0
