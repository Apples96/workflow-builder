# Handover Document - LightOn Workflow Builder Internship

**Intern**: Nathanaëlle
**Period**: November 3, 2024 - December 31, 2024 (8 weeks)
**Project**: LightOn Workflow Builder
**Version**: 1.1.0-mcp

---

## 📋 Table of Contents

1. [Project Overview](#1-project-overview)
2. [Main Achievements](#2-main-achievements)
3. [Detailed Technical Architecture](#3-detailed-technical-architecture)
4. [Components and Features](#4-components-and-features)
5. [Exportable Packages](#5-exportable-packages)
6. [Tests and Quality](#6-tests-and-quality)
7. [Deployment and Infrastructure](#7-deployment-and-infrastructure)
8. [Documentation](#8-documentation)
9. [Current State and Limitations](#9-current-state-and-limitations)
10. [Known Bugs](#10-known-bugs)
11. [Improvement Proposals](#11-improvement-proposals)
12. [Security](#12-security)
13. [References and Resources](#13-references-and-resources)

---

## 1. Project Overview

### 1.1 Description

The **LightOn Workflow Builder** is a web application that enables the creation and execution of automated document analysis workflows. The system generates executable Python code from natural language descriptions, using Anthropic's Claude Sonnet 4 AI and LightOn's Paradigm API for document processing.

### 1.2 Project Objectives

- **No-Code Automation**: Enable non-technical users to create complex workflows
- **AI Code Generation**: Use Claude Sonnet 4 to translate natural language into Python code
- **Paradigm Integration**: Leverage all Paradigm API capabilities (11 endpoints)
- **Standalone Export**: Generate independently deployable packages
- **Claude Desktop Integration**: Via MCP (Model Context Protocol)

### 1.3 Main Technologies

**Backend**:
- Python 3.11+
- FastAPI (REST API server)
- Anthropic Claude Sonnet 4 (claude-sonnet-4-20250514)
- LightOn Paradigm API (11 endpoints)
- Upstash Redis / Vercel KV (persistence)

**Frontend**:
- Vanilla JavaScript (no framework)
- HTML5 / CSS3
- jsPDF (client-side PDF generation)

**Packages**:
- Docker / Docker Compose
- Python packaging (pyproject.toml)
- MCP Protocol (Anthropic)

### 1.4 Internship Statistics

- **245 commits** since November 3, 2024
- **97 tests** covering 11/11 Paradigm endpoints
- **3393 lines** of code in generator.py
- **~2900 lines** of system prompts (81% of generator.py)
- **2 exportable packages** created (Workflow Runner, MCP Server)
- **Complete bilingual documentation** (FR/EN)

---

## 2. Main Achievements

### 2.1 Development Timeline

#### Phase 1: Foundations (Nov 2024)
- ✅ **FastAPI Backend**: Basic workflow endpoints
- ✅ **Claude API Integration**: Python code generation
- ✅ **Paradigm API Integration**: document_search, analyze_documents
- ✅ **Web Interface**: Vanilla JS frontend
- ✅ **Vercel Deployment**: Serverless configuration

#### Phase 2: Robustness (Dec 2024)
- ✅ **Retry Mechanism**: Up to 3 attempts with error feedback
- ✅ **Description Enhancement**: Automatic user description improvement
- ✅ **Post-Processing**: Automatic f-string error correction
- ✅ **Parallelization**: Automatic asyncio.gather() detection and implementation
- ✅ **Rate Limiting**: Paradigm API limits management (pauses between uploads)
- ✅ **Validation**: Python compilation and error detection

#### Phase 3: Advanced Features (Dec 2024)
- ✅ **PDF Generation**: Professional reports with ReportLab
- ✅ **File Upload Support**: Complete file lifecycle management
- ✅ **Structured Extraction**: guided_choice, guided_regex, guided_json
- ✅ **Vision Fallback**: VisionDocumentSearch for scanned documents
- ✅ **Performance**: Reusable HTTP session (5.55x faster)
- ✅ **Complex Workflow Detection**: Detection of workflows >40 API calls

#### Phase 4: Packages and Export (Jan 2025)
- ✅ **Workflow Runner Package**: Standalone application with auto-generated UI
- ✅ **MCP Server Package**: Claude Desktop + Paradigm integration
- ✅ **Workflow Analyzer**: Automatic Claude analysis for UI generation
- ✅ **HTTP MCP Server**: Dual-mode support (stdio + HTTP)
- ✅ **Bilingual Documentation**: All READMEs in FR/EN

#### Phase 5: Tests and Documentation (Jan 2025)
- ✅ **Complete Test Suite**: 97 tests covering 11/11 Paradigm endpoints
- ✅ **Makefile**: Development task automation
- ✅ **Technical Analysis**: Detailed documentation of generator.py (1167 lines)
- ✅ **Compliance Analysis**: Security and architecture audit
- ✅ **Bilingual READMEs**: FR/EN documentation for all components

### 2.2 Implemented Features

#### Workflow Generation
- **Natural Language to Code**: Automatic descriptions → Python translation
- **Description Enhancement**: Improvement with Claude before generation
- **Auto-Validation**: Retry up to 3 times with error feedback
- **Post-Processing**: Automatic f-string syntax correction
- **Complexity Detection**: Identification of workflows >40 API calls
- **Parallelization**: Automatic asyncio.gather() for independent operations

#### Paradigm API Integration (11/11 endpoints)
1. `document_search` - Semantic search
2. `analyze_documents_with_polling` - In-depth analysis
3. `chat_completion` - Completion with structured extraction
4. `upload_file` - Upload with auto-indexing
5. `get_file` - File information retrieval
6. `delete_file` - File deletion
7. `wait_for_embedding` - Indexing wait (300s timeout)
8. `get_file_chunks` - Chunk retrieval
9. `filter_chunks` - Relevance filtering
10. `query` - Chunk extraction without AI synthesis
11. `analyze_image` - Image analysis

#### Structured Data Extraction
- **guided_choice**: Forced selection from predefined list
- **guided_regex**: Guaranteed format (SIRET, IBAN, phone, dates, amounts)
- **guided_json**: JSON extraction with schema
- **Predefined patterns**: 14-digit SIRET, 9-digit SIREN, IBAN, etc.

#### Export and Packages
- **Workflow Runner Package**: Complete standalone application
- **MCP Server Package**: Claude Desktop integration
- **PDF Generation**: Vendor-neutral professional reports
- **UI Auto-Configuration**: Claude code analysis for UI generation

---

## 3. Detailed Technical Architecture

### 3.1 Project Structure

```
scaffold-ai-test2/
├── api/                                # FastAPI Backend
│   ├── main.py                        # API entry point (1005 lines)
│   ├── config.py                      # Environment configuration
│   ├── models.py                      # Pydantic models
│   ├── api_clients.py                 # API clients (Anthropic, Paradigm)
│   ├── paradigm_client_standalone.py  # Paradigm client for packages
│   ├── pdf_generator.py               # ReportLab PDF generation
│   └── workflow/
│       ├── generator.py               # Workflow generator (3393 lines)
│       ├── executor.py                # Workflow executor
│       ├── models.py                  # Workflow models
│       ├── package_generator.py       # Workflow Runner generator (245 lines)
│       ├── mcp_package_generator.py   # MCP Server generator (586 lines)
│       ├── workflow_analyzer.py       # Claude analyzer for UI (239 lines)
│       └── templates/
│           ├── workflow_runner/       # Workflow Runner templates
│           │   ├── backend_main.py
│           │   ├── frontend_index.html
│           │   ├── Dockerfile
│           │   ├── docker-compose.yml
│           │   ├── requirements.txt
│           │   ├── README.md (FR)
│           │   └── README_EN.md
│           └── mcp_server/            # MCP Server templates
│               ├── server.py          # MCP stdio for Claude Desktop
│               ├── http_server.py     # MCP HTTP for Paradigm
│               ├── pyproject.toml
│               ├── README.md (FR)
│               └── README_EN.md
├── frontend/
│   └── index.html                     # Web interface (1500+ lines)
├── tests/                             # Complete test suite
│   ├── test_paradigm_api.py          # 26 Paradigm tests
│   ├── test_workflow_api.py          # 15 workflow tests
│   ├── test_files_api.py             # 18 file tests
│   ├── test_integration.py           # 12 end-to-end tests
│   ├── test_security.py              # 16 security tests
│   ├── Makefile                      # Test automation
│   ├── README.md (FR)
│   └── README_EN.md
├── docs/
│   ├── ANALYSE_GENERATOR.md          # Technical analysis generator.py (1167 lines)
│   ├── ANALYSE_GENERATOR_EN.md       # English version
│   ├── analyse-conformite-architecture.md  # Security audit
│   ├── workflow-builder-schema.html  # Interactive architecture schema
│   └── extraction_improvements_analysis.md
├── docker-compose.yml                # Docker configuration
├── Dockerfile                        # Backend Docker image
├── vercel.json                       # Vercel configuration
├── .env.example                      # Environment template
├── README.md (FR)                    # Main documentation
├── README_EN.md                      # English documentation
└── HANDOVER.md                       # This document
```

### 3.2 Workflow Generation Flow

```
1. USER INPUT
   └─> Natural language description
        ↓
2. ENHANCEMENT (optional)
   └─> Claude improves description
        ↓
3. GENERATION
   ├─> Claude Sonnet 4 with massive prompt (~2900 lines)
   ├─> ParadigmClient template (950 lines) injected
   ├─> Mandatory patterns (file upload, wait_for_embedding)
   └─> Generated Python code
        ↓
4. POST-PROCESSING
   ├─> detect_workflow_type(): simple/complex/with_files
   ├─> count_api_calls(): detection >40 calls (rate limiting)
   ├─> add_staggering_to_workflow(): pauses between uploads
   └─> fix_fstring_with_braces(): syntax correction (DISABLED)
        ↓
5. VALIDATION
   ├─> compile(): Python syntax verification
   └─> If failure: retry (max 3 times) with error feedback
        ↓
6. STORAGE
   ├─> Upstash Redis / Vercel KV (TTL 24h)
   └─> In-memory fallback if Redis unavailable
        ↓
7. EXECUTION
   ├─> Secure sandbox (restricted globals)
   ├─> API keys injection
   ├─> Configurable timeout (default 30 min)
   └─> Stdout/stderr capture
        ↓
8. EXPORT (optional)
   ├─> PDF Report
   ├─> Workflow Runner Package (ZIP)
   └─> MCP Server Package (ZIP)
```

### 3.3 Generator Architecture (generator.py)

**File**: `api/workflow/generator.py` (3393 lines)

#### Structure:
- **Lines 15-122**: Utility functions (4 functions)
- **Lines 128-201**: `generate_workflow()` - Main entry point
- **Lines 202-2551**: `_generate_code()` - Generation via Claude (~2900 lines of prompt)
- **Lines 2553-2571**: `_clean_generated_code()` - Cleaning
- **Lines 2572-3339**: `enhance_workflow_description()` - Enhancement (730 lines of prompt)
- **Lines 3340-3390**: `_validate_code()` - Compilation validation

#### ParadigmClient Template:
- **950 lines** of Paradigm client embedded in prompt (lines 247-1198)
- **Reusable HTTP session**: 5.55x faster
- **11 methods** corresponding to 11 Paradigm endpoints
- **Complete async/await** support

#### Mandatory Patterns:
1. **File Upload Pattern** (180 lines, 1410-1589):
   ```python
   import builtins
   attached_files = None
   if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
       attached_files = globals()['attached_file_ids']
   elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
       attached_files = builtins.attached_file_ids

   if attached_files:
       file_id = int(attached_files[0])
       file_info = await paradigm_client.wait_for_embedding(
           file_id=file_id, max_wait_time=300, poll_interval=2
       )
   ```

2. **Parallelization Pattern**:
   ```python
   results = await asyncio.gather(
       paradigm_client.document_search(query1),
       paradigm_client.document_search(query2),
       paradigm_client.document_search(query3)
   )
   ```

3. **Error Handling Pattern**:
   ```python
   try:
       result = await paradigm_client.method()
   except Exception as e:
       return f"Error: {str(e)}"
   ```

#### Retry Mechanism:
- **3 maximum attempts**
- **Contextualized error feedback**: compilation error + traceback
- **Adapted prompt**: "CRITICAL ERROR DETECTED - FIX THIS"

---

## 4. Components and Features

### 4.1 FastAPI Backend (api/main.py)

**API Endpoints** (15 endpoints):

#### Workflows (7 endpoints)
```python
POST   /api/workflows                              # Create workflow
POST   /api/workflows/enhance-description          # Improve description
GET    /api/workflows/{id}                         # Workflow details
POST   /api/workflows/{id}/execute                 # Execute workflow
GET    /api/workflows/{id}/executions/{exec_id}    # Execution details
GET    /api/workflows/{id}/executions/{exec_id}/pdf # Download PDF
POST   /api/workflows-with-files                   # Create with attached files
```

#### Packages (2 endpoints - local dev only)
```python
POST   /api/workflow/generate-package/{id}         # Generate Workflow Runner ZIP
POST   /api/workflow/generate-mcp-package/{id}     # Generate MCP Server ZIP
```

#### Files (3 endpoints)
```python
POST   /api/files/upload                           # Upload file
GET    /api/files/{id}                             # File info
DELETE /api/files/{id}                             # Delete file
```

#### Health (3 endpoints)
```python
GET    /health                                     # Health check
GET    /                                           # Frontend
GET    /lighton-logo.png                          # Static logo
```

### 4.2 Standalone Paradigm Client

**File**: `api/paradigm_client_standalone.py`

**Features**:
- **Reusable HTTP session**: 5.55x performance improvement
- **Async/await**: Complete async operations support
- **Automatic retry**: 3 attempts with exponential backoff
- **Configurable timeouts**: Default 30 min, customizable
- **Error handling**: Detailed exceptions

**Methods** (11):
```python
async def document_search(query, file_ids=None, top_k=5)
async def analyze_documents_with_polling(query, document_ids, max_wait=300)
async def chat_completion(prompt, guided_choice=None, guided_regex=None, guided_json=None)
async def upload_file(file_content, filename, collection_type='private')
async def get_file(file_id)
async def delete_file(file_id)
async def wait_for_embedding(file_id, max_wait_time=300, poll_interval=2)
async def get_file_chunks(file_id)
async def filter_chunks(query, chunk_ids, n=5)
async def query(query, collection='private')
async def analyze_image(image_path_or_url, prompt)
```

### 4.3 Workflow Executor (api/workflow/executor.py)

**Responsibilities**:
- **Sandboxing**: Restricted environment (safe globals only)
- **API Keys Injection**: LIGHTON_API_KEY automatically injected
- **Timeout Protection**: asyncio.wait_for with configurable timeout
- **File Attachment Support**: `attached_file_ids` global variable
- **Logging**: Stdout/stderr capture
- **Storage**: Redis/Vercel KV with in-memory fallback

**Security**:
```python
safe_globals = {
    "__builtins__": {
        "print": print,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "True": True,
        "False": False,
        "None": None,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
    },
    "asyncio": asyncio,
    # Dangerous modules EXCLUDED: os, sys, subprocess, eval, exec, open
}
```

### 4.4 Web Frontend Interface

**File**: `index.html` (~1500 lines)

**Features**:
- **Vanilla JavaScript**: No framework dependencies
- **Drag-and-Drop Upload**: Visual file interface
- **Real-Time Logs**: Colored monitoring with API tracing
- **Code Preview**: Generated workflow visualization
- **PDF Export**: Integrated jsPDF
- **Package Downloads**: Workflow Runner ZIP, MCP Server
- **Responsive Design**: Desktop and mobile

**Sections**:
1. Description Enhancement (AI description improvement)
2. Workflow Creation (creation with optional files)
3. Workflow Execution (execution with real-time logs)
4. Code Preview (generated code visualization)
5. Downloads (PDF, packages)

---

## 5. Exportable Packages

### 5.1 Workflow Runner Package

**Generator**: `api/workflow/package_generator.py` (245 lines)

#### ZIP Contents:
```
workflow-{name}-{id}.zip
├── frontend/
│   ├── index.html              # Auto-generated dynamic interface
│   └── config.json             # UI configuration (fields, types)
├── backend/
│   ├── main.py                 # FastAPI server
│   ├── workflow.py             # Generated workflow code
│   ├── paradigm_client.py      # Standalone Paradigm client
│   └── requirements.txt        # Python dependencies
├── docker-compose.yml          # Docker configuration
├── Dockerfile                  # Optimized Docker image
├── README.md (FR)              # French documentation
├── README_EN.md                # English documentation
├── .env.example                # Configuration template
└── .gitignore                  # Files to ignore
```

#### Features:
- **Auto-Generated UI**: Claude code analysis for UI configuration
- **Intelligent Detection**:
  - Required/optional text fields
  - File upload (single/multiple)
  - Different document types (DC4, RIB, CV, etc.)
  - Max files per field
- **Integrated PDF Export**: jsPDF for reports
- **Docker Ready**: `docker-compose up` and ready
- **Bilingual**: FR + EN documentation
- **Standalone**: No dependency on main system

#### Workflow Analyzer (api/workflow/workflow_analyzer.py)

**Function**: `analyze_workflow_for_ui(workflow_code, workflow_name, workflow_description)`

**Automatic Analysis**:
1. **Text Input Detection**:
   - Search for `user_input` parameter in `execute_workflow()`
   - Verify actual use in code
   - Detection required vs optional (fallback values)
   - Generation of appropriate label and placeholder

2. **File Input Detection**:
   - Search for `attached_file_ids`, `file_ids`, `document_ids`
   - Detection of conditional logic (`if attached_file_ids: ... else: ...`)
   - File counting by array indices `[0]`, `[1]`, `[2]`
   - Label inference from workflow description

3. **Multiple File Types Detection**:
   - Pattern "1 job description + 5 CVs" → 2 separate fields
   - Pattern "DC4 + RIB + BOAMP" → 3 separate fields
   - Array slicing `attached_files[0]` vs `attached_files[1:]`
   - Document names extraction from description

**Example Output**:
```json
{
  "workflow_name": "CV Analysis",
  "workflow_description": "Compare CVs with job requirements",
  "requires_text_input": false,
  "requires_files": true,
  "files": [
    {
      "label": "Job Description",
      "description": "Document describing the position",
      "required": true,
      "multiple": false
    },
    {
      "label": "Candidate CVs",
      "description": "CVs to analyze (maximum 5)",
      "required": true,
      "multiple": true,
      "max_files": 5
    }
  ]
}
```

#### Client Deployment:
```bash
# 1. Extract ZIP
unzip workflow-package.zip
cd workflow-{name}-{id}

# 2. Configure API keys
cp .env.example .env
nano .env  # Add PARADIGM_API_KEY

# 3. Launch with Docker
docker-compose up -d

# 4. Access interface
http://localhost:8000
```

### 5.2 MCP Server Package

**Generator**: `api/workflow/mcp_package_generator.py` (586 lines)

#### ZIP Contents:
```
mcp-{name}-{id}.zip
├── server.py                   # MCP stdio for Claude Desktop
├── http_server.py              # MCP HTTP for Paradigm
├── workflow.py                 # Workflow code with WorkflowExecutor
├── paradigm_client.py          # Standalone Paradigm client
├── pyproject.toml              # Python package configuration
├── README.md (FR)              # French documentation
├── README_EN.md                # English documentation
├── .env.example                # Configuration template
└── .gitignore                  # Files to ignore
```

#### Operating Modes:

**Mode 1: stdio (Local Claude Desktop)**:
```bash
# Installation in Claude Desktop
cd mcp-package
pip install -e .

# Configuration claude_desktop_config.json
{
  "mcpServers": {
    "workflow-name": {
      "command": "python",
      "args": ["-m", "path.to.server"],
      "env": {
        "PARADIGM_API_KEY": "sk-..."
      }
    }
  }
}
```

**Mode 2: HTTP (Remote Paradigm)**:
```bash
# Start HTTP server
python http_server.py

# Configuration with bearer token
curl http://localhost:8080/mcp/v1/tools \
  -H "Authorization: Bearer your-secret-token"
```

#### MCP Features:

**Tool Definition**:
```json
{
  "name": "execute-workflow-name",
  "description": "Workflow description",
  "inputSchema": {
    "type": "object",
    "properties": {
      "file_paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Local file paths to analyze"
      },
      "query": {
        "type": "string",
        "description": "Question or request (optional)"
      }
    },
    "required": ["file_paths"]
  }
}
```

**WorkflowExecutor** (in workflow.py):
- **Multi-Mode Input**:
  - `file_paths`: Upload local files (Claude Desktop)
  - `file_ids`: Direct Paradigm IDs
  - `paradigm_context`: Documents from Paradigm workspace (future)
  - Legacy `attached_file_ids` (Workflow Builder web)
- **Auto-Upload**: Automatic local file upload to Paradigm
- **Wait for Embedding**: Indexing wait (300s timeout, 2s poll)
- **Error Handling**: Detailed exceptions

#### Known Limitations:

⚠️ **Paradigm MCP Bug**:
- `file_ids` are NOT transmitted from Paradigm to MCP server
- **Current workaround**: HTTP mode with manual upload
- **Impact**: Workflows with files don't work on Paradigm
- **Status**: Bug reported to Paradigm team

⚠️ **Claude Desktop Timeout**:
- 4-minute limit for tool execution
- Complex workflows may timeout
- **Workaround**: HTTP mode without time limit

---

## 6. Tests and Quality

### 6.1 Complete Test Suite

**Location**: `tests/` (97 tests)

#### Paradigm API Tests (26 tests)
**File**: `tests/test_paradigm_api.py`

Coverage of 11 endpoints:
```python
# Document Search (3 tests)
test_document_search_basic()
test_document_search_with_file_ids()
test_document_search_vision_fallback()

# Document Analysis (2 tests)
test_analyze_documents_basic()
test_analyze_documents_polling()

# Chat Completions (2 tests)
test_chat_completion_basic()
test_chat_completion_guided_regex()

# Files (5 tests)
test_file_upload()
test_file_get_info()
test_file_wait_for_embedding()
test_file_delete()
test_file_lifecycle()

# File Operations (4 tests)
test_file_ask_question()
test_file_get_chunks()
test_filter_chunks()
test_query()

# Image Analysis (1 test)
test_analyze_image()

# Error Handling (3 tests)
test_invalid_api_key()
test_file_not_found()
test_malformed_request()
```

#### Workflow Tests (15 tests)
**File**: `tests/test_workflow_api.py`

```python
# Creation (5 tests)
test_create_simple_workflow()
test_create_workflow_with_name()
test_enhance_description()
test_create_workflow_invalid_description()
test_workflow_generation_retry()

# Execution (8 tests)
test_execute_simple_workflow()
test_execute_workflow_with_files()
test_execute_workflow_timeout()
test_execute_nonexistent_workflow()
test_workflow_parallelization_detection()
test_workflow_complex_detection()
test_workflow_execution_logs()
test_workflow_execution_error_handling()

# Retrieval (2 tests)
test_get_workflow()
test_get_execution()
```

#### File Tests (18 tests)
**File**: `tests/test_files_api.py`

```python
# Upload (5 tests)
test_upload_text_file()
test_upload_pdf_file()
test_upload_multiple_files()
test_upload_invalid_file()
test_upload_with_workspace()

# Query (4 tests)
test_file_ask_question()
test_file_get_chunks()
test_file_filter_chunks()
test_file_query_collection()

# Lifecycle (4 tests)
test_file_get_info()
test_file_wait_for_embedding_success()
test_file_wait_for_embedding_timeout()
test_file_delete()

# Integration (5 tests)
test_upload_and_use_in_workflow()
test_multiple_files_workflow()
test_file_upload_rate_limiting()
test_file_concurrent_uploads()
test_file_cleanup_after_workflow()
```

#### Integration Tests (12 tests)
**File**: `tests/test_integration.py`

```python
# User Journeys (4 tests)
test_complete_user_journey()                  # Upload → Workflow → Exec → PDF
test_file_to_workflow_integration()           # Files → Workflow
test_workflow_enhancement_to_execution()      # Enhancement → Exec
test_multiple_workflows_parallel()            # Parallel workflows

# Complex Scenarios (5 tests)
test_workflow_with_vision_fallback()
test_workflow_with_structured_extraction()
test_workflow_with_multiple_file_types()
test_workflow_with_rate_limiting()
test_workflow_retry_on_error()

# Performance (3 tests)
test_concurrent_workflow_executions()
test_session_reuse_performance()
test_parallelization_performance()
```

#### Security Tests (16 tests)
**File**: `tests/test_security.py`

```python
# Sandbox Security (6 tests)
test_file_access_blocked()                    # os.open(), open()
test_subprocess_blocked()                     # subprocess.run()
test_os_module_blocked()                      # import os
test_eval_exec_blocked()                      # eval(), exec()
test_dangerous_imports_blocked()              # sys, socket, requests
test_builtin_overwrite_blocked()              # __builtins__ manipulation

# Input Validation (4 tests)
test_xss_in_workflow_description()
test_sql_injection_in_workflow_name()
test_path_traversal_in_file_upload()
test_command_injection_in_user_input()

# Resource Protection (3 tests)
test_memory_exhaustion_protection()
test_infinite_loop_timeout()
test_api_rate_limiting()

# API Key Security (3 tests)
test_api_key_not_in_generated_code()
test_api_key_not_in_logs()
test_api_key_not_in_error_messages()
```

### 6.2 Makefile and Automation

**File**: `tests/Makefile`

**Main Commands**:
```bash
make install          # Install dependencies
make verify-env       # Verify environment variables
make test             # All tests with coverage
make test-quick       # Quick tests (without slow)
make test-smoke       # API health test
make test-paradigm    # Paradigm API tests only
make test-workflow    # Workflow tests only
make test-files       # File tests only
make test-integration # End-to-end tests only
make test-security    # Security tests only
make test-coverage    # Generate HTML coverage report
make start-api        # Start backend API
make stop-api         # Stop backend API
make full-test        # Complete cycle: start → test → stop
make ci-test          # Tests for CI/CD
make clean            # Clean test files
```

### 6.3 Coverage and Metrics

**Current Coverage**:
- **11/11 Paradigm endpoints**: 100% coverage
- **97 total tests**
- **Execution time**: ~5-10 minutes (all tests)
- **Quick tests**: ~2 minutes

**Distribution**:
```
test_paradigm_api.py    : 26 tests (27%)
test_workflow_api.py    : 15 tests (15%)
test_files_api.py       : 18 tests (19%)
test_integration.py     : 12 tests (12%)
test_security.py        : 16 tests (16%)
Other                   : 10 tests (10%)
---
Total                   : 97 tests (100%)
```

---

## 7. Deployment and Infrastructure

### 7.1 Deployment Options

#### Option 1: Docker (Recommended for Production)

**Advantages**:
- Minimal configuration
- Isolated and reproducible environment
- No serverless function limits
- Production-ready

**Deployment**:
```bash
# 1. Clone repo
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-

# 2. Configure .env
cp .env.example .env
nano .env  # Add ANTHROPIC_API_KEY, LIGHTON_API_KEY

# 3. Start
docker-compose up --build

# 4. Access
# Frontend: http://localhost:3000
# API: http://localhost:8000/docs
```

**Configuration**:
- `Dockerfile`: Multi-stage Python 3.11 image
- `docker-compose.yml`: Frontend + backend + Redis (optional) services

#### Option 2: Vercel (Serverless)

**Prerequisites**:
- ⚠️ Vercel Pro Plan ($20/month) required
  - Python Runtime (not in free tier)
  - Execution Time >30s (free tier limited to 10s)
  - 12 Serverless Functions used (limit reached)

**Deployment**:
```bash
# 1. Connect GitHub/GitLab repo to Vercel

# 2. Configure environment variables
ANTHROPIC_API_KEY=sk-...
LIGHTON_API_KEY=sk-...

# 3. Link Vercel KV (Storage)
# Variables automatically created:
# - KV_REST_API_URL
# - KV_REST_API_TOKEN

# 4. Deploy
git push  # Automatic
```

**Vercel Limitations**:
- Package generation disabled (generate-package, generate-mcp-package)
- 12 serverless functions limit reached
- 60s max timeout (complex workflows may fail)

#### Option 3: Manual Python (VPS, Cloud VM)

**Deployment**:
```bash
# 1. Installation
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env
nano .env  # Add API keys

# 3. Start
uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

**Nginx Reverse Proxy** (optional):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### 7.2 Environment Variables

**Required**:
```bash
ANTHROPIC_API_KEY=sk-ant-...      # Anthropic Claude API key
LIGHTON_API_KEY=sk-...            # LightOn Paradigm API key
```

**Optional**:
```bash
# URLs
PARADIGM_BASE_URL=https://paradigm.lighton.ai  # Paradigm API URL
API_BASE_URL=http://localhost:8000             # Backend API URL

# Timeouts
MAX_EXECUTION_TIME=1800                        # Workflow timeout (30 min)

# Storage (Upstash Redis or Vercel KV)
UPSTASH_REDIS_REST_URL=https://...            # Upstash Redis URL
UPSTASH_REDIS_REST_TOKEN=...                  # Upstash Redis token
KV_REST_API_URL=https://...                   # Vercel KV URL (auto)
KV_REST_API_TOKEN=...                         # Vercel KV token (auto)

# Debug
DEBUG=true                                     # Debug mode
```

### 7.3 Persistence

#### Upstash Redis (Production)
- **TTL**: 24 hours
- **Serverless-compatible**: No persistent connection
- **REST API**: Access via HTTP

#### Vercel KV (Vercel Production)
- **Based on**: Upstash Redis
- **Auto-configured**: Variables automatically created during linking
- **TTL**: 24 hours

#### In-Memory Fallback (Development)
- **Automatic**: If Redis unavailable
- **Non-persistent**: Lost on restart
- **Usage**: Local dev only

### 7.4 CORS Configuration

**Allowed Origins**:
```python
allow_origins=[
    "null",                                    # file:// protocol
    "http://localhost:3000",                   # Local dev
    "http://127.0.0.1:3000",
    "https://scaffold-ai-test2.vercel.app",    # Production
    "https://*.vercel.app",                    # All Vercel deployments
    "https://*.netlify.app",                   # Netlify
    "https://*.github.io",                     # GitHub Pages
    "https://*.surge.sh",                      # Surge
    "https://*.firebaseapp.com"                # Firebase
]
```

---

## 8. Documentation

### 8.1 Created Documentation

#### Main Documentation
1. **README.md (FR)**: Complete project documentation
   - Docker quick start
   - Deployment options (Vercel, manual Python)
   - Detailed features
   - API endpoints
   - Workflow Runner Package
   - MCP Server Package

2. **README_EN.md**: Complete English version

#### Technical Documentation
1. **docs/ANALYSE_GENERATOR.md (1167 lines FR)**:
   - Detailed generator.py architecture
   - Analysis of 3393 lines of code
   - ParadigmClient templates (950 lines)
   - System prompts (~2900 lines)
   - Mandatory patterns
   - Retry process
   - Performance optimizations

2. **docs/ANALYSE_GENERATOR_EN.md (1167 lines EN)**:
   - Complete English translation

3. **docs/analyse-conformite-architecture.md**:
   - Complete security audit
   - Vulnerability analysis
   - Architecture recommendations
   - Improvement plan

4. **docs/workflow-builder-schema.html**:
   - Interactive architecture schema
   - Flow diagrams
   - Component visualization

#### Test Documentation
1. **tests/README.md (FR)**:
   - Complete test suite (97 tests)
   - Coverage of 11/11 Paradigm endpoints
   - Makefile commands
   - Security tests
   - CI/CD configuration

2. **tests/README_EN.md**: English version

#### Package Documentation

**Workflow Runner**:
1. **api/workflow/templates/workflow_runner/README.md (FR)**
2. **api/workflow/templates/workflow_runner/README_EN.md**

**MCP Server**:
1. **api/workflow/templates/mcp_server/README.md (FR)**
2. **api/workflow/templates/mcp_server/README_EN.md**

### 8.2 Embedded Documentation

**Code Comments**:
- Python docstrings (Google style) for all classes and functions
- Inline comments for complex logic
- Complete type hints

**API Documentation**:
- OpenAPI (Swagger) auto-generated by FastAPI
- Accessible at `/docs` (Swagger UI)
- Accessible at `/redoc` (ReDoc)

---

## 9. Current State and Limitations

### 9.1 Operational Features

✅ **Core Features**:
- Workflow generation from natural language
- Description enhancement before generation
- Automatic retry (3 attempts)
- Validation and post-processing
- Workflow execution with timeout
- File upload and lifecycle management
- PDF report export

✅ **Paradigm API**:
- 11/11 endpoints integrated and tested
- Reusable HTTP session (5.55x faster)
- Support for guided_choice, guided_regex, guided_json
- Vision fallback for scanned documents

✅ **Packages**:
- Workflow Runner Package (standalone ZIP)
- MCP Server Package (Claude Desktop + Paradigm)
- Auto-generated UI by Claude analysis
- Bilingual documentation (FR/EN)

✅ **Tests**:
- 97 tests covering all components
- 11/11 Paradigm endpoints tested
- End-to-end integration tests
- Sandbox security tests

### 9.2 Technical Limitations

#### Vercel Limitations
⚠️ **Package Generation**:
- Disabled on Vercel (12 serverless functions limit)
- Solution: Use local Docker to generate packages

⚠️ **Execution Timeout**:
- Max 60s on Vercel (complex workflows may timeout)
- Solution: Use Docker with configurable timeout (30 min)

#### MCP Limitations
⚠️ **Paradigm file_ids Bug**:
- `file_ids` are NOT transmitted from Paradigm MCP
- Impact: Workflows with files don't work on Paradigm
- Workaround: HTTP mode with manual upload
- Status: Bug reported to Paradigm team

⚠️ **Claude Desktop Timeout**:
- 4-minute limit for tool execution
- Impact: Complex workflows may timeout
- Workaround: HTTP mode without limit

#### Sandbox Limitations

⚠️ **Insufficient Sandbox for Public Production**:
- Basic built-ins restriction only
- No true process isolation
- Vulnerable to sophisticated attacks
- **Recommendation**: Isolated Docker containers + Linux namespaces

### 9.3 Compatibility

**Python**:
- ✅ Python 3.11+
- ✅ Python 3.12
- ⚠️ Python 3.13 (not tested)

**Browsers**:
- ✅ Chrome/Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ⚠️ IE11 (not supported)

**Platforms**:
- ✅ Linux (Ubuntu 20.04+, Debian 11+)
- ✅ macOS 11+
- ✅ Windows 10/11
- ✅ Docker (all platforms)

---

## 10. Known Bugs

### 10.1 Critical

#### 🔴 BUG-001: MCP file_ids not transmitted on Paradigm
**Status**: CRITICAL - Blocking for production
**Component**: MCP Server Package + Paradigm
**Description**: `file_ids` are not transmitted from Paradigm to HTTP MCP server
**Impact**: Workflows with files don't work on Paradigm
**Workaround**: Use HTTP mode with manual file upload
**Action**: Bug reported to Paradigm team, awaiting fix
**Reproduce**:
```python
# In Paradigm, with configured MCP tool
# 1. Upload file on Paradigm
# 2. Try to use MCP tool with this file
# 3. file_id is NOT transmitted to MCP server
# 4. Workflow fails because file not found
```

### 10.2 Major

#### 🟠 BUG-002: Insufficient sandbox for public production
**Status**: MAJOR - Security risk
**Component**: Workflow Executor
**Description**: Sandbox based on restricted globals is insufficient
**Impact**: Vulnerable to sophisticated arbitrary code attacks
**Workaround**: Private deployment with trusted users only
**Action**: Complete sandbox refactoring (see Security section)
**Reproduce**:
```python
# Malicious code can bypass restrictions
# Example: file access via __builtins__.__dict__
```

#### 🟠 BUG-003: Complex workflow timeout on Vercel
**Status**: MAJOR - Platform limitation
**Component**: Vercel Serverless Functions
**Description**: Workflows >60s timeout on Vercel
**Impact**: Complex workflows fail in Vercel production
**Workaround**: Deploy on Docker with 30 min timeout
**Action**: Clear documentation on Vercel limitations

### 10.3 Minor

#### 🟡 BUG-004: Undocumented Paradigm rate limiting
**Status**: MINOR - Active workaround
**Component**: Paradigm API file upload
**Description**: Undocumented limit on simultaneous uploads
**Impact**: Upload failures if too fast
**Workaround**: 60s pauses between uploads (add_staggering_to_workflow)
**Action**: Request official documentation from Paradigm

---

**Note**: The original BUG-004 bug (fix_fstring_with_braces too aggressive) was **deleted** on December 24, 2024. The function and its call were removed from the code (dead code cleaned).

---

## 11. Improvement Proposals

### 11.1 Short Term (1-2 months)

#### P1 - Secure Sandbox
**Priority**: CRITICAL
**Objective**: Make application production-ready for public use
**Approach**:
1. **Isolated Docker Containers**:
   ```python
   # Execute each workflow in dedicated Docker container
   docker_client = docker.from_env()
   container = docker_client.containers.run(
       image="workflow-runner:secure",
       command=["python", "workflow.py"],
       mem_limit="512m",         # RAM limit
       cpu_quota=50000,          # CPU limit
       network_disabled=True,    # No network
       read_only=True,           # Read-only filesystem
       remove=True,              # Auto-cleanup
       volumes={
           workflow_path: {
               "bind": "/app/workflow.py",
               "mode": "ro"
           }
       }
   )
   ```

2. **Linux Namespaces + cgroups**:
   - PID namespace: Process isolation
   - Network namespace: Network isolation
   - Mount namespace: Filesystem isolation
   - User namespace: User isolation
   - Cgroups: Resource limits (CPU, RAM, I/O)

3. **Security Profiles**:
   - AppArmor or SELinux policies
   - Seccomp filters (block dangerous syscalls)
   - Capabilities drop (CAP_NET_RAW, CAP_SYS_ADMIN, etc.)

**Effort**: 3-4 weeks
**Benefits**: Production-ready, safe public deployment

#### P2 - Fix MCP file_ids Paradigm Bug
**Priority**: HIGH
**Objective**: Enable workflows with files on Paradigm
**Actions**:
1. Collaboration with Paradigm team for fix
2. End-to-end tests after fix
3. Updated documentation

**Effort**: Depends on Paradigm (1-2 weeks after their fix)
**Benefits**: Complete feature, improved user experience

#### P3 - Improve Retry Mechanism
**Priority**: MEDIUM
**Objective**: Increase generation success rate
**Improvements**:
1. **Exponential Backoff**: Increase delay between retries
2. **Categorized Errors**:
   ```python
   if "SyntaxError" in error:
       prompt += "SYNTAX ERROR: Fix indentation and quotes"
   elif "NameError" in error:
       prompt += "UNDEFINED VARIABLE: Check variable names"
   elif "TimeoutError" in error:
       prompt += "TIMEOUT: Simplify workflow, reduce API calls"
   ```
3. **Learning from Past Failures**:
   - Store common errors
   - Add to initial prompt for prevention

**Effort**: 1 week
**Benefits**: +15-20% success rate

#### P4 - Improve Robustness for Complex Workflows
**Priority**: HIGH
**Objective**: Enable generator to reliably create increasingly complex workflows
**Improvements**:

1. **More Structured Prompts**:
   - Decompose generation into steps (planning → code → validation)
   - More detailed templates by workflow type
   - Examples of complex workflows in prompt
   - Specific instructions for robust error handling

2. **Automatic Complexity Detection**:
   ```python
   # Currently: simple detection based on number of API calls
   # Improvement: analyze real complexity
   - Number of conditional branches
   - Loop nesting depth
   - Number of variables and data structures
   - Dependencies between workflow steps
   ```

3. **Progressive Generation**:
   - For very complex workflows: generate by functional blocks
   - Intermediate validation of each block
   - Final assembly with consistency check

4. **Advanced Error Handling**:
   - Systematic try/except around each API call
   - Detailed logs for debugging
   - Automatic fallback strategies
   - Data validation between each step

5. **Automatic Optimizations**:
   - Detection and automatic parallelization (already implemented via asyncio.gather)
   - Cache intermediate results to avoid recalculations
   - Reduction of redundant API calls
   - Intelligent chunking for large data volumes

6. **Regression Tests**:
   - Suite of reference complex workflows
   - Automatic validation after each generator modification
   - Performance benchmarks

**Examples of Complex Workflows to Support**:
- Comparative analysis of 20+ documents with structured extraction
- Workflows with >50 steps and complex conditional logic
- Batch processing with partial error handling
- Nested workflows (workflow calling other workflows)

**Effort**: 3-4 weeks
**Benefits**:
- Support for advanced use cases
- Reduction of failures on complex workflows
- Better quality generated code
- System extensibility

---

## 12. Security

### 12.1 Identified Vulnerabilities

#### V1 - Insufficient Sandbox (CRITICAL)
**Vulnerability**: Isolation based on restricted globals only
**Possible Exploits**:
```python
# Filesystem access via __builtins__ manipulation
__builtins__.__dict__['__import__']('os').system('rm -rf /')

# Bypass via introspection
for cls in [].__class__.__bases__[0].__subclasses__():
    if cls.__name__ == 'Popen':
        cls(['cat', '/etc/passwd'])
```

**Recommendations**:
1. Isolated Docker containers (cf. P1)
2. AST parsing to block dangerous patterns before exec()
3. VM-level isolation (gVisor, Firecracker)

#### V2 - API Keys Exposure (MEDIUM)
**Vulnerability**: API keys injected in globals, visible via introspection
**Exploit**:
```python
# Malicious workflow code
import builtins
api_key = getattr(builtins, 'LIGHTON_API_KEY')
# Send key to external server
```

**Recommendations**:
1. Use limited-scope environment variables
2. API proxy with token rotation
3. NEVER log API keys

#### V3 - Weak Rate Limiting (MEDIUM)
**Vulnerability**: No strict rate limiting on workflow creation
**Exploit**: DDoS via massive workflow creation → API quota exhaustion
**Recommendations**:
1. Rate limiting per IP (10 workflows/hour)
2. Rate limiting per user (50 workflows/day)
3. CAPTCHA after 5 rapid attempts

#### V4 - Insufficient Input Validation (MEDIUM)
**Vulnerability**: No sanitization of workflow descriptions/names
**Exploit**: XSS via malicious workflow names
**Recommendations**:
1. Sanitize HTML (bleach library)
2. Escape output in frontend
3. Content Security Policy (CSP) headers

#### V5 - Permissive CORS (LOW)
**Vulnerability**: Wildcard origins (*.vercel.app, *.github.io, etc.)
**Exploit**: Cross-origin attacks from compromised domains
**Recommendations**:
1. Exact whitelist of production domains
2. Credentials: false except trusted domains
3. Preflight request validation

### 12.2 Priority Recommendations

#### Short Term (Urgent)
1. **Docker Sandbox** (cf. P1) - CRITICAL
2. **Strict Rate Limiting** - HIGH
3. **Input Validation** - HIGH
4. **API Key Proxy** - MEDIUM

#### Medium Term
1. **External Security Audit** - HIGH
2. **Penetration Testing** - HIGH
3. **Security Headers** (CSP, HSTS, X-Frame-Options) - MEDIUM
4. **WAF (Web Application Firewall)** - MEDIUM

#### Long Term
1. **Bug Bounty Program** - MEDIUM
2. **SOC 2 Compliance** - LOW (if SaaS)
3. **Team Security Training** - MEDIUM

### 12.3 Current Best Practices

✅ **What's good**:
- HTTPS only
- Secrets in environment variables
- Workflow execution timeout
- Detailed logs (incident forensics)
- Regular dependency updates
- Security tests (16 tests)

⚠️ **What's missing**:
- True sandbox isolation
- Strict rate limiting
- API key rotation
- Complete input sanitization
- Security headers
- Security incident monitoring

---

## 13. References and Resources

### 13.1 Technical Documentation

**Source Code**:
- Repository: https://github.com/Isydoria/lighton-workflow-generator-
- Main branch: `main`
- Documentation branch: `docs/update-readme`
- Features branch: `feature/mcp-package-generator`

**APIs**:
- Anthropic Claude API: https://docs.anthropic.com/
- LightOn Paradigm API: https://paradigm.lighton.ai/docs
- MCP Protocol: https://modelcontextprotocol.io/

**Technologies**:
- FastAPI: https://fastapi.tiangolo.com/
- Docker: https://docs.docker.com/
- Pytest: https://docs.pytest.org/
- Vercel: https://vercel.com/docs

### 13.2 Project Documents

**Main Documentation**:
- `README.md` (FR): Complete documentation
- `README_EN.md`: English version
- `HANDOVER.md`: This document

**Technical Documentation**:
- `docs/ANALYSE_GENERATOR.md`: generator.py analysis (1167 lines FR)
- `docs/ANALYSE_GENERATOR_EN.md`: English version
- `docs/analyse-conformite-architecture.md`: Security audit
- `docs/workflow-builder-schema.html`: Interactive architecture schema

**Test Documentation**:
- `tests/README.md` (FR): Complete test suite
- `tests/README_EN.md`: English version

**Package Documentation**:
- `api/workflow/templates/workflow_runner/README.md` (FR)
- `api/workflow/templates/workflow_runner/README_EN.md`
- `api/workflow/templates/mcp_server/README.md` (FR)
- `api/workflow/templates/mcp_server/README_EN.md`

### 13.3 Final Statistics

**Code**:
- 245 commits since November 3, 2024
- ~15,000 lines of Python code
- ~1,500 lines of JavaScript code
- ~3,000 lines of documentation

**Tests**:
- 97 tests (26 Paradigm, 15 workflows, 18 files, 12 integration, 16 security)
- Coverage of 11/11 Paradigm endpoints
- ~5-10 minutes complete execution

**Features**:
- 11 integrated Paradigm endpoints
- 15 backend API endpoints
- 2 exportable packages (Workflow Runner, MCP Server)
- 4 deployment modes (Docker, Vercel, manual Python, MCP)

**Documentation**:
- 8 bilingual READMEs (FR/EN)
- 1167 lines technical analysis generator.py
- 455 lines test README
- This handover document

---

## 14. Contacts and Transmission

### 14.1 Technical Contact Points

**Repository**: https://gitlab.lighton.ai/paradigm/usescases/workflowbuilder
**Documentation**: See section 13.2 above

### 14.2 Handover Checklist

- [x] Source code on GitLab (245 commits)
- [x] Complete technical documentation (8 bilingual READMEs)
- [x] Functional test suite (97 tests)
- [x] generator.py analysis (1167 lines)
- [x] Security audit and recommendations
- [x] Deployment documentation (Docker, Vercel, Python)
- [x] Documented known bugs
- [x] Detailed improvement proposals
- [x] This handover document

---

**Document drafted on**: December 24, 2024
**Version**: 1.0
**Author**: Nathanaëlle
**Status**: FINAL
