# LightOn Workflow Builder

Automated workflow generation and execution application using Anthropic Claude API and LightOn Paradigm API.

## 🚀 Quick Start with Docker

```bash
# 1. Clone the repository
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-

# 2. Configure API keys
cp .env.example .env
# Edit .env and add your keys:
# ANTHROPIC_API_KEY=your_anthropic_key
# LIGHTON_API_KEY=your_lighton_key

# 3. Start with Docker Compose
docker-compose up --build

# 4. Access the application
# Frontend: http://localhost:3000
# API Backend: http://localhost:8000/docs
```

**✅ Docker Benefits**:
- Minimal configuration
- Isolated and reproducible environment
- Production-ready (deployable on any server with Docker)
- No serverless function limits

## 🔧 Other Deployment Options

### Vercel Option (Requires Pro Plan)

⚠️ **Warning**: The workflow builder requires Vercel Pro ($20/month) to function properly.

**Why Pro is required**:
- **Python Runtime**: The workflow builder uses Python/FastAPI (not available in free tier)
- **Execution Time**: Workflow generation can take 30-60s+ (free tier limited to 10s)
- **Function Count**: The builder uses multiple API endpoints (limit quickly reached in free tier)

**Vercel Deployment**:
1. Connect your GitHub/GitLab repo to Vercel
2. Add environment variables in Vercel:
   - `ANTHROPIC_API_KEY`
   - `LIGHTON_API_KEY`
3. Link Vercel KV (Storage):
   - `KV_REST_API_URL` and `KV_REST_API_TOKEN` variables are created automatically
   - The code detects and uses these variables automatically
4. Deploy: `git push` (automatic)

**Note**: The code automatically supports both conventions:
- Vercel KV variables (automatically created when linking)
- Direct Upstash variables (manual configuration)

### Manual Python Option

Deploy on your own infrastructure (VPS, cloud VM, on-premises server).

```bash
# 1. Clone and install
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
nano .env  # Add ANTHROPIC_API_KEY and LIGHTON_API_KEY

# 3. Start the server
python -m uvicorn api.index:app --host 0.0.0.0 --port 8000

# Or with more production options
uvicorn api.index:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

**Nginx Configuration (optional)**:
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

## 📋 Prerequisites

1. **Docker Desktop** installed (for quick start)
2. **API Keys**:
   - Anthropic API key (for workflow generation)
   - LightOn Paradigm API key (for workflow execution)

## ✨ Key Features

### 1. AI-Powered Workflow Generation

- **Natural Language to Code**: Describe workflows in natural language, Claude Sonnet 4 generates executable Python code
- **Description Enhancement**: Automatic improvement of user descriptions before generation
- **Auto-Validation with Retry**: Up to 3 attempts with contextual error feedback for self-correction
- **Intelligent Post-Processing**: Automatic correction of f-string syntax errors
- **Complexity Detection**: Automatic identification of complex workflows (>40 API calls) with rate limiting management
- **Performance Optimization**: Automatic parallelization via asyncio.gather() for independent operations

### 2. Complete Paradigm API Integration

**Document Search and Analysis:**
- `document_search()` - Semantic search in your documents
- `search_with_vision_fallback()` - Automatic fallback to VisionDocumentSearch for scanned documents
- `analyze_documents_with_polling()` - In-depth analysis with automatic result retrieval
- `chat_completion()` - AI completion with structured data extraction:
  - **guided_choice**: Forced selection from predefined list (classification)
  - **guided_regex**: Guaranteed format (SIRET, IBAN, phone numbers, dates, amounts)
  - **guided_json**: Structured JSON extraction

**File Management:**
- `upload_file()` - Upload to Paradigm with automatic indexing
- `wait_for_embedding()` - Automatic wait for indexing (5min timeout)
- `get_file()` / `delete_file()` - Complete lifecycle management
- `get_file_chunks()` - Retrieve document chunks

**Advanced APIs:**
- `filter_chunks()` - Relevance filtering (+20% accuracy)
- `query()` - Chunk extraction without AI synthesis (30% faster)
- `analyze_image()` - AI-powered image analysis

**Performance:**
- Reusable HTTP session (5.55x faster)
- Full async operations support

### 3. Secure Execution

- **Sandboxing**: Restricted execution environment with only secure built-ins
- **Configurable Timeout**: Protection against infinite executions (default 30 min)
- **File Attachments**: Native support for attached files via `attached_file_ids`
- **Secure Injection**: API keys automatically injected at runtime
- **Complete Logging**: Stdout/stderr capture with detailed API tracing
- **Async Support**: Synchronous and asynchronous workflows

### 4. Persistence and Storage

- **Upstash Redis**: Serverless-compatible storage (24h TTL)
- **Vercel KV**: Automatic detection and use of Vercel variables
- **In-Memory Fallback**: Works without Redis if necessary
- **Workflow History**: Storage of executions and results

### 5. Export and Packages

**Workflow Runner (Standalone Package):**
- Dynamic web interface automatically generated by code analysis
- Intelligent field detection (text inputs, file uploads, multiple types)
- Complete FastAPI backend with Paradigm client
- Bilingual documentation (FR/EN)
- Docker-ready configuration
- Integrated PDF export (jsPDF)
- ⚠️ Local dev only (Vercel serverless limit)

**MCP Server Package:**
- Dual-mode MCP server (stdio for Claude Desktop + HTTP for Paradigm)
- Multi-format input support (local paths, file IDs, auto-upload)
- Automatic indexing wait (wait_for_embedding 5min)
- Docker configuration + bearer token auth
- ⚠️ Limitations: 4min Claude Desktop timeout, Paradigm file_ids bug

### 6. Professional PDF Reports

- Automatic vendor-neutral report generation
- Markdown support (headers, lists, tables, bold/italic)
- Structured JSON data display
- Complete metadata (name, description, duration, status)
- Professional typography (ReportLab)

### 7. Modern Web Interface

- **Vanilla JavaScript**: No framework dependencies
- **Drag-and-Drop Upload**: Visual file interface
- **Real-Time Monitoring**: Colored logs with complete API tracing
- **Code Preview**: Generated workflow visualization
- **Downloads**: PDF, Workflow Runner Package, MCP Package
- **Responsive**: Desktop and mobile compatible


## 📖 API Endpoints

### Workflows
- `POST /api/workflows` - Create a workflow from description
- `POST /api/workflows/enhance-description` - Enhance description with AI
- `GET /api/workflows/{id}` - Get workflow details
- `POST /api/workflows/{id}/execute` - Execute a workflow
- `GET /api/workflows/{id}/executions/{exec_id}` - Execution details
- `GET /api/workflows/{id}/executions/{exec_id}/pdf` - Download PDF report
- `POST /api/workflows-with-files` - Create workflow with access to specific files

### Packages (Local only)
- `POST /api/workflow/generate-package/{id}` - Generate Workflow Runner Package (ZIP)
- `POST /api/workflow/generate-mcp-package/{id}` - Generate MCP Server Package (ZIP)

### Files
- `POST /api/files/upload` - Upload file to Paradigm
- `GET /api/files/{id}` - File info (status, size, etc.)
- `DELETE /api/files/{id}` - Delete file

### Health
- `GET /health` - Health check for monitoring
- `GET /` - Web interface (frontend)

### Usage Example

```bash
# 1. Create a workflow
curl -X POST "http://localhost:8000/api/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Analyze uploaded resumes and compare them to a job description",
    "name": "Resume Analysis"
  }'

# 2. Upload files
curl -X POST "http://localhost:8000/api/files/upload" \
  -F "file=@resume1.pdf" \
  -F "collection_type=private"

# 3. Execute workflow with attached files
curl -X POST "http://localhost:8000/api/workflows/{workflow_id}/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "Analyze resumes",
    "attached_file_ids": [123, 124, 125]
  }'
```

## Example Workflow

The system is designed to handle workflows like this example:

**Description**: "User inputs a long prompt with multiple sentences. For each sentence, perform a search using the Paradigm Docsearch tool. Return results formatted as 'Question: [sentence]' followed by 'Answer: [result]'."

**Sample Input**: "What is machine learning? How does artificial intelligence work? What are the benefits of cloud computing?"

**Expected Output**:
```
Question: What is machine learning?
Answer: [Search result about machine learning]

Question: How does artificial intelligence work?
Answer: [Search result about AI]

Question: What are the benefits of cloud computing?
Answer: [Search result about cloud computing benefits]
```

## 🔧 Available APIs in Generated Workflows

Generated workflows have access to a **complete ParadigmClient** with all LightOn Paradigm APIs:

### Document Search and Analysis
- `document_search(query, file_ids=...)` - Semantic search in your documents
- `search_with_vision_fallback(query, file_ids)` - Search with automatic OCR for scanned documents
- `analyze_documents_with_polling(query, document_ids)` - In-depth analysis with automatic result retrieval
- `chat_completion(prompt, guided_choice=..., guided_regex=..., guided_json=...)` - Completion with structured extraction
  - **guided_choice**: Forced selection from predefined list (classification)
  - **guided_regex**: Guaranteed format (SIRET, IBAN, phone, dates, amounts)
  - **guided_json**: Structured JSON extraction with schema

### File Management
- `upload_file(file_content, filename, collection_type=...)` - Upload to Paradigm with auto indexing
- `wait_for_embedding(file_id, timeout=300)` - Auto wait for indexing (5min timeout)
- `get_file(file_id)` / `delete_file(file_id)` - Complete lifecycle management
- `get_file_chunks(file_id)` - Retrieve document chunks

### Advanced APIs
- `filter_chunks(query, chunk_ids, n=...)` - Relevance filtering (+20% accuracy)
- `query(query, collection=...)` - Chunk extraction without AI synthesis (30% faster)
- `analyze_image(image_path_or_url, prompt)` - AI-powered image analysis

### Structured Data Extraction

Workflows can extract data with **format guarantee**:

```python
# SIRET extraction with guaranteed format (14 digits)
siret = await paradigm_client.chat_completion(
    prompt="Extract the SIRET number from the document",
    guided_regex=r"\d{14}"
)

# Strict classification among predefined choices
status = await paradigm_client.chat_completion(
    prompt="Is the document compliant with requirements?",
    guided_choice=["compliant", "non_compliant", "incomplete"]
)

# Structured JSON extraction
invoice_data = await paradigm_client.chat_completion(
    prompt="Extract invoice data",
    guided_json={
        "type": "object",
        "properties": {
            "number": {"type": "string"},
            "amount": {"type": "number"},
            "date": {"type": "string"}
        }
    }
)
```

**Predefined regex patterns included**: SIRET (14 digits), SIREN (9 digits), IBAN, FR phone, ISO dates, EUR amounts, emails.

### Performance
- Reusable HTTP session for all methods (5.55x faster)
- Full async/await operations support

## 📦 Workflow Runner - Standalone Package

The **Workflow Runner** allows exporting a complete workflow as a standalone ZIP package, ready to be deployed to a client.

### Package Generation

**In local development mode only** (endpoint disabled on Vercel):

```bash
# Via API
curl -X POST "http://localhost:8000/api/workflow/generate-package/{workflow_id}" \
  --output workflow-package.zip

# Via web interface
# Click "Download Workflow Package" after workflow creation
```

### Package Contents

The generated ZIP contains a **complete standalone application**:

```
workflow-{name}-{id}.zip
├── frontend/
│   ├── index.html              # Auto-generated dynamic interface
│   ├── config.json             # UI configuration (fields, types, etc.)
│   └── integrated styles       # Responsive CSS
├── backend/
│   ├── main.py                 # FastAPI server
│   ├── workflow_code.py        # Generated workflow code
│   ├── paradigm_client.py      # Complete Paradigm client
│   └── requirements.txt        # Python dependencies
├── docker-compose.yml          # Docker configuration
├── Dockerfile                  # Optimized Docker image
├── README.md (FR)              # French documentation
├── README_EN.md                # English documentation
└── .env.example                # Configuration template
```

### Features

- ✅ **Dynamic UI**: Interface automatically generated by Claude code analysis
- ✅ **Bilingual**: Complete FR + EN documentation
- ✅ **Docker Ready**: `docker-compose up` and it's ready
- ✅ **PDF Export**: Integrated report generation
- ✅ **Standalone**: No dependency on main system
- ✅ **Production Ready**: Optimized Uvicorn configuration

### Client Deployment

```bash
# 1. Extract ZIP
unzip workflow-package.zip
cd workflow-{name}-{id}

# 2. Configure API keys
cp .env.example .env
nano .env  # Add LIGHTON_API_KEY and ANTHROPIC_API_KEY

# 3. Launch with Docker
docker-compose up -d

# 4. Access the interface
# http://localhost:8080
```

### Important Note

⚠️ Package generation is **disabled on Vercel** to stay within the 12 serverless functions limit. Use local development mode to generate packages.

## 🔌 MCP Server Package - Claude Desktop Integration

The **MCP (Model Context Protocol) Package** allows integrating your workflows directly into Claude Desktop or Paradigm via Anthropic's MCP protocol.

### MCP Package Generation

**In local development mode only**:

```bash
# Via web interface
# Click "Download MCP Package" after workflow creation
```

### MCP Package Contents

```
mcp-workflow-{name}.zip
├── server.py                   # MCP server (stdio + HTTP)
├── workflow.py                 # Generated workflow code
├── paradigm_client.py          # Complete Paradigm client
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # Docker configuration
├── Dockerfile                  # Docker image
├── .env.example                # Configuration template
└── README.md                   # Complete documentation
```

### Usage with Claude Desktop

```bash
# 1. Extract package
unzip mcp-workflow-{name}.zip
cd mcp-workflow-{name}

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure Claude Desktop
# Edit %APPDATA%\Claude\claude_desktop_config.json (Windows)
# or ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
```

Add this configuration:

```json
{
  "mcpServers": {
    "your-workflow-name": {
      "command": "python",
      "args": ["C:\\path\\to\\mcp-workflow\\server.py"],
      "cwd": "C:\\path\\to\\mcp-workflow",
      "env": {
        "PARADIGM_API_KEY": "your_paradigm_api_key",
        "PARADIGM_BASE_URL": "https://paradigm.lighton.ai"
      }
    }
  }
}
```

**4. Restart Claude Desktop** - The workflow is now available as a tool!

### Usage with Paradigm (HTTP Mode)

To deploy the MCP server and use it with Paradigm:

```bash
# 1. Deploy on a server with public URL
docker-compose up -d

# 2. In Paradigm Admin → MCP Servers
# Add: https://your-server.com/mcp
# Bearer Token: optional (configured in .env)
```

⚠️ **Known Paradigm Bug**: `file_ids` uploaded via Paradigm interface are not correctly transmitted to MCP workflows. Workaround: use Claude Desktop locally until bug is fixed.

### Limitations

- **Claude Desktop**: 4 minutes maximum timeout per MCP request
  - Limit to 3-5 documents per request
  - For complex workflows, prefer standard Workflow Runner Package
- **Paradigm HTTP**: file_ids transmission bug (being fixed)

## 🧪 Tests

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/test_integration.py

# Docker test
docker-compose up --build
```

## 📁 Project Structure

```
├── api/                          # FastAPI backend
│   ├── index.py                 # Entry point
│   ├── main.py                  # Main FastAPI application
│   ├── config.py                # Configuration and env variables
│   ├── models.py                # Pydantic models (requests/responses)
│   ├── api_clients.py           # HTTP clients Anthropic + Paradigm
│   ├── pdf_generator.py         # PDF report generation
│   └── workflow/                # Workflow module
│       ├── generator.py         # AI code generation
│       ├── executor.py          # Secure execution
│       ├── models.py            # Workflow models
│       ├── package_generator.py # ZIP package generation
│       └── workflow_analyzer.py # Workflow analysis
├── tests/                       # Unit and integration tests
├── index.html                   # Frontend (web interface)
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (DO NOT commit!)
├── docker-compose.yml           # Docker configuration
├── Dockerfile                   # Docker image
└── vercel.json                  # Vercel configuration
```

## 📚 Documentation

- **API Backend**: http://localhost:8000/docs (when server is running)
- **Docker**: See [DOCKER_README.md](DOCKER_README.md)
- **Paradigm API**: https://paradigm.lighton.ai/docs

## 🔒 Security

- **Sandboxed Execution**: Code runs in a restricted environment
- **Timeout Protection**: Executions are time-limited
- **Input Validation**: All inputs are validated
- **Error Handling**: Complete error handling and logging

## 🐛 Troubleshooting

**Problem: "Port already in use"**
- Stop Docker containers: `docker-compose down`
- Check processes on ports: `netstat -ano | findstr :8000`
- If needed, kill processes: `taskkill /F /PID <pid>`

**Problem: "API key not configured"**
- Verify `.env` file exists at project root
- Verify API keys are correct and start with proper prefixes
- Restart Docker: `docker-compose restart`

**Problem: "File not embedded yet"**
- Uploaded files must be indexed before use
- Workflow automatically waits up to 60s
- For custom workflows, use `wait_for_embedding(file_id)`

**Problem: "Workflow execution timeout"**
- Default timeout: 1800s (30 min) - configurable in `config.py`
- For long workflows, increase `max_execution_time` in settings
- Use `asyncio.gather()` to parallelize independent operations

## 📝 Technologies

**Backend**:
- FastAPI (REST API with automatic documentation)
- Python 3.11+
- Pydantic 2.0+ (data validation)
- aiohttp (async HTTP client)
- Upstash Redis / Vercel KV (persistence)

**Frontend**:
- HTML/CSS/JavaScript vanilla (no framework)
- Responsive interface with drag-and-drop
- jsPDF (client-side PDF export in packages)

**AI & Document Processing**:
- Anthropic Claude API (claude-sonnet-4-20250514)
- LightOn Paradigm API (search, analysis, structured extraction)

**Package Generation**:
- ReportLab (server PDF reports)
- Workflow Package Generator (auto-generated dynamic UI)
- MCP Package Generator (Anthropic protocol)

**Deployment**:
- Docker + Docker Compose (recommended)
- Vercel (Pro required)
- Manual Python/Uvicorn

## 🔄 Recent Improvements

**v1.1.0-mcp (January 2025)**:
- ✨ **MCP Server Package**: Claude Desktop and Paradigm integration via MCP protocol
  - Dual-mode server (local stdio + remote HTTP)
  - Multi-format input support (paths, file IDs, auto-upload)
  - Docker configuration with bearer token auth
- ✨ **Workflow Runner Package**: Standalone package with auto-generated UI
  - Claude code analysis for intelligent UI generation
  - Drag-and-drop file support
  - Integrated client-side PDF export
  - Bilingual documentation (FR/EN)

**Main Features**:
- ✅ **Structured Extraction**: `guided_choice`, `guided_regex`, `guided_json`
  - Guaranteed formats: SIRET, SIREN, IBAN, FR phones, dates, amounts
  - Strict classification with predefined choices
  - JSON extraction with schema
- ✅ **Description Enhancement**: Auto improvement of user descriptions
- ✅ **Auto-Validation**: Automatic retry (3 attempts) with error feedback
- ✅ **Post-Processing**: Auto correction of f-string syntax errors
- ✅ **Complexity Detection**: Complex workflow identification (>40 API calls)
- ✅ **Performance**: Auto parallelization via asyncio.gather()
- ✅ **Paradigm APIs**: Full support (Vision OCR, filter_chunks, analyze_image, etc.)
- ✅ **Session Reuse**: Reusable HTTP client (5.55x faster)
