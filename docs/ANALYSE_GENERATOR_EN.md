# Technical Analysis of the Workflow Generator

**Technical analysis document**: [`api/workflow/generator.py`](../api/workflow/generator.py)
**Version**: 1.1.0-mcp
**Date**: January 2025
**Size**: 3393 lines of code

---

## 📋 Table of Contents

1. [Overview](#1-overview)
2. [Global Architecture](#2-global-architecture)
3. [Post-processing Utility Functions](#3-post-processing-utility-functions)
4. [WorkflowGenerator Class](#4-workflowgenerator-class)
5. [Integrated ParadigmClient Template](#5-integrated-paradigmclient-template)
6. [Massive Prompt System](#6-massive-prompt-system)
7. [Generation and Retry Process](#7-generation-and-retry-process)
8. [Description Enhancement Mechanism](#8-description-enhancement-mechanism)
9. [Validation and Error Detection](#9-validation-and-error-detection)
10. [Optimizations and Best Practices](#10-optimizations-and-best-practices)
11. [Critical Points and Mandatory Patterns](#11-critical-points-and-mandatory-patterns)

---

## 1. Overview

The `generator.py` file is the **core of the LightOn Workflow Builder system**. It transforms natural language descriptions into executable Python code that interacts with the Paradigm API.

### Statistics

- **3393 lines of code** (including ~2900 lines of system prompts)
- **2 main classes**:
  - `WorkflowGenerator`: Generation and orchestration
  - `ParadigmClient`: Template embedded in prompts
- **4 utility functions** for post-processing
- **30+ Paradigm API methods** documented in the client template
- **Automatic retry** with maximum 3 attempts
- **Syntax validation** with Python compilation
- **Multilingual support** (automatic French/English detection)

### Main Responsibilities

1. **Python code generation** from natural language descriptions
2. **Automatic validation and correction** of generated code (retry with error context)
3. **User description enhancement** before generation (via Claude)
4. **Complete Paradigm API integration** in generated code
5. **Performance optimization** (parallelization with `asyncio.gather()`, reusable HTTP session)
6. **Intelligent post-processing** (complex workflow detection, staggering addition)

---

## 2. Global Architecture

### File Structure

```
generator.py
│
├── Imports (lines 0-8)
│   └── asyncio, logging, re, typing, models, Anthropic, settings
│
├── Utility functions (lines 11-122)
│   ├── detect_workflow_type(description) → str
│   ├── count_api_calls(code) → int
│   ├── fix_fstring_with_braces(code) → str (disabled)
│   └── add_staggering_to_workflow(code, description) → str
│
├── WorkflowGenerator class (lines 124-3389)
│   ├── __init__()
│   ├── generate_workflow(description, name, context) → Workflow
│   ├── _generate_code(description, context) → str
│   ├── _clean_generated_code(code) → str
│   ├── enhance_workflow_description(raw_description) → Dict
│   └── _validate_code(code) → Dict[str, Any]
│
└── Global instance (lines 3392-3393)
    └── workflow_generator = WorkflowGenerator()
```

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      USER REQUEST                           │
│  "Analyze 5 resumes against a job posting"                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              enhance_workflow_description()                  │
│  • Enhances description via Claude Sonnet 4                 │
│  • Breaks down into detailed steps (STEP 1, 2, 3...)       │
│  • Detects ambiguities and asks questions                   │
│  • Identifies parallelization opportunities                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  generate_workflow()                         │
│  • Creates Workflow object                                   │
│  • Launches retry loop (max 3 attempts)                     │
│  • Calls _generate_code()                                    │
│  • Validates with _validate_code()                           │
│  • Post-processing (staggering if needed)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    _generate_code()                          │
│  • Sends description + system prompt (~2900 lines) to       │
│    Claude Sonnet 4 (claude-sonnet-4-20250514)               │
│  • max_tokens=15000 for complete code                        │
│  • Cleans markdown with _clean_generated_code()             │
│  • Logs raw and cleaned code                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   _validate_code()                           │
│  • Compiles Python (SyntaxError detection)                   │
│  • Checks for execute_workflow() presence                    │
│  • Verifies async def                                        │
│  • Checks required imports (asyncio, aiohttp)               │
│  • Saves failed code to /tmp on error                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                   ┌─────┴──────┐
                   │   Valid?   │
                   └─────┬──────┘
                         │
            ┌────────────┼────────────┐
            │ YES                     │ NO
            ▼                         ▼
    ┌──────────────┐         ┌───────────────────┐
    │   SUCCESS    │         │  Retry with error  │
    │ Code ready   │         │  (max 3 times)     │
    └──────────────┘         └───────────┬────────┘
                                         │
                                         └──────┐
                                                │
                    ┌───────────────────────────┘
                    │
                    ▼
         Adds previous_error to context
         Relaunches _generate_code() with context
```

### Dependencies

```python
# External imports
from anthropic import Anthropic  # Claude API calls
from ..config import settings     # Configuration (API keys)
from .models import Workflow      # Workflow data model

# Standard libraries
import asyncio                    # Asynchronous programming
import logging                    # Logs
import re                         # Regular expressions
from typing import Optional, Dict, Any  # Type hints
```

---

## 3. Post-processing Utility Functions

These functions are called **after** initial code generation to apply automatic optimizations and corrections.

### 3.1 `detect_workflow_type(description: str) → str`

**Location**: Lines 15-59

**Goal**: Automatically classify workflow type to choose appropriate APIs.

**Algorithm**:

```python
def detect_workflow_type(description: str) -> str:
    description_lower = description.lower()

    # Keywords indicating structured data extraction
    extraction_keywords = [
        'cv', 'resume', 'curriculum vitae', 'curricul',
        'form', 'formulaire', 'application',
        'invoice', 'facture', 'receipt', 'reçu',
        'extract', 'extraire', 'parse', 'parsing',
        'field', 'champ', 'structured', 'structuré',
        'candidat', 'candidate', 'recrutement', 'recruitment',
        'contract', 'contrat',
        'fiche', 'profil', 'profile'
    ]

    # Keywords indicating document summarization
    summarization_keywords = [
        'summarize', 'résumer', 'synthèse', 'synthesis',
        'long document', 'rapport', 'report',
        'research paper', 'article', 'white paper',
        'analyse approfondie', 'deep analysis',
        'comprehensive review'
    ]

    # Count matches
    extraction_score = sum(1 for kw in extraction_keywords if kw in description_lower)
    summarization_score = sum(1 for kw in summarization_keywords if kw in description_lower)

    # Decision logic
    if extraction_score > 0 and extraction_score > summarization_score:
        return "extraction"
    elif summarization_score > extraction_score:
        return "summarization"
    else:
        # Default: extraction (faster, more reliable)
        return "extraction"
```

**Usage**: Currently defined but not actively used in generation. Can be used for future optimizations or routing decisions.

---

### 3.2 `count_api_calls(code: str) → int`

**Location**: Lines 61-78

**Goal**: Count Paradigm API calls in generated code to detect complex workflows.

**Detected patterns**:

```python
patterns = [
    r'await\s+paradigm_client\.\w+\(',   # await paradigm_client.method(
    r'paradigm_client\.\w+\([^)]+\)'     # paradigm_client.method(args)
]

total_calls = 0
for pattern in patterns:
    matches = re.findall(pattern, code)
    total_calls += len(matches)

return total_calls
```

**Trigger threshold**: **40 API calls or more** → complex workflow requiring staggering

**Usage**: Called by `add_staggering_to_workflow()` to detect complex workflows.

---

### 3.3 `fix_fstring_with_braces(code: str) → str`

**Location**: Lines 80-87

**Status**: **DISABLED** (returns code unchanged)

```python
def fix_fstring_with_braces(code: str) -> str:
    """
    Disabled - too complex to reliably fix f-strings with regex.
    We now rely on improved instructions to Claude to avoid this problem.
    """
    # Does nothing - lets validation catch errors and retry with context
    return code
```

**Reason for disabling**: Attempts at automatic f-string correction with regex caused more problems than they solved.

**Adopted solution**: **Strict instructions to Claude** (lines 223-230 of system prompt) to use `.format()` instead of f-strings.

---

### 3.4 `add_staggering_to_workflow(code: str, description: str) → str`

**Location**: Lines 89-122

**Goal**: Add delays (staggering) between API calls for complex workflows to avoid overload and timeouts.

**Implementation**:

```python
def add_staggering_to_workflow(code: str, description: str) -> str:
    api_call_count = count_api_calls(code)

    if api_call_count < 40:
        # Not a complex workflow, no staggering needed
        return code

    logger.info(f"🔧 Post-processing: Detected complex workflow ({api_call_count} API calls)")
    logger.info(f"   Adding staggering to prevent API overload")

    staggering_note = '''
# ⚠️ Post-processing note: This workflow has many API calls ({})
# Consider adding delays between call groups to avoid timeouts:
# await asyncio.sleep(2)  # Small delay between API call groups
'''.format(api_call_count)

    # Insert note after imports
    if "import asyncio" in code:
        code = code.replace("import asyncio", f"import asyncio{staggering_note}")

    logger.info(f"✅ Post-processing: Added staggering guidance for {api_call_count} API calls")

    return code
```

**Trigger threshold**: 40 API calls or more

**Implementation note**: Currently adds an instructive comment. A future version could parse the Python AST and automatically insert `await asyncio.sleep(2)` between `asyncio.gather()` blocks.

---

## 4. WorkflowGenerator Class

### 4.1 Initialization

**Location**: Lines 124-127

```python
class WorkflowGenerator:
    def __init__(self):
        self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
```

**Configuration**:
- **Model**: claude-sonnet-4-20250514 (Claude Sonnet 4)
- **API Key**: Loaded from `settings.anthropic_api_key`

---

### 4.2 `generate_workflow()` - Main Method

**Location**: Lines 128-201

**Signature**:

```python
async def generate_workflow(
    self,
    description: str,
    name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Workflow
```

**Complete process** (summary):

1. **Workflow creation**: `Workflow` object with status "generating"
2. **Retry loop**: Up to 3 attempts
3. **Generation**: Call `_generate_code()` with description + context
4. **Post-processing**: `fix_fstring_with_braces()` (currently no-op)
5. **Validation**: `_validate_code()` checks syntax and structure
6. **Error feedback**: Adds `previous_error` to context for intelligent retry
7. **Final status**: "ready" if success, "failed" if failure after 3 attempts

**Retry mechanism code** (lines 152-196):

```python
# Retry mechanism for code generation (up to 3 attempts)
max_retries = 3
last_error = None

for attempt in range(max_retries):
    try:
        # Generate code via Anthropic API
        generated_code = await self._generate_code(description, context)

        # Fix f-strings with braces BEFORE validation
        generated_code = fix_fstring_with_braces(generated_code)

        # Validate generated code
        validation_result = await self._validate_code(generated_code)

        if validation_result["valid"]:
            # Success! Valid code
            workflow.generated_code = generated_code
            workflow.update_status("ready")
            return workflow
        else:
            # Validation failed, prepare for retry
            last_error = validation_result['error']
            if attempt < max_retries - 1:
                # Add error context for next attempt
                if context is None:
                    context = {}
                context['previous_error'] = f"Previous attempt had syntax error: {last_error}"
                continue
```

---

### 4.3 `_generate_code()` - Generation via Claude

**Location**: Lines 202-2551

**Signature**:

```python
async def _generate_code(self, description: str, context: Optional[Dict[str, Any]] = None) -> str
```

**Structure**:

1. **System prompt definition** (lines 206-2497): ~2900 lines of documentation
2. **User prompt construction** (lines 2499-2509)
3. **Anthropic API call** (lines 2511-2517)
4. **Code extraction and cleaning** (lines 2519-2534)
5. **Post-processing** (lines 2536-2547)

**API call**:

```python
response = self.anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=15000,  # Increased for complete code generation
    system=system_prompt,
    messages=[{"role": "user", "content": enhanced_description}]
)

code = response.content[0].text

# Log raw code for debugging
logger.info("🔧 RAW GENERATED CODE:")
logger.info("=" * 50)
logger.info(code)
logger.info("=" * 50)

# Clean code - remove markdown formatting if present
code = self._clean_generated_code(code)
```

**User prompt**:

```python
enhanced_description = f"""
Workflow Description: {description}
Additional Context: {context or 'None'}

Generate a complete, self-contained workflow that:
1. Includes all necessary imports and API client classes
2. Implements the execute_workflow function with the exact logic described
3. Can be copy-pasted and run independently on any server
4. Handles the workflow requirements exactly as specified
5. MANDATORY: If the workflow uses documents, implement the if/else pattern for attached_file_ids
"""
```

---

### 4.4 `_clean_generated_code()` - Code Cleaning

**Location**: Lines 2553-2571

**Goal**: Remove Markdown formatting and ensure correct structure.

```python
def _clean_generated_code(self, code: str) -> str:
    # Remove markdown code blocks
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]

    # Remove leading/trailing whitespace
    code = code.strip()

    # Ensure execute_workflow is async
    if "def execute_workflow(" in code and "async def execute_workflow(" not in code:
        code = code.replace("def execute_workflow(", "async def execute_workflow(")

    return code
```

**Applied corrections**:

1. Extract code from markdown blocks (\`\`\`python ... \`\`\`)
2. Remove whitespace
3. Convert `def execute_workflow` → `async def execute_workflow` if needed

---

### 4.5 `enhance_workflow_description()` - AI Enhancement

**Location**: Lines 2572-3339

**Signature**:

```python
async def enhance_workflow_description(self, raw_description: str) -> Dict[str, Any]
```

**Goal**: Transform a brief user description into a detailed specification with clear steps, ambiguity detection, and parallelization opportunities.

**Return**:

```python
{
    "enhanced_description": "STEP 1: ...\n---\nSTEP 2: ...",
    "questions": [],  # Now embedded in each step
    "warnings": []    # Now embedded in each step
}
```

**Enhancement prompt** (lines 2583-3315): ~730 lines of instructions including:

- **Language rules**: Preserve original language (French/English) exactly
- **Available APIs**: Paradigm tools documentation with use cases
- **Mandatory parallelization**: Automatic detection of independent operations
- **Ambiguity detection**: Identification of vague terms ("reference", "date", "amount")
- **Output format**: STEP X + QUESTIONS AND LIMITATIONS structure
- **Professional Markdown formatting**: Visual separators, hierarchy, emojis

**Enhancement example**:

Input: `"Analyze 5 resumes against a job posting"`

Output:
```
STEP 1: Wait for complete indexing of all uploaded files (5 resumes + 1 job posting)...
QUESTIONS AND LIMITATIONS: None
---
STEP 2a: Extract information from first resume (CAN RUN IN PARALLEL with 2b, 2c, 2d, 2e)
QUESTIONS AND LIMITATIONS: None
---
STEP 3: Compile and clean results...
QUESTIONS AND LIMITATIONS: None
```

---

### 4.6 `_validate_code()` - Syntax Validation

**Location**: Lines 3340-3390

**Implementation**:

```python
async def _validate_code(self, code: str) -> Dict[str, Any]:
    try:
        # Check for syntax errors
        compile(code, '<string>', 'exec')

        # Check for required function
        if 'def execute_workflow(' not in code:
            return {"valid": False, "error": "Missing execute_workflow function"}

        # Check for async definition
        if 'async def execute_workflow(' not in code:
            return {"valid": False, "error": "execute_workflow must be async"}

        # Check required imports
        required_imports = ['import asyncio', 'import aiohttp']
        for imp in required_imports:
            if imp not in code:
                return {"valid": False, "error": f"Missing required import: {imp}"}

        return {"valid": True, "error": None}

    except SyntaxError as e:
        # Save failed code for debugging to /tmp/
        # ...
        return {"valid": False, "error": f"Syntax error: {str(e)}"}
```

**Performed checks**:

1. **Python compilation**: `compile(code, '<string>', 'exec')` detects SyntaxError
2. **Required function**: Presence of `def execute_workflow(`
3. **Async definition**: `async def execute_workflow(`
4. **Required imports**: `import asyncio`, `import aiohttp`

**Error handling**: If SyntaxError, saves failed code to `/tmp/workflow_failed_YYYYMMDD_HHMMSS.py`.

---

## 5. Integrated ParadigmClient Template

The `ParadigmClient` template is **embedded in the system prompt** (lines 247-1198) and copied as-is into each generated workflow.

### Main Methods

#### 5.1 Session Management (5.55x faster)

```python
async def _get_session(self) -> aiohttp.ClientSession:
    '''
    Reusing the same session across multiple requests provides a 5.55x
    performance improvement by avoiding connection setup overhead on each call.

    Official benchmark (Paradigm docs):
    - With session reuse: 1.86s for 20 requests
    - Without session reuse: 10.33s for 20 requests
    '''
    if self._session is None or self._session.closed:
        self._session = aiohttp.ClientSession()
        logger.debug("🔌 Created new aiohttp session")
    return self._session
```

#### 5.2 `document_search()` - Semantic Search

**Signature**:

```python
async def document_search(
    self,
    query: str,
    file_ids: Optional[List[int]] = None,
    workspace_ids: Optional[List[int]] = None,
    chat_session_id: Optional[str] = None,
    model: Optional[str] = None,
    company_scope: bool = False,
    private_scope: bool = True,
    tool: str = "DocumentSearch",
    private: bool = True
) -> Dict[str, Any]
```

**Use cases**:
- Fast workspace search
- Specific field extraction from uploaded files
- Search with vision OCR (tool="VisionDocumentSearch") for scanned documents

#### 5.3 `analyze_documents_with_polling()` - Complete Analysis

**Performance**: ~20-30 seconds, comprehensive results

**Process**:

1. Start analysis via `document_analysis_start()`
2. Poll results every 5 seconds
3. Return result when status = "completed"
4. Timeout after 300 seconds (configurable)

**⚠️ CRITICAL**: NEVER in parallel! Always process sequentially.

#### 5.4 `chat_completion()` - Structured Extraction

**3 extraction modes**:

1. **`guided_choice`**: Strict classification
   ```python
   status = await client.chat_completion(
       prompt="Is document compliant?",
       guided_choice=["compliant", "non_compliant", "incomplete"]
   )
   ```

2. **`guided_regex`**: Guaranteed specific formats
   ```python
   siret = await client.chat_completion(
       prompt="Extract SIRET",
       guided_regex=r"\d{14}"
   )
   ```

3. **`guided_json`**: Guaranteed valid JSON
   ```python
   data = await client.chat_completion(
       prompt="Extract invoice data",
       guided_json={"type": "object", "properties": {...}}
   )
   ```

#### 5.5 Additional Methods

- **`upload_file()`**: Upload files to Paradigm
- **`get_file()`**: Retrieve metadata and status
- **`wait_for_embedding()`**: Wait for complete indexing (critical for PDFs!)
- **`filter_chunks()`**: Filter chunks by relevance
- **`get_file_chunks()`**: Retrieve all chunks
- **`query()`**: Extraction without AI generation (~30% faster)
- **`analyze_image()`**: Visual image analysis
- **`delete_file()`**: Delete files

---

## 6. Massive Prompt System

### 6.1 System Prompt Size and Structure

**Location**: Lines 206-2497
**Size**: **~2900 lines** of documentation and instructions (81% of the file!)

**Main structure**:

```
system_prompt = """
├── CRITICAL INSTRUCTIONS (lines 208-231)
│   ├── Output format (Python code only)
│   ├── Required structure (async def execute_workflow)
│   ├── String formatting rules (f-strings FORBIDDEN)
│   └── Complete implementation (NO PLACEHOLDERS)
│
├── REQUIRED STRUCTURE (lines 232-1216)
│   ├── Standard imports
│   ├── Configuration (env variables)
│   └── COMPLETE ParadigmClient template (950 lines)
│
├── LIBRARY RESTRICTIONS (lines 1218-1224)
│   └── Only standard Python libraries + aiohttp
│
├── MISSING VALUES DETECTION (lines 1228-1409)
│   ├── Missing value patterns
│   ├── is_value_missing() function
│   └── Correct comparison workflow
│
├── MANDATORY FILE HANDLING CODE (lines 1410-1589)
│   ├── Check attached_file_ids (globals + builtins)
│   ├── Wait for embedding with wait_for_embedding() (MANDATORY!)
│   └── if/else pattern for uploaded files vs workspace
│
├── QUERY FORMULATION BEST PRACTICES (lines 1589-1637)
│   ├── Be specific with field names
│   ├── Include expected formats explicitly
│   └── Use real document keywords
│
├── PARALLELIZATION (lines 1775-1914)
│   ├── When to parallelize (document_search, chat_completion)
│   ├── When NOT to parallelize (analyze_documents_with_polling)
│   └── Correct vs incorrect examples
│
├── API RATE LIMITING (lines 1915-1976)
│   ├── MAX 5 calls per batch
│   └── Mandatory delays between batches
│
├── CODE SIMPLICITY PRINCIPLES (lines 2208-2330)
│   ├── Prefer API intelligence vs custom code
│   ├── Robust data access (isinstance, .get())
│   └── Minimize custom utility functions
│
└── FINAL INSTRUCTION (line 2497)
    └── NO PLACEHOLDER CODE - FULLY IMPLEMENTED
"""
```

### 6.2 Key Critical Instructions

#### Absolute f-strings Prohibition

**Lines 223-231**:

```
*** CRITICAL STRING FORMATTING RULE - YOU MUST FOLLOW THIS EXACTLY:
    - NEVER EVER use f-strings (f"..." or f'''...''') ANYWHERE in the code
    - ALWAYS use .format() method for ALL string interpolation
    - Example CORRECT: "Bearer {}".format(self.api_key)
    - Example WRONG: f"Bearer {self.api_key}"
    - This prevents ALL syntax errors with curly braces ***
```

**Reason**: F-strings with braces in generated code cause SyntaxErrors that are difficult to fix automatically.

#### Fully Implemented Code (NO PLACEHOLDERS)

**Lines 213-217**:

```
5. *** NEVER USE 'pass' OR PLACEHOLDER COMMENTS - IMPLEMENT ALL FUNCTIONS COMPLETELY ***
6. *** EVERY FUNCTION MUST BE FULLY IMPLEMENTED WITH WORKING CODE ***
7. *** NO STUB FUNCTIONS - ALL CODE MUST BE EXECUTABLE AND FUNCTIONAL ***
```

#### Mandatory Parallelization

**Lines 216-221**:

```
8. *** ALWAYS USE asyncio.gather() FOR INDEPENDENT PARALLEL TASKS - IMPROVES PERFORMANCE 3-10x ***
   *** CRITICAL: analyze_documents_with_polling() requires BATCH PROCESSING (max 2-3 parallel) ***
   *** Safe to fully parallelize: document_search(), chat_completion(), upload_file() ***
```

#### Mandatory Pattern for Uploaded Files

**Lines 1410-1589**: Complete 180-line code to copy VERBATIM.

**Critical pattern**:

```python
# Check for uploaded files in both globals() and builtins
import builtins
attached_files = None
if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
    attached_files = globals()['attached_file_ids']
elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
    attached_files = builtins.attached_file_ids

if attached_files:
    # User uploaded files - MANDATORY: Wait for embedding FIRST
    file_id = int(attached_files[0])
    try:
        file_info = await paradigm_client.wait_for_embedding(
            file_id=file_id,
            max_wait_time=300,
            poll_interval=2
        )
    except Exception as e:
        await asyncio.sleep(90)  # Fallback wait
else:
    # No uploaded files - search workspace
    search_results = await paradigm_client.document_search(query)
```

**Criticality**: This pattern is **MANDATORY** - without it, workflows fail with uploaded documents.

---

## 7. Generation and Retry Process

### 7.1 Complete Flow with Retry

```
ATTEMPT 1
└─> _generate_code(description, {})
    └─> Send system prompt (~2900 lines)
        └─> Claude Sonnet 4 generates code
            └─> _clean_generated_code()
                └─> _validate_code()
                    ├─> Valid? → SUCCESS
                    └─> Invalid? → ATTEMPT 2

ATTEMPT 2 (with error context)
├─> context['previous_error'] = "Previous attempt had syntax error: ..."
└─> _generate_code(description, context)
    └─> Claude receives error feedback
        └─> Generates corrected code
            └─> _validate_code()
                ├─> Valid? → SUCCESS
                └─> Invalid? → ATTEMPT 3

ATTEMPT 3 (last chance)
└─> If still fails → Exception raised
    └─> workflow.status = "failed"
```

### 7.2 Retry Mechanism with Feedback

**Key points**:

1. **3 maximum attempts**
2. **Error context**: `context['previous_error']` passed to Claude
3. **Auto-correction**: Claude understands and fixes its errors
4. **Failure logging**: Failed code saved to `/tmp/`

**Auto-correction example**:

Attempt 1 (error):
```python
headers = {"Authorization": f"Bearer {api_key}"}  # ❌ SyntaxError
```

Attempt 2 (corrected):
```python
headers = {"Authorization": "Bearer {}".format(api_key)}  # ✅ Correct
```

---

## 8. Description Enhancement Mechanism

### 8.1 Goal

Transform a brief description into a detailed specification ready for generation.

**Input**: `"Analyze 5 resumes against a job posting"`

**Output**: Breakdown into steps STEP 1, STEP 2a, STEP 2b, etc. with complete details.

### 8.2 Enhancement Prompt

**Location**: Lines 2583-3315 (~730 lines)

**Critical rules**:

1. **Language preservation**: NEVER translate (French stays French, English stays English)
2. **Mandatory parallelization**: Automatically detect independent operations
3. **Ambiguity detection**: Ask questions for "reference", "date", "amount", etc.
4. **Output format**: PLAIN TEXT (not JSON!) with STEP + QUESTIONS structure
5. **Professional Markdown**: Visual separators (%%%), emojis, clear hierarchy

**Example generated question**:

```
QUESTIONS AND LIMITATIONS:
⚠️ AMBIGUITY DETECTED - Clarification needed:

1. **"reference number"** is ambiguous:
   - Do you mean the procedure number (e.g., 22U012)?
   - Do you mean the market number (e.g., 617529)?
   - In which section of each document?
   - What format (numeric, alphanumeric)?
```

---

## 9. Validation and Error Detection

### 9.1 Compilation Checks

```python
async def _validate_code(self, code: str) -> Dict[str, Any]:
    try:
        # 1. Check for syntax errors
        compile(code, '<string>', 'exec')

        # 2. Check for execute_workflow()
        if 'def execute_workflow(' not in code:
            return {"valid": False, "error": "Missing execute_workflow function"}

        # 3. Check for async definition
        if 'async def execute_workflow(' not in code:
            return {"valid": False, "error": "execute_workflow must be async"}

        # 4. Check required imports
        required_imports = ['import asyncio', 'import aiohttp']
        for imp in required_imports:
            if imp not in code:
                return {"valid": False, "error": f"Missing required import: {imp}"}

        return {"valid": True, "error": None}

    except SyntaxError as e:
        # Save failed code to /tmp/
        return {"valid": False, "error": f"Syntax error: {str(e)}"}
```

### 9.2 Failed Code Saving

**Path**: `/tmp/workflow_failed_YYYYMMDD_HHMMSS.py` (Unix) or Windows equivalent

**Advantage**: Allows manual debugging of generation failures.

---

## 10. Optimizations and Best Practices

### 10.1 Reusable HTTP Session (5.55x faster)

**Official Paradigm benchmark**:
- Without reuse: 10.33s for 20 requests
- With reuse: **1.86s for 20 requests** (5.55x)

**Implementation**:

```python
async def _get_session(self) -> aiohttp.ClientSession:
    if self._session is None or self._session.closed:
        self._session = aiohttp.ClientSession()
    return self._session
```

### 10.2 Parallelization with asyncio.gather()

**Performance**: 3-10x improvement

**Example**:

```python
# Sequential: 3 tasks × 5s = 15s total
result1 = await task1()
result2 = await task2()
result3 = await task3()

# Parallel: max(5, 5, 5) = 5s total (3x faster!)
result1, result2, result3 = await asyncio.gather(task1(), task2(), task3())
```

### 10.3 API Batching (max 5 calls per batch)

**Correct pattern**:

```python
# Batch 1: First 5 queries
batch1_tasks = [paradigm_client.document_search(q) for q in queries[:5]]
batch1_results = await asyncio.gather(*batch1_tasks)
await asyncio.sleep(0.5)  # MANDATORY DELAY

# Batch 2: Next 5 queries
batch2_tasks = [paradigm_client.document_search(q) for q in queries[5:10]]
batch2_results = await asyncio.gather(*batch2_tasks)
await asyncio.sleep(0.5)  # MANDATORY DELAY

all_results = batch1_results + batch2_results
```

**Rules**:
1. MAX 5 parallel calls per batch
2. `asyncio.sleep(0.5)` between batches (standard ops)
3. `asyncio.sleep(1)` between batches (heavy ops: VisionDocumentSearch, upload)

### 10.4 Robust Data Access (isinstance, .get())

**Defensive pattern**:

```python
# ✅ CORRECT - Type checking before access
if isinstance(results, dict):
    documents = results.get('documents', [])
elif isinstance(results, list):
    documents = results
else:
    documents = []

for doc in documents:
    if isinstance(doc, dict):
        doc_id = doc.get('id', 'unknown')
        doc_name = doc.get('filename', 'Document {}'.format(doc_id))
```

**Principle**: Always check types with `isinstance()` and use `.get()` with defaults.

---

## 11. Critical Points and Mandatory Patterns

### 11.1 Uploaded Files Pattern (MANDATORY)

**Prompt location**: Lines 1410-1589 (180 lines)

**Mandatory code**:

```python
import builtins
attached_files = None
if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
    attached_files = globals()['attached_file_ids']
elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
    attached_files = builtins.attached_file_ids

if attached_files:
    # MANDATORY: Wait for embedding!
    file_id = int(attached_files[0])
    file_info = await paradigm_client.wait_for_embedding(file_id=file_id, max_wait_time=300)
    # Then use the file...
else:
    # Search workspace
    search_results = await paradigm_client.document_search(query)
```

**Why mandatory**: PDFs require 30-120s OCR processing. Without waiting → "document not found" error.

---

### 11.2 Prohibition of analyze_documents_with_polling() in Parallel

**Critical rule**:

```
❌ WRONG: await asyncio.gather(*[analyze_documents_with_polling(...) for doc in docs])
✅ CORRECT: for doc in docs: result = await analyze_documents_with_polling(...)
```

**Reason**: Heavy endpoint (deep analysis) → timeouts if parallelized.

---

### 11.3 Critical Scopes for file_ids

**Rule**:

```python
# ✅ CORRECT: Target specific file only
content = await document_search(query, file_ids=[doc_id], company_scope=False, private_scope=False)

# ❌ WRONG: Returns ALL private collection + specified file!
content = await document_search(query, file_ids=[doc_id])
```

**Explanation**: By default, `document_search()` searches entire private collection even if `file_ids` specified.

---

### 11.4 Preserving file_id → result Mapping

**Problem**: When processing multiple files in parallel, mapping is lost.

**Solution**: Store `(file_id, task)` tuples:

```python
# ✅ CORRECT
file_search_tasks = []
for file_id in attached_files:
    task = paradigm_client.document_search(query, file_ids=[int(file_id)])
    file_search_tasks.append((file_id, task))  # Keep mapping!

file_search_results = []
for i in range(0, len(file_search_tasks), 5):
    batch = file_search_tasks[i:i+5]
    batch_tasks = [task for file_id, task in batch]
    batch_results = await asyncio.gather(*batch_tasks)
    for j, result in enumerate(batch_results):
        file_id = batch[j][0]  # Get file_id from tuple
        file_search_results.append((file_id, result))
```

---

### 11.5 Missing Value Detection Before Comparison

**Problem**: API returns "Not found" → comparing 2 "Not found" = false positive.

**Solution**: `is_value_missing()` function + check before comparison:

```python
def is_value_missing(value: str) -> bool:
    if not value or not value.strip():
        return True
    missing_indicators = ["not found", "no information", "no data available", ...]
    value_lower = value.lower()
    return any(indicator in value_lower for indicator in missing_indicators)

# Check for missing BEFORE comparison
raw_value_dc4 = step_search_dc4.get("answer", "")
raw_value_avis = step_search_avis.get("answer", "")

dc4_missing = is_value_missing(raw_value_dc4)
avis_missing = is_value_missing(raw_value_avis)

if dc4_missing or avis_missing:
    status = "WARNING Missing data"
else:
    # Both values exist, now compare
    comparison = await chat_completion("Compare...")
    status = "OK Compliant" if "identical" in comparison.lower() else "ERROR Non-compliant"
```

**Key principle**: Check `is_value_missing()` on raw values IMMEDIATELY after extraction, BEFORE any normalization or comparison.

---

## Conclusion

The `generator.py` is a sophisticated system with the following characteristics:

### Metrics

- **3393 lines** of total code
- **~2900 lines** of system prompts (81% of file)
- **950 lines** of ParadigmClient template
- **730 lines** of enhancement prompt
- **30+ API methods** Paradigm documented
- **3x retry** with error context
- **5.55x performance** with reusable session
- **3-10x performance** with parallelization

### Strengths

- ✅ Automatic retry with auto-correction
- ✅ Complete and optimized Paradigm client integrated
- ✅ Very detailed system prompt for code quality
- ✅ Post-processing for complex workflows
- ✅ Structured extraction support (guided_*)
- ✅ Precisely documented mandatory patterns

### Improvement Areas

- 🔄 More advanced semantic validation
- 🔄 Automatic staggering (AST parser)
- 🔄 System prompt modularization
- 🔄 Automatic unit tests of generated code

---

**Maintained by**: LightOn Workflow Builder Team
**Last updated**: January 24, 2025
**Based on**: Complete reading of `api/workflow/generator.py` (3393 lines)
