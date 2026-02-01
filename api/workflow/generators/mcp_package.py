"""
MCP Package Generator
=====================

This module generates MCP (Model Context Protocol) server packages containing:
- MCP server with tool definitions
- Workflow code
- Paradigm client
- Python package configuration
- Documentation for Claude Desktop integration

The generated package can be used directly in Claude Desktop or any MCP-compatible client.
"""

import os
import io
import zipfile
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class MCPPackageGenerator:
    """
    Generates a complete MCP server package as a ZIP file.

    The package includes everything needed to expose the workflow as an MCP tool:
    - MCP server with tool definitions
    - Workflow execution code
    - Paradigm API client
    - Python package configuration
    - Claude Desktop integration instructions
    """

    def __init__(
        self,
        workflow_name: str,
        workflow_description: str,
        workflow_code: str,
        workflow_parameters: List[Dict[str, Any]],
        workflow_output_format: str
    ):
        """
        Initialize the MCP package generator.

        Args:
            workflow_name: Human-readable name for the workflow
            workflow_description: Brief description of what the workflow does
            workflow_code: The Python code of the workflow (execute_workflow function)
            workflow_parameters: List of input parameters with their schemas
            workflow_output_format: Description of the output format
        """
        self.workflow_name = workflow_name
        self.workflow_description = workflow_description
        self.workflow_code = workflow_code
        self.workflow_parameters = workflow_parameters
        self.workflow_output_format = workflow_output_format
        self.templates_dir = Path(__file__).parent.parent / "templates" / "mcp_server"

    def generate_zip(self) -> io.BytesIO:
        """
        Generate the complete MCP package as a ZIP file in memory.

        Returns:
            BytesIO: In-memory ZIP file ready to download
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # MCP server file (stdio for Claude Desktop)
            self._add_server_file(zip_file)

            # HTTP MCP server file (for Paradigm)
            self._add_http_server_file(zip_file)

            # Workflow code
            self._add_workflow_file(zip_file)

            # Paradigm client
            self._add_paradigm_client(zip_file)

            # Python package configuration
            self._add_package_config(zip_file)

            # Documentation
            self._add_documentation(zip_file)

            # Configuration files
            self._add_config_files(zip_file)

        zip_buffer.seek(0)
        return zip_buffer

    def _add_server_file(self, zip_file: zipfile.ZipFile):
        """Add the MCP server.py file to the ZIP"""

        # Read server.py template
        server_py_path = self.templates_dir / "server.py"
        with open(server_py_path, 'r', encoding='utf-8') as f:
            server_py = f.read()

        # Generate workflow name slug
        workflow_name_slug = self.workflow_name.lower().replace(' ', '-').replace('_', '-')

        # Generate tool input schema
        tool_input_schema = self._generate_tool_input_schema()

        # Generate tool input schema description (for documentation)
        tool_input_description = self._generate_tool_input_description()

        # Replace placeholders
        server_py = server_py.replace('{WORKFLOW_NAME}', self.workflow_name)
        server_py = server_py.replace('{WORKFLOW_NAME_SLUG}', workflow_name_slug)
        server_py = server_py.replace('{WORKFLOW_DESCRIPTION}', self.workflow_description)
        server_py = server_py.replace('{TOOL_INPUT_SCHEMA}', tool_input_description)
        server_py = server_py.replace('{TOOL_OUTPUT_DESCRIPTION}', self.workflow_output_format)
        server_py = server_py.replace('{TOOL_INPUT_JSON_SCHEMA}', json.dumps(tool_input_schema, ensure_ascii=False))

        zip_file.writestr('server.py', server_py)

    def _add_http_server_file(self, zip_file: zipfile.ZipFile):
        """Add the HTTP MCP server (http_server.py) file to the ZIP for Paradigm integration"""

        # Read http_server.py template
        http_server_py_path = self.templates_dir / "http_server.py"
        with open(http_server_py_path, 'r', encoding='utf-8') as f:
            http_server_py = f.read()

        # Generate workflow name slug
        workflow_name_slug = self.workflow_name.lower().replace(' ', '-').replace('_', '-')

        # Generate tool input schema
        tool_input_schema = self._generate_tool_input_schema()

        # Generate parameters description for the API docs
        parameters_description = self._generate_tool_input_description()

        # Replace placeholders
        http_server_py = http_server_py.replace('{WORKFLOW_NAME}', self.workflow_name)
        http_server_py = http_server_py.replace('{WORKFLOW_NAME_SLUG}', workflow_name_slug)
        http_server_py = http_server_py.replace('{WORKFLOW_DESCRIPTION}', self.workflow_description)
        http_server_py = http_server_py.replace('{WORKFLOW_PARAMETERS_DESCRIPTION}', parameters_description)
        http_server_py = http_server_py.replace('{WORKFLOW_OUTPUT_DESCRIPTION}', self.workflow_output_format)
        http_server_py = http_server_py.replace('{WORKFLOW_INPUT_SCHEMA}', json.dumps(tool_input_schema, ensure_ascii=False))

        zip_file.writestr('http_server.py', http_server_py)

    def _add_workflow_file(self, zip_file: zipfile.ZipFile):
        """Add the workflow.py file to the ZIP"""

        # Wrap the workflow code in a WorkflowExecutor class with file upload support
        workflow_wrapper = """\"\"\"
Workflow Execution Logic
Generated by LightOn Workflow Builder
\"\"\"

import logging
import os
from typing import Any, Dict, List
from dotenv import load_dotenv
from paradigm_client import ParadigmClient

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    \"\"\"
    Executes the workflow using the Paradigm API.
    Supports multiple input modes:
    - File paths (for Claude Desktop with local files)
    - File IDs (for direct Paradigm document IDs)
    - Paradigm context (future - documents from Paradigm workspace)
    - Legacy attached_file_ids (from Workflow Builder web interface)
    \"\"\"

    def __init__(self, paradigm_client: ParadigmClient):
        self.paradigm_client = paradigm_client

    async def upload_file_from_path(self, file_path: str) -> int:
        \"\"\"
        Upload a file from local filesystem to Paradigm.

        Args:
            file_path: Path to the file to upload

        Returns:
            int: File ID in Paradigm

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If upload fails
        \"\"\"
        if not os.path.exists(file_path):
            raise FileNotFoundError("File not found: {}".format(file_path))

        logger.info("Uploading file: {}".format(file_path))

        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()

        filename = os.path.basename(file_path)

        # Upload to Paradigm
        result = await self.paradigm_client.upload_file(
            file_content=file_content,
            filename=filename,
            collection_type='private'
        )

        file_id = result.get('id') or result.get('file_id')
        logger.info("File uploaded successfully: {} (ID: {})".format(filename, file_id))

        # Wait for file to be embedded/indexed
        logger.info("Waiting for file {} to be indexed...".format(file_id))
        await self.paradigm_client.wait_for_embedding(
            file_id=file_id,
            max_wait_time=300,
            poll_interval=2
        )
        logger.info("File {} is ready".format(file_id))

        return file_id

    async def process_file_inputs(self, **kwargs) -> List[int]:
        \"\"\"
        Process file inputs from various sources and return file IDs.

        Supports:
        - file_paths: List of local file paths to upload
        - cv_file_path, job_posting_file_path, etc.: Individual file paths
        - file_ids: Direct Paradigm document IDs
        - paradigm_context: Future Paradigm MCP context
        - Legacy attached_file_ids

        Returns:
            List[int]: List of file IDs ready to use
        \"\"\"
        file_ids = []

        # MODE 1: File paths provided (Claude Desktop with local files)
        if 'file_paths' in kwargs and kwargs['file_paths']:
            logger.info("MODE 1: Uploading files from paths")
            for path in kwargs['file_paths']:
                file_id = await self.upload_file_from_path(path)
                file_ids.append(file_id)

        # MODE 1b: Individual file path parameters (cv_file_path, job_posting_file_path, etc.)
        elif any(k.endswith('_file_path') for k in kwargs.keys()):
            logger.info("MODE 1b: Uploading individual files from paths")
            for key, value in kwargs.items():
                if key.endswith('_file_path') and value:
                    file_id = await self.upload_file_from_path(value)
                    file_ids.append(file_id)

        # MODE 2: File IDs provided directly
        elif 'file_ids' in kwargs and kwargs['file_ids']:
            logger.info("MODE 2: Using provided file IDs")
            file_ids = [int(fid) for fid in kwargs['file_ids']]

        # MODE 3: Paradigm context (future integration)
        elif 'paradigm_context' in kwargs:
            logger.info("MODE 3: Using Paradigm context")
            context = kwargs['paradigm_context']
            file_ids = context.get('document_ids', [])

        # MODE 4: Legacy attached_file_ids (Workflow Builder web)
        else:
            logger.info("MODE 4: Using legacy attached_file_ids")
            import builtins
            if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
                file_ids = globals()['attached_file_ids']
            elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
                file_ids = builtins.attached_file_ids
            else:
                logger.warning("No file inputs found")
                file_ids = []

        logger.info("Processed file inputs: {} file(s)".format(len(file_ids)))
        return file_ids

    async def execute(self, **kwargs) -> Dict[str, Any]:
        \"\"\"
        Execute the workflow with given parameters.

        Automatically detects input mode and processes files accordingly.

        Args:
            **kwargs: Workflow parameters (file_paths, file_ids, or other parameters)

        Returns:
            Dict containing workflow results
        \"\"\"
        try:
            # Process file inputs
            file_ids = await self.process_file_inputs(**kwargs)

            # Set attached_file_ids for legacy workflow code
            import builtins
            builtins.attached_file_ids = file_ids

            # Execute the workflow with user_input parameter
            # Extract query/user_input from kwargs, default to empty string
            user_input = kwargs.get('query', kwargs.get('user_input', ''))
            result = await execute_workflow(user_input)

            # Return structured result with file information
            return {
                "status": "success",
                "result": result,
                "files_processed": len(file_ids)
            }

        except Exception as e:
            logger.error("Workflow execution failed: {}".format(str(e)))
            raise


# Generated workflow code
"""

        # Append the workflow code directly (avoid .format() issues with braces in workflow code)
        workflow_file_content = workflow_wrapper + self.workflow_code

        zip_file.writestr('workflow.py', workflow_file_content)

    def _add_paradigm_client(self, zip_file: zipfile.ZipFile):
        """Add the standalone Paradigm client to the ZIP"""

        paradigm_client_path = Path(__file__).parent.parent.parent / "paradigm_client_standalone.py"
        with open(paradigm_client_path, 'r', encoding='utf-8') as f:
            paradigm_client_code = f.read()

        zip_file.writestr('paradigm_client.py', paradigm_client_code)

    def _add_package_config(self, zip_file: zipfile.ZipFile):
        """Add Python package configuration (pyproject.toml) to the ZIP"""

        # Read pyproject.toml template
        pyproject_path = self.templates_dir / "pyproject.toml"
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            pyproject_toml = f.read()

        # Generate workflow name slug
        workflow_name_slug = self.workflow_name.lower().replace(' ', '-').replace('_', '-')

        # Replace placeholders
        pyproject_toml = pyproject_toml.replace('{WORKFLOW_NAME_SLUG}', workflow_name_slug)
        pyproject_toml = pyproject_toml.replace('{WORKFLOW_DESCRIPTION}', self.workflow_description)

        zip_file.writestr('pyproject.toml', pyproject_toml)

    def _add_documentation(self, zip_file: zipfile.ZipFile):
        """Add README.md with installation instructions to the ZIP"""

        # Read README.md template
        readme_path = self.templates_dir / "README.md"
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme = f.read()

        # Generate workflow name slug
        workflow_name_slug = self.workflow_name.lower().replace(' ', '-').replace('_', '-')

        # Generate usage examples
        usage_examples = self._generate_usage_examples()

        # Generate parameters documentation
        parameters_doc = self._generate_parameters_doc()

        # Replace placeholders
        readme = readme.replace('{WORKFLOW_NAME}', self.workflow_name)
        readme = readme.replace('{WORKFLOW_NAME_SLUG}', workflow_name_slug)
        readme = readme.replace('{WORKFLOW_DESCRIPTION}', self.workflow_description)
        readme = readme.replace('{USAGE_EXAMPLES}', usage_examples)
        readme = readme.replace('{WORKFLOW_PARAMETERS_DOC}', parameters_doc)
        readme = readme.replace('{WORKFLOW_OUTPUT_DOC}', self.workflow_output_format)

        zip_file.writestr('README.md', readme)

    def _add_config_files(self, zip_file: zipfile.ZipFile):
        """Add configuration files (.env.example, .gitignore) to the ZIP"""

        # Add .env.example
        env_example_content = """# Paradigm API Configuration
PARADIGM_API_KEY=your_api_key_here
PARADIGM_BASE_URL=https://paradigm.lighton.ai
"""
        zip_file.writestr('.env.example', env_example_content)

        # Create .gitignore
        gitignore_content = """# Environment variables
.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Distribution
dist/
build/
*.egg-info/
"""
        zip_file.writestr('.gitignore', gitignore_content)

    def _generate_tool_input_schema(self) -> Dict[str, Any]:
        """
        Generate JSON schema for tool input based on workflow parameters.

        Returns:
            Dict containing JSON schema
        """
        properties = {}
        required = []

        for param in self.workflow_parameters:
            param_name = param.get('name', 'input')
            param_type = param.get('type', 'string')
            param_description = param.get('description', '')
            param_required = param.get('required', True)

            # Map workflow types to JSON schema types
            type_mapping = {
                'text': 'string',
                'file': 'string',
                'files': 'array',
                'number': 'number',
                'boolean': 'boolean'
            }

            json_type = type_mapping.get(param_type, 'string')

            properties[param_name] = {
                "type": json_type,
                "description": param_description
            }

            if param_type == 'files':
                properties[param_name]['items'] = {"type": "string"}

            if param_required:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    def _generate_tool_input_description(self) -> str:
        """
        Generate human-readable description of tool input parameters.

        Returns:
            String describing parameters
        """
        if not self.workflow_parameters:
            return "No input parameters required."

        lines = []
        for param in self.workflow_parameters:
            param_name = param.get('name', 'input')
            param_description = param.get('description', '')
            param_required = param.get('required', True)
            param_type = param.get('type', 'string')

            required_str = "(required)" if param_required else "(optional)"
            lines.append("- {}: {} {}".format(param_name, param_description, required_str))

        return "\n".join(lines)

    def _generate_usage_examples(self) -> str:
        """
        Generate usage examples for README.

        Returns:
            String with example usage
        """
        if not self.workflow_parameters:
            return "Utilisez simplement le nom du workflow dans votre conversation avec Claude."

        example_params = []
        for param in self.workflow_parameters:
            param_name = param.get('name', 'input')
            param_type = param.get('type', 'string')

            if param_type == 'text':
                example_params.append("{}: \"votre texte ici\"".format(param_name))
            elif param_type == 'file':
                example_params.append("{}: \"chemin/vers/fichier.pdf\"".format(param_name))
            elif param_type == 'files':
                example_params.append("{}: [\"fichier1.pdf\", \"fichier2.pdf\"]".format(param_name))
            elif param_type == 'number':
                example_params.append("{}: 42".format(param_name))
            elif param_type == 'boolean':
                example_params.append("{}: true".format(param_name))

        example_str = ", ".join(example_params)

        return """Exemple de demande dans Claude Desktop:

```
Utilise le workflow {} avec les parametres suivants: {}
```

Claude utilisera automatiquement l'outil MCP pour executer le workflow.""".format(
            self.workflow_name,
            example_str
        )

    def _generate_parameters_doc(self) -> str:
        """
        Generate parameters documentation for README.

        Returns:
            String with parameters documentation
        """
        if not self.workflow_parameters:
            return "Aucun parametre d'entree requis."

        lines = []
        for param in self.workflow_parameters:
            param_name = param.get('name', 'input')
            param_description = param.get('description', '')
            param_required = param.get('required', True)
            param_type = param.get('type', 'string')

            required_str = "**Obligatoire**" if param_required else "*Optionnel*"
            lines.append("- `{}` ({}): {} - {}".format(
                param_name,
                param_type,
                required_str,
                param_description
            ))

        return "\n".join(lines)


def extract_workflow_parameters_simple(workflow_name: str) -> List[Dict[str, Any]]:
    """
    Generate simple workflow parameters for prototyping.

    This is a basic configuration generator for testing.
    Later, we'll use Claude to analyze the workflow code and extract this automatically.

    Args:
        workflow_name: Name of the workflow

    Returns:
        List of parameter definitions
    """
    # Default: assume workflow takes file paths (for Claude Desktop with local files)
    return [
        {
            "name": "file_paths",
            "type": "files",
            "description": "Chemins complets des fichiers locaux a analyser (ex: C:\\\\Documents\\\\cv.pdf)",
            "required": True
        },
        {
            "name": "query",
            "type": "text",
            "description": "Question ou demande d'analyse (optionnel)",
            "required": False
        }
    ]
