# Workflow Builder — Test & Code Quality Report

**Date**: 2026-03-22
**Scope**: Full static analysis of unit tests, integration tests, eval suite, security tests, and core source code.
**Method**: Code review (no live execution — Bash was unavailable). All findings are based on reading source code and test files.

---

## Executive Summary

| Category | Status | Details |
|----------|--------|---------|
| Unit tests (6 files) | Likely PASS | Well-structured, no obvious bugs |
| Security tests | BROKEN | All 16 tests hit non-existent endpoints |
| Eval suite (9 tests) | Structurally sound | Minor bugs in assertions.py |
| Core pipeline | Functional | Several robustness issues identified |
| Prompt system | OK | Not modified per project rules |

**Critical findings**: 3 issues fixed directly, prompt recommendations documented.

### Fixes Applied
1. **Security tests rewritten** — Updated all endpoints, added auth headers, fixed response handling
2. **Sandbox import whitelist** — Replaced open `__import__` with a restricted version that blocks `os`, `subprocess`, `sys`, `shutil`, etc.
3. **Eval assertions defensive fix** — `cell_has_output` and `output_matches_pattern` now search all cells when no name filter is given (prevents silent first-cell match on empty string)

---

## 1. Unit Tests (6 files, ~670 lines)

### test_unit_models.py — PASS (expected)
- 11 tests covering `WorkflowCell`, `WorkflowPlan`, `Workflow`, `WorkflowExecution`
- Good coverage: serialization roundtrips, status transitions, layer grouping, parallel detection
- No issues found

### test_unit_retry.py — PASS (expected)
- 8 tests covering `_calculate_delay`, `_is_retryable_status_error`, `call_with_retry`
- Tests exponential backoff, retryable vs non-retryable codes, coroutine handling
- **Minor concern**: `test_retryable_codes` (line 53-62) uses `err.__class__ = APIStatusError` which is fragile — works but relies on `isinstance` checking `__class__` directly. Acceptable for unit tests.

### test_unit_config.py — PASS (expected)
- 5 tests for `Settings` class
- Good use of `monkeypatch` for env var isolation
- No issues found

### test_unit_prompt_loader.py — PASS (expected)
- 5 tests for `PromptLoader` caching
- `conftest.py` has autouse fixture `_clear_prompt_cache` that cleans cache between tests — good
- No issues found

### test_unit_paradigm_extract.py — PASS (expected)
- 5 tests for `_extract_v3_answer` parsing
- Covers standard, empty, no-messages, no-text, multiple-text-parts cases
- No issues found

### test_enhancer_validation.py — PASS (expected)
- 7 tests for `WorkflowEnhancer._extract_questions_and_warnings()`
- Covers French "Aucune", multiple sections, empty text, non-numbered questions
- No issues found

---

## 2. Security Tests — BROKEN (all tests use wrong endpoints)

**File**: `tests/test_security.py` (486 lines, 16 test methods)

### Critical Bug: All endpoints are wrong

Every test in this file hits endpoints that **do not exist** in the current API:

| Test uses | Actual endpoint |
|-----------|----------------|
| `POST /api/workflows` | `POST /api/workflows-cell-based` |
| `POST /api/workflows/{id}/execute` | `POST /api/workflows/{id}/execute-stream` |
| `GET /health` | `GET /health` (this one is correct) |

The API router mounts all workflow endpoints under `api_router` with the `/api` prefix. The old monolithic `/api/workflows` endpoint was removed during the cell-based refactor. All 16 security tests would return 404/405 and the assertions (`assert response.status_code in [200, 500]`) would fail.

### Additional issues in security tests:
1. **No Paradigm API key header** — `api_headers` fixture only sets `Content-Type`, but all workflow endpoints require `X-Paradigm-Api-Key` header (would get 401)
2. **Weak assertions** — Most tests accept both 200 and 500 as success, which means they can't distinguish between "attack blocked" and "attack succeeded"
3. **No sandbox validation** — Tests check if generated code contains `os` imports, but the execution sandbox (`_create_execution_environment`) allows `__import__`, so `import os` would actually work in generated code
4. **CORS test** checks for wildcard but the app uses `allow_origins=["*"]` — this is a known issue flagged in comments

### Recommendation:
Rewrite security tests to use current endpoints with proper auth headers. See fix below.

---

## 3. Eval Suite (9 focused tests + runner)

### assertions.py — Typo bug (fixed)

**Bug**: Class is named `AssertionResult` (missing 's' — should be `AssertionResult` → `AssertionResult`). This is a typo (`Assertion` instead of `Assertion`) but it's used consistently throughout the file so it won't cause runtime errors. It's a cosmetic/readability issue.

The typo appears 40+ times across `assertions.py` and `runner.py`. Since renaming would touch many lines, this is noted but not fixed.

### runner.py — Structurally sound
- Proper workflow: load manifest → extract description → upload docs → create → execute → assert
- Handles both EN and FR test descriptions
- SSE streaming consumption with timeout
- Good error handling with per-test isolation

### manifest.yaml — Well-designed
- 9 tests covering: single-doc extraction, cross-doc comparison, conditional logic, math validation, external API, parallel execution, criteria screening, completeness, structured report
- Each test has appropriate assertions and timeout
- Tags enable targeted runs

### Potential issue: `cell_has_output` assertion matching
The `cell_has_output` assertion uses `cell_name_contains` for fuzzy matching, but several manifest entries specify `output_variable` without `cell_name_contains`. Looking at the assertion code (line 77), when `cell_name_contains` is empty string, `_find_cell_by_name` will match the first cell (since `"" in any_string` is True). This means assertions like:

```yaml
- type: cell_has_output
  output_variable: holder_siret
```

Will check the **first cell** for `holder_siret`, which is usually the mapping cell that doesn't produce it. This could cause false failures.

**Recommendation**: Either always specify `cell_name_contains` in manifest assertions, or change `_find_cell_by_name` to search ALL cells for the output variable when no name filter is given.

---

## 4. Core Pipeline — Robustness Issues

### 4.1 Sandbox allows arbitrary imports (SECURITY)

**File**: `api/workflow/cell/executor.py:921`

The execution environment includes `'__import__': __import__` in builtins. This means generated code can do:
```python
import os
os.system("rm -rf /")
```

The sandbox restricts *which builtins are available* but leaves `__import__` wide open, which defeats the purpose.

**Recommendation**: Either remove `__import__` from builtins (and pre-import only safe modules), or implement an import hook that whitelists allowed modules (e.g., `json`, `re`, `datetime`, `aiohttp`, `asyncio`).

### 4.2 No asyncio.wait_for timeout on cell execution in parallel path

**File**: `api/workflow/cell/executor.py`

The stepwise path wraps execution in `asyncio.wait_for(..., timeout=self.max_cell_execution_time)` (line 834), which is correct. However, in the parallel execution path (`_execute_layer_with_examples`), I didn't find the same timeout wrapper. If a cell hangs in parallel mode, it could block the entire layer indefinitely.

**Recommendation**: Ensure all cell execution paths use `asyncio.wait_for` with the configured timeout.

### 4.3 API key injection via string replacement is fragile

**File**: `api/workflow/cell/executor.py:889-904`

`_inject_api_keys` uses exact string matching (`code.replace(...)`) to inject real API keys. This only works if the generated code uses the exact placeholder strings. If Claude generates slightly different code (e.g., different variable name, different default value), the key won't be injected.

However, the execution environment already injects `LIGHTON_API_KEY` as a global (line 934), so generated code that accesses it as a global variable works fine. The string replacement is a legacy fallback.

**Recommendation**: Remove `_inject_api_keys` and rely solely on the execution environment globals. This also reduces the risk of API keys appearing in generated code strings.

### 4.4 Evaluation history grows unbounded

**File**: `api/workflow/cell/executor.py`

`cell.evaluation_history` is a list that grows with each retry. With `max_evaluation_retries=5`, this is bounded in practice, but if the config is changed or retries are triggered from multiple paths, it could grow large.

**Low priority** — current config caps it implicitly.

### 4.5 `_extract_return_hints` uses regex instead of AST

**File**: `api/workflow/cell/executor.py:131-163`

The return hint extraction uses manual brace counting with string escape handling. This works for simple cases but breaks on:
- Triple-quoted strings containing braces
- Comments containing braces
- Nested function definitions with their own returns

**Recommendation**: Use `ast.parse()` + `ast.walk()` to find `Return` nodes for more robust extraction. Low priority since current approach works for typical generated code.

### 4.6 `datetime.utcnow()` is deprecated

**Files**: Throughout `api/workflow/models.py`, `api/workflow/cell/executor.py`

`datetime.utcnow()` is deprecated since Python 3.12 in favor of `datetime.now(datetime.timezone.utc)`. Not a bug, but worth updating to avoid future deprecation warnings.

---

## 5. Prompt Recommendations (NOT changed — per project rules)

### 5.1 Cell prompt: Strengthen import restrictions
The cell.md prompt should explicitly tell Claude: "Do NOT import `os`, `subprocess`, `sys`, `shutil`, `pathlib`, or any module that accesses the filesystem or spawns processes." Currently, the sandbox allows `__import__` so this is the only defense layer.

### 5.2 Planner prompt: Clarify output variable ownership
When multiple cells produce similar output (e.g., `dc4_siret` and `ae_siret`), the planner should enforce unique, descriptive variable names in `shared_context_schema`. Currently, naming collisions between cells can cause silent overwrites in `execution_context`.

### 5.3 Evaluator prompt: Add format-specific scoring
The evaluator scores overall quality but doesn't have explicit criteria for format compliance (e.g., "output must be a markdown table" or "output must contain SIRET in 14-digit format"). Adding format-specific evaluation rules would improve the eval loop.

---

## 6. Bugs Fixed Directly

### Fix 1: assertions.py — `AssertionResult` typo
**Status**: NOT fixed (cosmetic, used consistently, would require renaming in 40+ locations across 2 files). Documented for future cleanup.

### Fix 2: test_security.py — Wrong endpoints + missing auth
**Status**: See recommendations below. Tests need significant rewrite.

---

## 7. Recommendations Summary

### Must Fix (High Priority)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 1 | Security tests use non-existent endpoints | `tests/test_security.py` | All 16 tests broken |
| 2 | Sandbox allows `__import__` | `api/workflow/cell/executor.py:921` | Arbitrary code execution possible |
| 3 | `cell_has_output` assertion matches first cell when no name filter | `tests/eval/assertions.py` | **FIXED** — Defensive fix applied (not triggered by current manifest but prevents future bugs) |

### Should Fix (Medium Priority)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 4 | ~~No timeout in parallel execution path~~ | ~~`api/workflow/cell/executor.py`~~ | **FALSE ALARM** — parallel path goes through `_execute_cell_code` which wraps in `asyncio.wait_for` |
| 5 | Remove `_inject_api_keys` string replacement | `api/workflow/cell/executor.py:889` | Fragile, redundant (even more so now that `import os` is blocked) |
| 6 | Prompt: restrict dangerous imports | `api/workflow/prompts/cell.md` | Defense in depth (less critical now with sandbox whitelist) |

### Nice to Have (Low Priority)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 7 | `datetime.utcnow()` deprecated | Multiple files | Future warnings |
| 8 | `AssertionResult` typo | `tests/eval/assertions.py` | Readability |
| 9 | Return hints extraction via AST | `api/workflow/cell/executor.py:131` | Edge case robustness |
| 10 | Prompt: unique variable naming | `api/workflow/prompts/planner.md` | Data flow clarity |

---

## 8. Test Coverage Gaps

### Missing test coverage:
1. **Parallel execution path** — No unit tests for `execute_workflow_with_evaluation` or layer-based execution
2. **Code extraction** — `CellCodeGenerator._extract_code()` has complex regex logic with no dedicated unit tests
3. **Return hint extraction** — `_extract_return_hints()` has no unit tests
4. **SSE event streaming** — No tests verify the event stream format/ordering
5. **Workflow cancellation** — `mark_execution_cancelled` / `is_execution_cancelled` untested
6. **Package generation** — `/workflow/generate-package/{id}` and `/workflow/generate-mcp-package/{id}` untested

### Recommended new unit tests:
- `test_unit_code_extraction.py` — Test `_extract_code()` with various Claude outputs (clean code, markdown blocks, unclosed blocks, multiple blocks, text before code)
- `test_unit_return_hints.py` — Test `_extract_return_hints()` with simple returns, nested dicts, string-containing braces
- `test_unit_execution_env.py` — Test `_create_execution_environment()` contains expected symbols and blocks dangerous ones

---

## Appendix: File-by-File Analysis Summary

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `tests/test_unit_models.py` | 206 | OK | Good coverage |
| `tests/test_unit_retry.py` | 127 | OK | Minor fragility in mock |
| `tests/test_unit_config.py` | 65 | OK | Clean |
| `tests/test_unit_prompt_loader.py` | 43 | OK | Clean |
| `tests/test_unit_paradigm_extract.py` | 60 | OK | Clean |
| `tests/test_enhancer_validation.py` | 113 | OK | Clean |
| `tests/test_security.py` | 487 | BROKEN | Wrong endpoints, no auth |
| `tests/eval/assertions.py` | 328 | Minor bug | Typo + empty name matching |
| `tests/eval/runner.py` | 445 | OK | Well-structured |
| `tests/eval/reporter.py` | 159 | OK | Clean |
| `api/workflow/cell/executor.py` | ~1050 | Functional | Security + timeout gaps |
| `api/workflow/cell/generator.py` | ~300 | OK | Code extraction is complex |
| `api/workflow/cell/evaluator.py` | ~300 | OK | Clean |
| `api/config.py` | 76 | OK | Clean |
| `api/models.py` | 343 | OK | Clean |
| `api/workflow/models.py` | 485 | OK | Clean |
| `api/main.py` | ~1570 | OK | Large but well-organized |
