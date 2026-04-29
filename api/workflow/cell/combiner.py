import re
import logging
from typing import List, Dict, Set
from dataclasses import dataclass

from ..models import WorkflowPlan, WorkflowCell

logger = logging.getLogger(__name__)


@dataclass
class CellCodeAnalysis:
    """Analysis of a single cell's code."""
    imports: Set[str]
    setup_code: List[str]
    core_logic: str
    output_variables: List[str]


class WorkflowCombiner:
    """Combines cell-based workflow code into a single clean workflow."""

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

    API_SETUP_PATTERNS = [
        r'PARADIGM_API_KEY\s*=',
        r'LIGHTON_API_KEY\s*=',
        r'API_BASE_URL\s*=',
        r'headers\s*=\s*\{[^}]*Authorization',
    ]

    def __init__(self, plan: WorkflowPlan, workflow_description: str = ""):
        self.plan = plan
        self.workflow_description = workflow_description
        self.cells_by_layer = plan.get_cells_by_layer()

    def combine(self) -> str:
        """Combine all cell codes into a single workflow string."""
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
        """Extract imports, setup code, and core logic from a cell."""
        code = cell.generated_code or ""
        lines = code.split('\n')

        imports: Set[str] = set()
        setup_code: List[str] = []
        core_lines: List[str] = []
        in_imports = True

        for line in lines:
            stripped = line.strip()

            if not stripped or stripped.startswith('#'):
                if not in_imports:
                    core_lines.append(line)
                continue

            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.add(stripped)
                continue

            in_imports = False
            is_setup = any(re.search(pattern, stripped) for pattern in self.API_SETUP_PATTERNS)

            if is_setup:
                setup_code.append(line)
            else:
                core_lines.append(line)

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
            parallel_info="Parallel execution enabled ({} parallel layers).".format(parallel_layers) if parallel_layers > 0 else "Sequential execution.",
            cell_list='\n'.join("  - Cell {}: {}".format(c.step_number, c.name) for c in self.plan.cells)
        )

    def _generate_imports_section(self, all_imports: Set[str]) -> str:
        """Generate deduplicated imports section."""
        stdlib_imports = []
        typing_imports = []
        thirdparty_imports = []

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
        """Generate the API configuration section."""
        return '''# =============================================================================
# API CONFIGURATION
# =============================================================================

from paradigm_client import ParadigmClient

# Load API key from environment (matching cell code expectations)
LIGHTON_API_KEY = os.environ.get("LIGHTON_API_KEY") or os.environ.get("PARADIGM_API_KEY")
LIGHTON_BASE_URL = os.environ.get("PARADIGM_BASE_URL", "https://paradigm.lighton.ai")

if not LIGHTON_API_KEY:
    raise ValueError("LIGHTON_API_KEY or PARADIGM_API_KEY environment variable is required")'''

    def _generate_helper_functions(self) -> str:
        """Generate shared helper functions."""
        return '''# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def print_output(message: str):
    """Print output message (captured for cell output)."""
    print("CELL_OUTPUT: {}".format(message))'''

    def _generate_cell_function(self, cell: WorkflowCell, analysis: CellCodeAnalysis) -> str:
        """Generate an async wrapper function for a cell."""
        func_name = self._cell_name_to_function(cell.name)
        inputs = cell.inputs_required or []
        params = ["context: Dict[str, Any]"]
        layer_mode = "parallel" if len(self.cells_by_layer.get(cell.layer, [])) > 1 else "sequential"
        inputs_str = ', '.join(inputs) if inputs else 'None'
        outputs_str = ', '.join(cell.outputs_produced) if cell.outputs_produced else 'context updates'

        core_logic = self._process_core_logic(analysis.core_logic, inputs, cell.outputs_produced)

        function_code = '''
# -----------------------------------------------------------------------------
# CELL {step}: {name_upper}
# -----------------------------------------------------------------------------

async def {func_name}({params}) -> Dict[str, Any]:
    """
    Cell {step}: {name}

    {description}

    Layer: {layer} ({layer_mode})

    Inputs: {inputs_str}
    Outputs: {outputs_str}
    """

    # Cell logic (defines execute_cell)
{core_logic}

    # Execute the cell and return its result
    return await execute_cell(context)
'''.format(
            step=cell.step_number,
            name_upper=cell.name.upper(),
            name=cell.name,
            func_name=func_name,
            params=', '.join(params),
            description=cell.description,
            layer=cell.layer,
            layer_mode=layer_mode,
            inputs_str=inputs_str,
            outputs_str=outputs_str,
            core_logic=self._indent_code(core_logic, 4)
        )

        return function_code

    def _generate_main_execution(self) -> str:
        """Generate the main workflow execution function."""
        layers = sorted(self.cells_by_layer.keys())

        layer_code_blocks = []

        for layer_num in layers:
            cells = self.cells_by_layer[layer_num]

            if len(cells) == 1:
                # Sequential execution
                cell = cells[0]
                func_name = self._cell_name_to_function(cell.name)
                block = '    # Layer {layer}: {name}\n'.format(layer=layer_num, name=cell.name)
                block += '    print_output("Executing Layer {layer}: {name}")\n'.format(layer=layer_num, name=cell.name)
                block += '    layer_{layer}_result = await {func}(context)\n'.format(layer=layer_num, func=func_name)
                block += '    context.update(layer_{layer}_result)'.format(layer=layer_num)
                layer_code_blocks.append(block)
            else:
                # Parallel execution
                cell_names = [c.name for c in cells]
                func_calls = ["{}(context.copy())".format(self._cell_name_to_function(c.name)) for c in cells]
                names_joined = ', '.join(cell_names)

                block = '    # Layer {layer}: PARALLEL ({names})\n'.format(layer=layer_num, names=names_joined)
                block += '    print_output("Executing Layer {layer} in parallel: {names}")\n'.format(layer=layer_num, names=names_joined)
                block += '    layer_{layer}_results = await asyncio.gather(\n'.format(layer=layer_num)
                block += '        ' + (',\n        ').join(func_calls) + '\n'
                block += '    )\n'
                block += '    # Merge results from parallel cells\n'
                block += '    for result in layer_{layer}_results:\n'.format(layer=layer_num)
                block += '        context.update(result)'
                layer_code_blocks.append(block)

        layers_joined = '\n\n'.join(layer_code_blocks)

        return '''# =============================================================================
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

    print_output("Starting workflow with input: {{}}...".format(user_input[:100]))

{layers}

    print_output("Workflow completed successfully!")

    return context'''.format(layers=layers_joined)

    def _generate_entry_point(self) -> str:
        """Generate the standalone entry point."""
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
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        name = name.lower()
        if name and name[0].isdigit():
            name = 'cell_' + name
        return "cell_{}".format(name) if name else "cell_unnamed"

    def _process_core_logic(self, code: str, inputs: List[str], outputs: List[str]) -> str:
        """Ensure core logic contains an execute_cell definition, wrapping if needed."""
        if not code.strip():
            return 'async def execute_cell(context):\n    return {}'

        # Verify execute_cell is defined in the core logic
        if 'async def execute_cell' not in code:
            # Wrap the raw code in an execute_cell function as fallback
            logger.warning("Core logic missing execute_cell definition, wrapping automatically")
            indented = self._indent_code(code, 4)
            return 'async def execute_cell(context):\n{indented}\n    return {{}}'.format(
                indented=indented
            )

        return code

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent each non-empty line by the given number of spaces."""
        indent = ' ' * spaces
        lines = code.split('\n')
        return '\n'.join(indent + line if line.strip() else line for line in lines)


def combine_workflow_cells(plan: WorkflowPlan, workflow_description: str = "") -> str:
    """Combine workflow cells into a single executable script."""
    combiner = WorkflowCombiner(plan, workflow_description)
    return combiner.combine()
