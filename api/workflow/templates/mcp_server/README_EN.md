# {WORKFLOW_NAME} - MCP Server

MCP (Model Context Protocol) server exposing the "{WORKFLOW_NAME}" workflow as a reusable tool.

## Description

{WORKFLOW_DESCRIPTION}

## Integration Status

- ✅ **Claude Desktop**: Works perfectly (local stdio mode)
- ⚠️ **LightOn Paradigm**: Installation successful but known execution bug (uploaded file_ids are not transmitted to the workflow)

---

## 🌐 PART 1: Deployment for LightOn Paradigm

### Prerequisites

- Server with Python 3.10+ and public access (e.g., Render, Railway, Fly.io)
- LightOn Paradigm API key
- Bearer token to secure MCP access (optional but recommended)

### Step 1: Deploy HTTP server on a public URL

The MCP HTTP server must be accessible from the Internet for Paradigm to call it.

**Option A: Deploy on Render.com**

1. Create an account on https://render.com
2. Create a new "Web Service"
3. Connect your Git repository or upload this folder
4. Configuration:
   ```
   Build Command: pip install mcp aiohttp python-dotenv uvicorn
   Start Command: python -m http_server --host 0.0.0.0 --port 10000
   ```
5. Environment variables:
   ```
   PARADIGM_API_KEY=your_api_key
   PARADIGM_BASE_URL=https://paradigm.lighton.ai
   MCP_BEARER_TOKEN=a_secure_secret_token
   ```
6. Deploy and note the public URL (e.g., `https://your-app.onrender.com`)

**Option B: Deploy on Railway**

1. Create an account on https://railway.app
2. Create a new project and deploy from GitHub or locally
3. Add environment variables
4. Port will be automatically assigned

**Option C: VPS Server (DigitalOcean, AWS, etc.)**

```bash
# On your server
cd /opt/mcp-servers/{WORKFLOW_NAME_SLUG}

# Install dependencies
pip install mcp aiohttp python-dotenv uvicorn

# Create .env
cat > .env << EOF
PARADIGM_API_KEY=your_api_key
PARADIGM_BASE_URL=https://paradigm.lighton.ai
MCP_BEARER_TOKEN=your_secret_token
EOF

# Start with systemd or supervisord
python -m http_server --host 0.0.0.0 --port 8080
```

### Step 2: Register server in Paradigm

As a system administrator in Paradigm:

1. Go to **Admin > MCP Servers**
2. Click **Add MCP Server**
3. Fill in the information:
   - **Name**: `{WORKFLOW_NAME_SLUG}`
   - **URL**: `https://your-server.com/mcp` (public URL from step 1 + `/mcp`)
   - **Bearer Token**: The value of configured `MCP_BEARER_TOKEN` (optional)
4. Click **Save**

**⚠️ Important**: The URL must end with `/mcp` for Paradigm to communicate with the MCP server.
   - ✅ Correct: `https://mcp-workflow-resume-analysis.onrender.com/mcp`
   - ❌ Incorrect: `https://mcp-workflow-resume-analysis.onrender.com`

### Step 3: Activate the MCP server

1. Go to **Chat Settings** (gear icon in top right)
2. **Agent Tools** section
3. Enable the toggle for `{WORKFLOW_NAME_SLUG}`
4. Enable **Agent Mode** in your conversations

### ⚠️ Known Paradigm Bug

**Problem**: Files uploaded via Paradigm interface are not correctly transmitted to the MCP workflow.

**Symptom**: The workflow receives empty or incorrect `file_ids`, even if you uploaded documents.

**Status**: Bug under investigation with the Paradigm team.

**Temporary workaround**: Use Claude Desktop locally (see Part 2) where everything works correctly.

---

## 🖥️ PART 2: Installation for Claude Desktop

### Prerequisites

- Python 3.10 or higher installed
- Claude Desktop installed (https://claude.ai/download)

### Step 1: Install Python dependencies (once only)

**IMPORTANT:** Install dependencies globally, once for all your MCP workflows!

```bash
pip install mcp aiohttp python-dotenv
```

⚠️ **DO NOT** run `pip install -e .` in this folder! This would create conflicts if you have multiple MCP workflows.

### Step 2: Configure the .env file

A `.env.example` file is present in this folder. Rename it to `.env` and fill in your Paradigm API key:

```bash
# Rename the file
mv .env.example .env

# Edit the .env file and replace "your_api_key" with your real key
PARADIGM_API_KEY=your_api_key_here
PARADIGM_BASE_URL=https://paradigm.lighton.ai
```

You can get your API key from: https://paradigm.lighton.ai/settings/api-keys

### Step 3: Configure Claude Desktop

Add this configuration to the Claude Desktop configuration file.

**File location:**

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
  - Full path: `C:\Users\YourName\AppData\Roaming\Claude\claude_desktop_config.json`
  - Open folder: Type `%APPDATA%\Claude` in Windows Explorer

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

- **Linux**: `~/.config/Claude/claude_desktop_config.json`

**Configuration to add:**

```json
{{
  "mcpServers": {{
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "py",
      "args": ["-3.10", "-m", "server"],
      "cwd": "ABSOLUTE_PATH_TO_THIS_FOLDER"
    }}
  }}
}}
```

**⚠️ IMPORTANT - Replace `ABSOLUTE_PATH_TO_THIS_FOLDER`:**

Examples:
- Windows: `"cwd": "C:\\Users\\YourName\\Downloads\\{WORKFLOW_NAME_SLUG}"`
- macOS/Linux: `"cwd": "/Users/YourName/Downloads/{WORKFLOW_NAME_SLUG}"`

**Notes:**
- Use double backslashes `\\` on Windows
- Path must be absolute (no `~` or environment variables)
- If you have Python 3.11+, replace `-3.10` with your version

**If you already have other MCP servers:**

```json
{{
  "mcpServers": {{
    "other-server": {{
      "command": "...",
      "args": [...]
    }},
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "py",
      "args": ["-3.10", "-m", "server"],
      "cwd": "ABSOLUTE_PATH_TO_THIS_FOLDER"
    }}
  }}
}}
```

### Step 4: Restart Claude Desktop

1. **Completely** close Claude Desktop (check it's not in the taskbar)
2. Restart Claude Desktop
3. The `{WORKFLOW_NAME_SLUG}` MCP server will load automatically

### Verification

In Claude Desktop, you should see a notification indicating the MCP server is connected.

If you see an error, check the logs:
- **Windows**: Menu **Help > Show Logs**
- **macOS**: Menu **Claude > Show Logs**

---

## 📖 Usage

### In Claude Desktop

Once configured, use the workflow directly in your conversations by specifying **absolute paths** to documents to analyze:

{USAGE_EXAMPLES}

**Important**: Claude Desktop requires complete file paths on your system (e.g., `C:\Users\YourName\Documents\my_resume.pdf` on Windows or `/Users/YourName/Documents/my_resume.pdf` on macOS/Linux).

**⚠️ Claude Desktop time limit**: Claude Desktop imposes a **4 minute maximum** timeout per MCP request. If your workflow processes many documents or performs complex analyses exceeding this time, the request will be cancelled with a "Request timed out" message.

**Recommendations**:
- Limit the number of documents analyzed simultaneously (ideally 3-5 maximum)
- For long workflows, prefer HTTP deployment on Paradigm which doesn't have this limitation
- If timeout occurs, try simplifying the workflow or reducing the number of files processed

Claude will automatically use the MCP tool to execute the workflow.

### In Paradigm (once the bug is fixed)

1. Upload your documents via Paradigm interface
2. Enable **Agent Mode** in the conversation
3. Ask Paradigm to use the workflow:
   ```
   Use the {WORKFLOW_NAME_SLUG} workflow to analyze the uploaded documents
   ```

---

## 📊 Workflow Parameters

{WORKFLOW_PARAMETERS_DOC}

## 📤 Output Format

{WORKFLOW_OUTPUT_DOC}

---

## 🔧 Troubleshooting

### Claude Desktop

**Server doesn't start**
- Verify Python 3.10+ is installed: `python --version` or `py -3.10 --version`
- Check dependencies: `pip list | grep mcp`
- Check Claude Desktop logs: Menu **Help > Show Logs**

**Error "command not found"**
- On Windows, use `"command": "py"` instead of `"command": "python"`
- Specify full path: `"command": "C:\\Python310\\python.exe"`

**Paradigm authentication error**
- Verify your API key is correct in the `.env` file
- Test the key: `curl -H "Authorization: Bearer YOUR_KEY" https://paradigm.lighton.ai/api/v2/health`

**Workflow fails**
- Verify you uploaded the required files
- Check logs for error details
- Verify parameters match the expected schema

### Paradigm

**MCP server doesn't appear**
- Verify the public URL is accessible: `curl https://your-server.com/health`
- Check the configured bearer token
- Contact your Paradigm system administrator

**file_ids bug**
- This is a known issue, use Claude Desktop while waiting for the fix

---

## 📁 Project Structure

```
{WORKFLOW_NAME_SLUG}/
├── server.py              # MCP stdio server (Claude Desktop)
├── http_server.py         # MCP HTTP server (Paradigm)
├── workflow.py            # Generated workflow logic
├── paradigm_client.py     # Standalone Paradigm API client
├── pyproject.toml         # Python package configuration
├── .env                   # Environment variables (already configured)
├── .env.example           # Environment variables template
├── .gitignore             # Files to ignore by Git
└── README.md              # This file
```

---

## 📞 Support

- **MCP Documentation**: https://modelcontextprotocol.io
- **Paradigm Documentation**: https://docs.lighton.ai
- **LightOn Support**: support@lighton.ai

---

**Generated by LightOn Workflow Builder**
