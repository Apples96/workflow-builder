"""
Workflow Combiner - Combines cell-based workflows into clean, executable code.

This module takes a workflow plan with individual cell codes and combines them
into a single, clean workflow file that:
1. Deduplicates imports and setup code
2. Wraps each cell's logic in an async function
3. Generates a main execution flow respecting layer parallelism
4. Produces production-ready, executable code

The output is suitable for:
- Standalone deployment
- Package generation (web app, MCP server)
- Code review and modification
"""

import re
import ast
import logging
from typing import List, Dict, Any, Set, Tuple, Optional
from dataclasses import dataclass

from ..models import WorkflowPlan, WorkflowCell

logger = logging.getLogger(__name__)


@dataclass
class CellCodeAnalysis:
    """
    Analysis of a single cell's code.

    Attributes:
        imports: Set of import statements
        setup_code: Code that sets up API clients, constants, etc.
        core_logic: The main logic of the cell
        output_variables: Variables that this cell produces
    """
    imports: Set[str]
    setup_code: List[str]
    core_logic: str
    output_variables: List[str]


class WorkflowCombiner:
    """
    Combines cell-based workflow code into a single clean workflow.

    Takes individual cell codes and produces a unified workflow with:
    - Deduplicated imports
    - Single API setup section
    - Cell functions with proper signatures
    - Main execution flow respecting layer parallelism
    """

    # Common imports that should appear only once
    STANDARD_IMPORTS = {
        'import requests',
        'import json',
        'import asyncio',
        'import aiohttp',
        'import os',
        'import re',
        'import time',
        'from typing import Dict, Any, List, Optional, Tuple',
        'from datetime import datetime',
    }

    # Patterns for API setup code that should be deduplicated
    API_SETUP_PATTERNS = [
        r'PARADIGM_API_KEY\s*=',
        r'LIGHTON_API_KEY\s*=',
        r'API_BASE_URL\s*=',
        r'headers\s*=\s*\{[^}]*Authorization',
    ]

    def __init__(self, plan: WorkflowPlan, workflow_description: str = ""):
        """
        Initialize the combiner with a workflow plan.

        Args:
            plan: The workflow plan containing cells
            workflow_description: Human-readable workflow description
        """
        self.plan = plan
        self.workflow_description = workflow_description
        self.cells_by_layer = plan.get_cells_by_layer()

    def combine(self) -> str:
        """
        Combine all cell codes into a single clean workflow.

        Returns:
            str: Combined workflow code
        """
        # Analyze all cells
        cell_analyses: Dict[str, CellCodeAnalysis] = {}
        all_imports: Set[str] = set()

        for cell in self.plan.cells:
            if cell.generated_code:
                analysis = self._analyze_cell_code(cell)
                cell_analyses[cell.id] = analysis
                all_imports.update(analysis.imports)

        # Build the combined workflow
        sections = []

        # 1. Module docstring
        sections.append(self._generate_module_docstring())

        # 2. Imports (deduplicated)
        sections.append(self._generate_imports_section(all_imports))

        # 3. API setup (single instance)
        sections.append(self._generate_api_setup_section())

        # 4. Helper functions
        sections.append(self._generate_helper_functions())

        # 5. Cell functions
        for cell in self.plan.cells:
            if cell.id in cell_analyses:
                sections.append(self._generate_cell_function(cell, cell_analyses[cell.id]))

        # 6. Main execution function
        sections.append(self._generate_main_execution())

        # 7. Entry point
        sections.append(self._generate_entry_point())

        return "\n\n".join(filter(None, sections))

    def _analyze_cell_code(self, cell: WorkflowCell) -> CellCodeAnalysis:
        """
        Analyze a cell's code to extract imports, setup, and core logic.

        Args:
            cell: The cell to analyze

        Returns:
            CellCodeAnalysis: Analysis results
        """
        code = cell.generated_code or ""
        lines = code.split('\n')

        imports: Set[str] = set()
        setup_code: List[str] = []
        core_lines: List[str] = []

        in_imports = True
        in_setup = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines and comments at the start
            if not stripped or stripped.startswith('#'):
                if not in_imports:
                    core_lines.append(line)
                continue

            # Collect imports
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.add(stripped)
                continue

            # After imports, check for setup code
            in_imports = False

            # Check if this is API setup code
            is_setup = any(re.search(pattern, stripped) for pattern in self.API_SETUP_PATTERNS)

            if is_setup:
                setup_code.append(line)
            else:
                core_lines.append(line)

        # Clean up core logic - remove leading/trailing empty lines
        while core_lines and not core_lines[0].strip():
            core_lines.pop(0)
        while core_lines and not core_lines[-1].strip():
            core_lines.pop()

        return CellCodeAnalysis(
            imports=imports,
            setup_code=setup_code,
            core_logic='\n'.join(core_lines),
            output_variables=cell.outputs_produced
        )

    def _generate_module_docstring(self) -> str:
        """Generate the module docstring."""
        # Get layer info
        total_layers = len(self.cells_by_layer)
        parallel_layers = sum(1 for cells in self.cells_by_layer.values() if len(cells) > 1)

        return '''"""
{description}

Auto-generated workflow with {total_cells} cells in {total_layers} layers.
{parallel_info}

Cells:
{cell_list}
"""'''.format(
            description=self.workflow_description or "Combined Workflow",
            total_cells=len(self.plan.cells),
            total_layers=total_layers,
            parallel_info=f"Parallel execution enabled ({parallel_layers} parallel layers)." if parallel_layers > 0 else "Sequential execution.",
            cell_list='\n'.join(f"  - Cell {c.step_number}: {c.name}" for c in self.plan.cells)
        )

    def _generate_imports_section(self, all_imports: Set[str]) -> str:
        """Generate deduplicated imports section."""
        # Separate standard library, third-party, and typing imports
        stdlib_imports = []
        typing_imports = []
        thirdparty_imports = []

        # Always include these base imports
        base_imports = {
            'import asyncio',
            'import json',
            'import os',
            'import re',
            'from typing import Dict, Any, List, Optional',
            'from datetime import datetime',
        }
        all_imports.update(base_imports)

        for imp in sorted(all_imports):
            if 'typing' in imp:
                typing_imports.append(imp)
            elif any(pkg in imp for pkg in ['requests', 'aiohttp', 'anthropic']):
                thirdparty_imports.append(imp)
            else:
                stdlib_imports.append(imp)

        sections = []
        sections.append("# Standard library imports")
        sections.extend(sorted(set(stdlib_imports)))

        if typing_imports:
            sections.append("")
            sections.append("# Type hints")
            sections.extend(sorted(set(typing_imports)))

        if thirdparty_imports:
            sections.append("")
            sections.append("# Third-party imports")
            sections.extend(sorted(set(thirdparty_imports)))

        return '\n'.join(sections)

    def _generate_api_setup_section(self) -> str:
        """Generate the API setup section."""
        return '''# =============================================================================
# API CONFIGURATION
# =============================================================================

# Load API key from environment
PARADIGM_API_KEY = os.environ.get("LIGHTON_API_KEY") or os.environ.get("PARADIGM_API_KEY")
API_BASE_URL = "https://paradigm.lighton.ai"

if not PARADIGM_API_KEY:
    raise ValueError("LIGHTON_API_KEY or PARADIGM_API_KEY environment variable is required")

# Common headers for Paradigm API calls
def get_api_headers() -> Dict[str, str]:
    """Get headers for Paradigm API requests."""
    return {
        "Authorization": f"Bearer {PARADIGM_API_KEY}",
        "Content-Type": "application/json"
    }'''

    def _generate_helper_functions(self) -> str:
        """Generate common helper functions."""
        return '''# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def paradigm_document_search(
    query: str,
    file_ids: Optional[List[int]] = None,
    tool: str = "DocumentSearch"
) -> Dict[str, Any]:
    """
    Search documents using Paradigm API.

    Args:
        query: Search query in natural language
        file_ids: Optional list of specific file IDs to search
        tool: Search tool to use (DocumentSearch or VisionDocumentSearch)

    Returns:
        Dict with answer and source documents
    """
    import aiohttp

    endpoint = f"{API_BASE_URL}/api/v2/chat/completions"

    payload = {
        "model": "alfred-40b-1124",
        "messages": [{"role": "user", "content": query}],
        "tools": [tool],
        "stream": False
    }

    if file_ids:
        payload["file_ids"] = file_ids

    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json=payload,
            headers=get_api_headers()
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Paradigm API error {response.status}: {error_text}")

            result = await response.json()

            # Extract answer from response
            answer = ""
            documents = []

            if "choices" in result and result["choices"]:
                message = result["choices"][0].get("message", {})
                answer = message.get("content", "")

                # Extract documents from tool calls
                tool_calls = message.get("tool_calls", [])
                for tc in tool_calls:
                    if tc.get("type") == "document_search":
                        docs = tc.get("documents", [])
                        documents.extend(docs)

            return {
                "answer": answer,
                "documents": documents,
                "raw_response": result
            }


def print_output(message: str):
    """Print output message (captured for cell output)."""
    print(f"CELL_OUTPUT: {message}")'''

    def _generate_cell_function(self, cell: WorkflowCell, analysis: CellCodeAnalysis) -> str:
        """
        Generate an async function for a cell.

        Args:
            cell: The cell definition
            analysis: Analysis of the cell's code

        Returns:
            str: The cell function code
        """
        # Create function name from cell name
        func_name = self._cell_name_to_function(cell.name)

        # Determine inputs needed
        inputs = cell.inputs_required or []

        # Build function signature
        params = ["context: Dict[str, Any]"]

        # Build docstring
        docstring = f'''"""
    Cell {cell.step_number}: {cell.name}

    {cell.description}

    Layer: {cell.layer} ({"parallel" if len(self.cells_by_layer.get(cell.layer, [])) > 1 else "sequential"})

    Inputs: {', '.join(inputs) if inputs else 'None'}
    Outputs: {', '.join(cell.outputs_produced) if cell.outputs_produced else 'context updates'}
    """'''

        # Process core logic - indent it properly and handle context
        core_logic = self._process_core_logic(analysis.core_logic, inputs, cell.outputs_produced)

        # Build the function
        function_code = f'''
# -----------------------------------------------------------------------------
# CELL {cell.step_number}: {cell.name.upper()}
# -----------------------------------------------------------------------------

async def {func_name}({', '.join(params)}) -> Dict[str, Any]:
    {docstring}

    # Extract inputs from context
    user_input = context.get("user_input", "")
    attached_file_ids = context.get("attached_file_ids", [])
{self._generate_input_extraction(inputs)}

    # Cell logic
{self._indent_code(core_logic, 4)}

    # Return outputs
    return {self._generate_output_dict(cell.outputs_produced)}'''

        return function_code

    def _generate_main_execution(self) -> str:
        """Generate the main execution function with layer parallelism."""
        layers = sorted(self.cells_by_layer.keys())

        layer_code_blocks = []

        for layer_num in layers:
            cells = self.cells_by_layer[layer_num]

            if len(cells) == 1:
                # Sequential execution
                cell = cells[0]
                func_name = self._cell_name_to_function(cell.name)
                layer_code_blocks.append(f'''    # Layer {layer_num}: {cell.name}
    print_output(f"Executing Layer {layer_num}: {cell.name}")
    layer_{layer_num}_result = await {func_name}(context)
    context.update(layer_{layer_num}_result)''')
            else:
                # Parallel execution
                cell_names = [c.name for c in cells]
                func_calls = [f"{self._cell_name_to_function(c.name)}(context.copy())" for c in cells]

                layer_code_blocks.append(f'''    # Layer {layer_num}: PARALLEL ({', '.join(cell_names)})
    print_output(f"Executing Layer {layer_num} in parallel: {', '.join(cell_names)}")
    layer_{layer_num}_results = await asyncio.gather(
        {(','+chr(10)+'        ').join(func_calls)}
    )
    # Merge results from parallel cells
    for result in layer_{layer_num}_results:
        context.update(result)''')

        return f'''# =============================================================================
# MAIN WORKFLOW EXECUTION
# =============================================================================

async def run_workflow(
    user_input: str,
    attached_file_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Execute the complete workflow.

    Args:
        user_input: User's input query
        attached_file_ids: Optional list of document file IDs

    Returns:
        Dict containing all workflow outputs
    """
    # Initialize context with inputs
    context: Dict[str, Any] = {{
        "user_input": user_input,
        "attached_file_ids": attached_file_ids or []
    }}

    print_output(f"Starting workflow with input: {{user_input[:100]}}...")

{chr(10).join(layer_code_blocks)}

    print_output("Workflow completed successfully!")

    return context'''

    def _generate_entry_point(self) -> str:
        """Generate the entry point for standalone execution."""
        return '''# =============================================================================
# ENTRY POINT
# =============================================================================

async def execute_workflow(user_input: str, file_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Async entry point for workflow execution.

    Args:
        user_input: User's input query
        file_ids: Optional list of document file IDs

    Returns:
        Dict containing all workflow outputs
    """
    return await run_workflow(user_input, file_ids)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python workflow.py <user_input> [file_id1,file_id2,...]")
        sys.exit(1)

    user_input = sys.argv[1]
    file_ids = None

    if len(sys.argv) > 2:
        file_ids = [int(fid) for fid in sys.argv[2].split(",")]

    result = asyncio.run(execute_workflow(user_input, file_ids))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))'''

    def _cell_name_to_function(self, name: str) -> str:
        """Convert a cell name to a valid Python function name."""
        # Remove special characters and convert to snake_case
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        name = name.lower()
        # Ensure it starts with a letter
        if name and name[0].isdigit():
            name = 'cell_' + name
        return f"cell_{name}" if name else "cell_unnamed"

    def _process_core_logic(self, code: str, inputs: List[str], outputs: List[str]) -> str:
        """
        Process core logic to work within the function context.

        Replaces direct variable references with context lookups where needed.
        """
        # For now, return as-is - the cell code should already handle context
        # In a more sophisticated version, we could rewrite variable references
        return code if code.strip() else "pass  # No logic generated"

    def _generate_input_extraction(self, inputs: List[str]) -> str:
        """Generate code to extract inputs from context."""
        if not inputs:
            return ""

        lines = []
        for inp in inputs:
            lines.append(f'    {inp} = context.get("{inp}")')

        return '\n'.join(lines)

    def _generate_output_dict(self, outputs: List[str]) -> str:
        """Generate the return dictionary for outputs."""
        if not outputs:
            return "{}"

        items = [f'"{out}": {out}' for out in outputs]

        if len(items) <= 2:
            return "{" + ", ".join(items) + "}"
        else:
            return "{\n        " + ",\n        ".join(items) + "\n    }"

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by a number of spaces."""
        indent = ' ' * spaces
        lines = code.split('\n')
        return '\n'.join(indent + line if line.strip() else line for line in lines)


def combine_workflow_cells(plan: WorkflowPlan, workflow_description: str = "") -> str:
    """
    Convenience function to combine workflow cells into clean code.

    Args:
        plan: The workflow plan containing cells
        workflow_description: Human-readable workflow description

    Returns:
        str: Combined, clean workflow code
    """
    combiner = WorkflowCombiner(plan, workflow_description)
    return combiner.combine()
