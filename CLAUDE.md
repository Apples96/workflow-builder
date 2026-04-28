## Project Overview

Web app for process automation: users describe workflows in natural language, the system generates executable Python code that orchestrates document operations via the LightOn Paradigm API. Anthropic Claude handles code generation and planning.

## Architecture

- **Frontend**: Single-file `index.html` (vanilla JS, no framework)
- **Backend**: FastAPI app in `api/main.py`
- **Workflow pipeline**: `api/workflow/` — planner, cell generator, evaluator, enhancer
  - `api/workflow/cell/` — cell-level code generation, execution, evaluation, combining
  - `api/workflow/core/` — workflow-level enhancer, analyzer, executor, generator
  - `api/workflow/prompts/` — markdown prompt templates (planner.md, cell.md, evaluator.md, etc.)
  - `api/workflow/models.py` — Pydantic models for all workflow data structures
- **Tests**: `tests/` — pytest-based, mostly integration tests against live APIs

## LLM Prompt Files

Prompt templates live in `api/workflow/prompts/*.md`. These are critical to how the system behaves.
- Prompts are loaded by `api/workflow/prompts/loader.py`

## Key Conventions

- **Single-file frontend**: All UI code lives in `index.html`. No build step, no bundler. Keep it that way.
- **Pydantic models**: All API request/response shapes are defined in `api/workflow/models.py` (or `api/models.py`). Always update models when changing API contracts.
- **Cell-based workflows**: The main execution model. A planner breaks workflows into cells, each cell gets independently generated code, executed, and evaluated.
- **Shared context schema**: The `shared_context_schema` dict (variable name → type description) defines data flow between cells. Changes here affect all downstream cell generation.

## Paradigm API Integration

- Backend uses LightOn Paradigm API for document operations
- API key stored as `LIGHTON_API_KEY` environment variable

## Code Generation Requirements

- Generated workflow code must be standalone and contain full Paradigm API documentation
- Cell code follows the signature: `async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]`
- `ParadigmClient` is injected at runtime — generated code must NOT define it

## Development Workflow

- Run backend: `cd api && uvicorn main:app --reload`
- Run tests: `cd tests && pytest`
- Tests require `LIGHTON_API_KEY` to be set (most tests hit live APIs)
- No CI/CD pipeline yet — test locally before pushing

## End-to-End Test: UGAP Workflow

A complete end-to-end test scenario lives in `tests/ugap-test/`. Test via code by hitting the API endpoints directly (upload → create → execute → check results).

**Workflow description**: `tests/ugap-test/ugap-test-workflow.md`
- 11-step document compliance workflow for UGAP public procurement (DC4 sous-traitance)
- Checks 22 controls across document zones A–L: buyer identification, market object, subcontractor identity, IBAN validation, signatures, etc.
- Uses Paradigm `doc_search` for extractions and external API calls (data.gouv.fr entreprises API)

**Input set 1 — "CONFORME MODIFICATIF"** (`tests/ugap-test/CONFORME MODIFICATIF/`):
- `01_DC4_C_001_MODIFICATIF.pdf` — DC4 (modificatif)
- `02_AVIS_APPEL_PUBLIC_CONCURRENCE 21U031.pdf` — Avis d'appel public à la concurrence
- `03_ACTE ENGAGEMENT ATOS.pdf` — Acte d'engagement
- `04_RIB FIGPOM.pdf` — Relevé d'identité bancaire
- `05_DECLARATION DU CANDIDAT ATOS.pdf` — DC2
- `06_DC4_C_001_INITIAL.pdf` — Précédente déclaration de sous-traitance (DC4 initial, document 6)

**Input set 2 — "DC4_C_002"** (`tests/ugap-test/DC4_C_002/`):
- `01_DC4_C_002.pdf` — DC4
- `02_Avis_appel_public_concurrence.pdf` — Avis d'appel public à la concurrence
- `03_ACTE ENGAGEMENT INOPS.pdf` — Acte d'engagement
- `04_RIB INOPS - KEYRIUS.pdf` — Relevé d'identité bancaire
- `05_DECLARATION DU CANDIDAT INOPS.pdf` — DC2

**Expected output**: `tests/ugap-test/output-example/recap_74.pdf`
- Example recap PDF produced by the workflow

**Quick E2E test** (`tests/ugap-test/e2e-test-workflow.md`):
- 3-step workflow description that the planner expands to ~6 cells (mapping, 2 extractions, comparison, API call, report)
- Uses only 2 documents: `DC4_C_002/01_DC4_C_002.pdf` and `DC4_C_002/03_ACTE ENGAGEMENT INOPS.pdf`
- Covers all key patterns: Paradigm search, inter-cell data passing, external HTTP API call, Python computation, pure Python aggregation
- Tested runtime: ~6-7 min total (planning ~35s + execution ~6 min)

**How to run (code-based via API)**: Start the backend (`cd api && uvicorn main:app --reload`), then:
1. Upload each PDF via `POST /api/files/upload` (multipart `file` field) — returns `{"id": <file_id>}`
2. Create workflow via `POST /api/workflows-cell-based` with JSON body: `{"description": "<workflow text>", "context": {"attached_file_ids": [<file_id_1>, <file_id_2>]}}`
3. Execute via `POST /api/workflows/{id}/execute-stream` with JSON body: `{"user_input": "<any prompt>", "attached_file_ids": [<file_id_1>, <file_id_2>], "stream": true}` — returns SSE events
4. Check results via `GET /api/workflows/{id}/plan` — each cell has `status`, `output`, `execution_time`, `error`
5. For full UGAP test: compare generated output against `tests/ugap-test/output-example/recap_74.pdf`

**Note**: The Paradigm API key is read from the server's `.env` (`LIGHTON_API_KEY`) as fallback, or can be passed via `X-Paradigm-Api-Key` header.

## Eval Suite

Automated evaluation harness in `tests/eval/` that runs test workflows against the live backend and checks results with assertions.

**Focused test workflows** (`tests/ugap-test/test-*.md`): 8 short workflows, each testing 1-2 capabilities (extraction, parallel execution, conditional logic, math validation, external API, etc.). Mix of EN and FR. ~3-8 min each.

**How to run evals** (requires backend running on localhost:8000):
```bash
python tests/eval/runner.py                          # Run all 8 tests
python tests/eval/runner.py --filter single-doc      # Run one test by name
python tests/eval/runner.py --tags extraction,en     # Filter by tags
python tests/eval/runner.py --compare a.json b.json  # Compare two runs for regressions
```

**Key files**:
- `tests/eval/manifest.yaml` — test declarations with assertions (add new tests here)
- `tests/eval/runner.py` — orchestrates upload → create → execute → assert cycle
- `tests/eval/assertions.py` — assertion types: `all_cells_completed`, `cell_has_output`, `has_parallel_layer`, `output_matches_pattern`, `total_time_under`, `llm_judge`, etc.
- `tests/eval/reporter.py` — JSON report generation and regression comparison
- `tests/eval/reports/` — saved eval reports (JSON)

**LLM-as-judge evaluation** (`api/workflow/cell/evaluator.py`): Cells are evaluated after execution using Claude tool_use for structured scoring (score 0-1, confidence, per-field scores). Failed evaluations accumulate feedback history across retries. After max retries, cells with score >= 0.6 proceed; below 0.6 are marked failed.

## Common Pitfalls

- `index.html` has duplicate code paths for manual vs auto-execution (e.g., workflow creation text logs appear in two places). When changing UI display logic, check for both instances.
- Bytes literals in Python test files must use ASCII only (no accented characters in `b"..."` strings)
- The frontend stores `currentWorkflowPlan` and `currentCells` as global state — these are set during workflow creation and used throughout execution
