"""
Workflow Package Generator
===========================

This module generates standalone workflow runner packages (ZIP files) containing:
- Frontend (HTML/CSS/JS with jsPDF for PDF generation)
- Backend (FastAPI server)
- Workflow code
- Paradigm client
- Docker configuration
- Documentation (bilingual FR/EN)

The generated package can be deployed independently by clients.
"""

import os
import io
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class WorkflowPackageGenerator:
    """
    Generates a complete standalone workflow package as a ZIP file.

    The package includes everything needed to run the workflow independently:
    - Frontend with dynamic UI and PDF generation
    - Backend API server
    - Workflow execution code
    - Docker configuration
    - Comprehensive documentation
    """

    def __init__(
        self,
        workflow_name: str,
        workflow_description: str,
        workflow_code: str,
        ui_config: Dict[str, Any]
    ):
        """
        Initialize the package generator.

        Args:
            workflow_name: Human-readable name for the workflow
            workflow_description: Brief description of what the workflow does
            workflow_code: The Python code of the workflow (execute_workflow function)
            ui_config: UI configuration (files, text input requirements, etc.)
        """
        # Sanitize name: collapse whitespace to single space, remove control characters
        self.workflow_name = re.sub(r'\s+', ' ', workflow_name).strip()[:80]
        self.workflow_description = re.sub(r'[\r\n]+', ' ', workflow_description).strip()
        self.workflow_code = workflow_code
        self.ui_config = ui_config
        self.templates_dir = Path(__file__).parent.parent / "templates" / "workflow_runner"

    def generate_zip(self) -> io.BytesIO:
        """
        Generate the complete package as a ZIP file in memory.

        Returns:
            BytesIO: In-memory ZIP file ready to download
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Frontend files
            self._add_frontend_files(zip_file)

            # Backend files
            self._add_backend_files(zip_file)

            # Docker configuration
            self._add_docker_files(zip_file)

            # Documentation
            self._add_documentation(zip_file)

            # Configuration files
            self._add_config_files(zip_file)

        zip_buffer.seek(0)
        return zip_buffer

    def _add_frontend_files(self, zip_file: zipfile.ZipFile):
        """Add frontend files (HTML, config) to the ZIP"""

        # Read and customize index.html template
        index_html_path = self.templates_dir / "frontend_index.html"
        with open(index_html_path, 'r', encoding='utf-8') as f:
            index_html = f.read()

        # Replace placeholders
        index_html = index_html.replace('{{WORKFLOW_NAME}}', self.workflow_name)
        index_html = index_html.replace('{{WORKFLOW_DESCRIPTION}}', self.workflow_description)

        zip_file.writestr('frontend/index.html', index_html)

        # Create config.json
        import json
        config_json = json.dumps(self.ui_config, indent=2, ensure_ascii=False)
        zip_file.writestr('frontend/config.json', config_json)

    def _add_backend_files(self, zip_file: zipfile.ZipFile):
        """Add backend files (main.py, workflow.py, etc.) to the ZIP"""

        # Read and customize main.py template
        main_py_path = self.templates_dir / "backend_main.py"
        with open(main_py_path, 'r', encoding='utf-8') as f:
            main_py = f.read()

        # Replace placeholders
        main_py = main_py.replace('{{WORKFLOW_NAME}}', self.workflow_name)

        zip_file.writestr('backend/main.py', main_py)

        # Add workflow.py (the generated workflow code)
        zip_file.writestr('backend/workflow.py', self.workflow_code)

        # Add paradigm_client.py (standalone client)
        paradigm_client_path = Path(__file__).parent.parent.parent / "paradigm_client_standalone.py"
        with open(paradigm_client_path, 'r', encoding='utf-8') as f:
            paradigm_client_code = f.read()

        zip_file.writestr('backend/paradigm_client.py', paradigm_client_code)

        # Add requirements.txt
        requirements_path = self.templates_dir / "requirements.txt"
        with open(requirements_path, 'r', encoding='utf-8') as f:
            requirements = f.read()

        zip_file.writestr('backend/requirements.txt', requirements)

    def _add_docker_files(self, zip_file: zipfile.ZipFile):
        """Add Docker configuration files to the ZIP"""

        # Add Dockerfile
        dockerfile_path = self.templates_dir / "Dockerfile"
        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            dockerfile = f.read()

        zip_file.writestr('Dockerfile', dockerfile)

        # Read and customize docker-compose.yml
        compose_path = self.templates_dir / "docker-compose.yml"
        with open(compose_path, 'r', encoding='utf-8') as f:
            compose_yml = f.read()

        # Create container name from workflow name (sanitize for YAML/Docker compatibility)
        container_name = re.sub(r'[^a-z0-9]+', '-', self.workflow_name.lower()).strip('-')[:50]
        compose_yml = compose_yml.replace('{{CONTAINER_NAME}}', f'workflow-{container_name}')

        zip_file.writestr('docker-compose.yml', compose_yml)

    def _add_documentation(self, zip_file: zipfile.ZipFile):
        """Add README and other documentation to the ZIP"""

        # Read and customize README.md template
        readme_path = self.templates_dir / "README.md"
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme = f.read()

        # Replace placeholders
        readme = readme.replace('{{WORKFLOW_NAME}}', self.workflow_name)
        readme = readme.replace('{{WORKFLOW_DESCRIPTION}}', self.workflow_description)
        readme = readme.replace('{{GENERATION_DATE}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        zip_file.writestr('README.md', readme)

    def _add_config_files(self, zip_file: zipfile.ZipFile):
        """Add configuration files (.env.example, .gitignore) to the ZIP"""

        # Add .env.example
        env_example_path = self.templates_dir / ".env.example"
        with open(env_example_path, 'r', encoding='utf-8') as f:
            env_example = f.read()

        zip_file.writestr('.env.example', env_example)

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

# Docker
*.log
"""
        zip_file.writestr('.gitignore', gitignore_content)


def generate_ui_config_simple(workflow_name: str, workflow_description: str, file_count: int = 1) -> Dict[str, Any]:
    """
    Generate a simple UI configuration for prototyping.

    This is a basic configuration generator for testing.
    Later, we'll use Claude to analyze the workflow code and generate this automatically.

    Args:
        workflow_name: Name of the workflow
        workflow_description: Brief description
        file_count: Number of files to upload (default: 1)

    Returns:
        Dict containing UI configuration
    """
    files = []
    for i in range(file_count):
        files.append({
            "key": f"document_{i+1}",
            "label": f"Document {i+1}",
            "description": f"Upload document {i+1} for analysis",
            "required": True,
            "accept": ".pdf,.doc,.docx,.txt"
        })

    return {
        "workflow_name": workflow_name,
        "workflow_description": workflow_description,
        "requires_text_input": True,
        "text_input_label": "Entrez votre question",
        "text_input_placeholder": "Que voulez-vous analyser dans les documents ?",
        "requires_files": file_count > 0,
        "files": files
    }
