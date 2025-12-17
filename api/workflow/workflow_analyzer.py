"""
Workflow Analyzer
==================

Analyzes workflow code to automatically generate UI configuration.
Uses Claude to understand the workflow requirements and generate appropriate UI.
"""

import json
import anthropic
from typing import Dict, Any
from api.config import settings


async def analyze_workflow_for_ui(workflow_code: str, workflow_name: str, workflow_description: str) -> Dict[str, Any]:
    """
    Analyze workflow code with Claude to generate UI configuration.

    Args:
        workflow_code: The Python code of the workflow
        workflow_name: Name of the workflow
        workflow_description: Description of the workflow

    Returns:
        UI configuration dict with:
        - workflow_name: str
        - workflow_description: str
        - requires_text_input: bool
        - text_input_label: str (optional)
        - text_input_placeholder: str (optional)
        - requires_files: bool
        - files: List[Dict] (optional)
    """

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    analysis_prompt = f"""Analyze this Python workflow code and extract the user interface requirements.

Workflow Name: {workflow_name}
Workflow Description: {workflow_description}

Workflow Code:
```python
{workflow_code}
```

Based on the code above, generate a JSON configuration describing the required user interface.

IMPORTANT ANALYSIS GUIDELINES:

**TEXT INPUT DETECTION:**
1. Check if `execute_workflow` function accepts a `user_input` parameter
2. Search if `user_input` is USED in the code (not just received):
   - Look for: user_input in function calls, queries, conditions
   - Example: `query=user_input`, `search_query = user_input`, etc.
3. If user_input is used ANYWHERE in the workflow, set requires_text_input=true
4. Determine if text input is optional or required:
   - If there's a fallback value like `user_input if user_input.strip() else "default"`, it's optional
   - If user_input is used directly without fallback, it may be required
5. Create appropriate label and placeholder based on how user_input is used

**FILE INPUT DETECTION:**
6. Look for `attached_file_ids`, `file_ids`, `document_ids` variables
7. **CRITICAL**: Check for CONDITIONAL logic (if/else) with file variables:
   - Pattern: `if attached_file_ids:... else:...` means files are OPTIONAL
   - Set requires_files=true but file.required=false for optional files
   - The workflow can work both WITH and WITHOUT files
8. Count files needed by looking at array indices: [0], [1], [2], etc.
9. Infer file labels from:
   - Workflow description (DC4, RIB, Avis, etc.)
   - API call context (what is being analyzed)
   - Use French labels like "Document à analyser", "Document 1", "Document 2"
10. Set file.required field correctly:
    - false if workflow has fallback logic for missing files
    - true if workflow will fail without the file

**MULTIPLE FILES DETECTION:**
11. **CRITICAL**: Detect if the workflow expects MULTIPLE DIFFERENT TYPES of documents:
    - Look for descriptions like "1 fiche de poste + 5 CV", "DC4 + RIB + BOAMP", "facture + bon de commande"
    - Look for array indexing with different semantic meanings:
      * `attached_files[0]` = first document (e.g., job description)
      * `attached_files[1:6]` = next 5 documents (e.g., CVs)
    - Look for variable names suggesting different types: `job_description_file_id`, `cv_file_ids`
    - Look for comments describing different document types per position

12. **WHEN TO CREATE MULTIPLE SEPARATE FILE FIELDS:**
    - If workflow mentions DIFFERENT document types at SPECIFIC positions, create SEPARATE fields:
      * Example: "exactement 6 fichiers : 1 fiche de poste + 5 CV"
        → Create 2 fields:
           1. "Fiche de poste" (required=true, multiple=false)
           2. "CV des candidats" (required=true, multiple=true, max_files=5)
      * Example: "DC4, RIB, BOAMP, Acte d'engagement, JOUE"
        → Create 5 separate fields, one for each document type

13. **WHEN TO CREATE ONE FIELD WITH multiple=true:**
    - If workflow processes SAME type of documents (no specific positions):
      * Example: "plusieurs factures fournisseurs" → ONE field "Factures" with multiple=true
      * Example: "1 à 10 documents PDF à analyser" → ONE field with multiple=true, max_files=10

14. **HOW TO DETECT DOCUMENT TYPES:**
    - Search workflow description for document type names (facture, CV, RIB, DC4, BOAMP, etc.)
    - Look for array slicing patterns: `attached_files[0]` vs `attached_files[1:]` = 2 types
    - Check for len() requirements: `len(attached_files) != 6` = expects specific count
    - Extract document names from error messages and descriptions

Output format (JSON only, no markdown):
{{
  "workflow_name": "{workflow_name}",
  "workflow_description": "Brief user-friendly description in French",
  "requires_text_input": true/false,
  "text_input_label": "Label for text input (if required)",
  "text_input_placeholder": "Placeholder text in French",
  "requires_files": true/false,
  "files": [
    {{
      "label": "User-friendly name in French",
      "description": "What this file is for",
      "required": true/false,
      "multiple": true/false,
      "max_files": <number>  // Only if multiple=true
    }}
  ]
}}

Return ONLY valid JSON, no markdown code blocks."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": analysis_prompt
                }
            ]
        )

        # Extract JSON from response
        response_text = response.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        # Parse JSON
        ui_config = json.loads(response_text)

        # Validate required fields
        if "workflow_name" not in ui_config:
            ui_config["workflow_name"] = workflow_name
        if "workflow_description" not in ui_config:
            ui_config["workflow_description"] = workflow_description
        if "requires_text_input" not in ui_config:
            ui_config["requires_text_input"] = True
        if "requires_files" not in ui_config:
            ui_config["requires_files"] = False

        return ui_config

    except Exception as e:
        # Raise error instead of returning fallback
        # The endpoint in main.py will catch this and return HTTP 500
        raise Exception(f"Failed to analyze workflow with Claude: {str(e)}")


async def generate_simple_description(workflow_description: str, workflow_name: str = "") -> str:
    """
    Generate a simple, user-friendly description (1-3 lines) from a technical workflow description.

    Args:
        workflow_description: The technical description (may include steps, details, etc.)
        workflow_name: Optional workflow name for context

    Returns:
        A short, simple description in French (1-3 lines maximum)
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    prompt = f"""Tu es un assistant qui crée des descriptions courtes et simples pour des workflows.

Workflow: {workflow_name if workflow_name else "Sans nom"}

Description technique:
{workflow_description}

Génère UNE description simple et claire en français de ce workflow en maximum 1 à 3 lignes.
La description doit expliquer ce que fait le workflow de manière compréhensible pour un utilisateur non-technique.

Exemples de bonnes descriptions:
- "Ce workflow compare plusieurs documents pour en extraire les différences de tarif"
- "Extrait les informations de contact (noms, adresses, emails) des documents uploadés"
- "Analyse des factures pour identifier les montants et dates de paiement"
- "Compare les conditions contractuelles entre deux contrats"

NE PAS inclure:
- Les steps techniques (STEP 1a, STEP 1b, etc.)
- Les détails d'implémentation
- Les références à paradigm_client ou APIs
- Les instructions techniques

Réponds UNIQUEMENT avec la description courte, sans introduction ni explication."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        description = response.content[0].text.strip()

        # Remove quotes if present
        if description.startswith('"') and description.endswith('"'):
            description = description[1:-1]
        if description.startswith("'") and description.endswith("'"):
            description = description[1:-1]

        # Limit to 300 characters max
        if len(description) > 300:
            description = description[:297] + "..."

        return description

    except Exception as e:
        # Fallback: return first line of original description if generation fails
        first_line = workflow_description.split('\n')[0]
        if len(first_line) > 300:
            return first_line[:297] + "..."
        return first_line
