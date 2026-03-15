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
- **Do NOT modify prompt files without asking first** — even small wording changes can significantly affect generated output
- Prompts are loaded by `api/workflow/prompts/loader.py`

## Key Conventions

- **Single-file frontend**: All UI code lives in `index.html`. No build step, no bundler. Keep it that way.
- **Pydantic models**: All API request/response shapes are defined in `api/workflow/models.py` (or `api/models.py`). Always update models when changing API contracts.
- **Cell-based workflows**: The main execution model. A planner breaks workflows into cells, each cell gets independently generated code, executed, and evaluated.
- **Shared context schema**: The `shared_context_schema` dict (variable name → type description) defines data flow between cells. Changes here affect all downstream cell generation.

## Paradigm API Integration

- Backend uses LightOn Paradigm API for document operations
- Key endpoints used:
  - Docsearch: POST /api/v2/chat/completions (with document search)
  - Document Analysis: POST /api/v2/chat/document-analysis
  - File Upload: POST /api/v2/files
- Collection types for file uploads: `private`, `company`, `workspace`
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

## Common Pitfalls

- `index.html` has duplicate code paths for manual vs auto-execution (e.g., workflow creation text logs appear in two places). When changing UI display logic, check for both instances.
- Bytes literals in Python test files must use ASCII only (no accented characters in `b"..."` strings)
- The frontend stores `currentWorkflowPlan` and `currentCells` as global state — these are set during workflow creation and used throughout execution
