"""
Workflow Description Enhancer

This module handles enhancing raw workflow descriptions into detailed,
actionable specifications using Claude AI. It separates the enhancement
logic from the core workflow generation for better maintainability.

Key Features:
    - Language preservation (French/English/etc.)
    - Automatic parallelization analysis and layer-based structuring
    - Ambiguity detection and clarification requests
    - Paradigm API tool selection guidance
    - Detailed step-by-step workflow specifications

Architecture:
    - Loads enhancement prompt from markdown file
    - Uses Anthropic Claude for intelligent enhancement
    - Automatically analyzes for parallelization opportunities
    - Returns layer-structured enhancement results
    - Maintains context for code generation
"""

import logging
from pathlib import Path
from typing import Dict, Any, List
from anthropic import Anthropic

logger = logging.getLogger(__name__)


def load_enhancement_prompt() -> str:
    """
    Load the workflow enhancement prompt template from markdown file.
    
    Returns:
        str: The enhancement prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "enhancer_prompt.md"
        
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"✅ Loaded enhancement prompt from {prompt_file}")
            return content
        else:
            logger.warning(f"⚠️ Enhancement prompt not found at {prompt_file}")
            return ""
    except Exception as e:
        logger.error(f"❌ Error loading enhancement prompt: {e}")
        return ""


class WorkflowEnhancer:
    """
    Enhances raw workflow descriptions into detailed specifications.
    
    This class takes user-provided natural language workflow descriptions
    and transforms them into comprehensive, step-by-step specifications
    that can be effectively converted to executable code.
    
    Features:
        - Language preservation (responds in same language as input)
        - Automatic parallelization optimization
        - Ambiguity detection and clarification requests
        - Paradigm API tool selection guidance
        - Professional output formatting specifications
    """
    
    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize the workflow enhancer.
        
        Args:
            anthropic_client: Configured Anthropic client for AI enhancement
        """
        self.anthropic_client = anthropic_client
        self._enhancement_prompt = None
    
    @property
    def enhancement_prompt(self) -> str:
        """
        Get the enhancement prompt, loading it lazily on first access.
        
        Returns:
            str: The enhancement prompt template
        """
        if self._enhancement_prompt is None:
            self._enhancement_prompt = load_enhancement_prompt()
            
            # Fallback prompt if file loading fails
            if not self._enhancement_prompt:
                logger.warning("⚠️ Using fallback enhancement prompt")
                self._enhancement_prompt = self._get_fallback_prompt()
        
        return self._enhancement_prompt
    
    def _get_fallback_prompt(self) -> str:
        """
        Get a minimal fallback prompt if the main prompt file cannot be loaded.
        
        Returns:
            str: Basic enhancement prompt
        """
        return """You are an AI assistant that helps create detailed workflow descriptions.

Your task is to enhance the user's workflow description into clear, specific steps.

CRITICAL RULES:
1. Respond in the EXACT SAME LANGUAGE as the user's input
2. Break down workflows into specific steps
3. Identify operations that can run in parallel for better performance
4. Preserve ALL details from the original description

For each step, use this format:

STEP X: [Detailed description of what needs to be done]

QUESTIONS AND LIMITATIONS: [List any unclear points or missing information]

Enhance this workflow description:"""

    async def enhance_workflow_description(self, raw_description: str) -> Dict[str, Any]:
        """
        Enhance a raw workflow description using Claude AI to create a more detailed,
        actionable workflow specification with proper tool usage and clear steps.
        
        Args:
            raw_description: User's initial natural language workflow description
            
        Returns:
            Dict containing enhanced description, questions, and warnings
            
        Raises:
            Exception: If enhancement fails due to API or processing errors
        """
        try:
            user_message = f"Raw workflow description: {raw_description}"
            
            logger.info(f"🔄 Enhancing workflow description: {raw_description[:100]}...")
            
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=12000,  # Increased for complex workflows
                system=self.enhancement_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            result_text = response.content[0].text.strip()
            
            if not result_text:
                logger.warning("⚠️ Empty enhancement result, using original description")
                result_text = raw_description
            
            logger.info(f"✅ Enhanced workflow description ({len(result_text)} chars)")
            
            # Parse plain text response
            # Note: Questions and warnings are now embedded in the enhanced steps

            # Automatically analyze for parallelization and restructure into layers
            logger.info("🔄 Analyzing enhanced description for parallelization...")
            parallelized_result = await self._analyze_parallelization(result_text)

            return {
                "enhanced_description": parallelized_result["layer_structured_description"],
                "questions": [],  # Questions are embedded in QUESTIONS AND LIMITATIONS sections
                "warnings": [],   # Warnings are embedded in QUESTIONS AND LIMITATIONS sections
                "parallelization_info": parallelized_result.get("parallelization_info", {})
            }

        except Exception as e:
            error_msg = f"Workflow description enhancement failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

    async def _analyze_parallelization(self, enhanced_description: str) -> Dict[str, Any]:
        """
        Analyze enhanced workflow description for parallelization opportunities.

        This method takes the sequentially-enhanced workflow description and
        restructures it into execution layers where:
        - Steps in the same layer can run in parallel
        - Layer N+1 only starts after all cells in layer N complete
        - Data dependencies are respected (a step that needs output from another
          must be in a later layer)

        Args:
            enhanced_description: The enhanced step-by-step workflow description

        Returns:
            Dict containing:
                - layer_structured_description: Description restructured with layers
                - parallelization_info: Metadata about the parallelization
        """
        parallelization_prompt = self._get_parallelization_prompt()

        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=12000,
                system=parallelization_prompt,
                messages=[{"role": "user", "content": f"ENHANCED WORKFLOW DESCRIPTION:\n{enhanced_description}"}]
            )

            result_text = response.content[0].text.strip()

            if not result_text:
                logger.warning("⚠️ Empty parallelization result, using original description")
                return {
                    "layer_structured_description": enhanced_description,
                    "parallelization_info": {"layers": 1, "parallel_steps": False}
                }

            # Parse the parallelization info from the response
            parallelization_info = self._parse_parallelization_info(result_text)

            logger.info(f"✅ Parallelization analysis complete: {parallelization_info['total_layers']} layers, {parallelization_info['parallel_steps_count']} parallel steps")

            return {
                "layer_structured_description": result_text,
                "parallelization_info": parallelization_info
            }

        except Exception as e:
            logger.error(f"❌ Parallelization analysis failed: {str(e)}")
            # Return original description if parallelization fails
            return {
                "layer_structured_description": enhanced_description,
                "parallelization_info": {"layers": 1, "parallel_steps": False, "error": str(e)}
            }

    def _get_parallelization_prompt(self) -> str:
        """
        Get the system prompt for parallelization analysis.

        Returns:
            str: System prompt for the parallelization LLM call
        """
        return """You are a workflow parallelization expert. Your task is to analyze a sequential workflow description and restructure it into execution layers for optimal parallel execution.

## CRITICAL LANGUAGE PRESERVATION RULE
- Respond in the EXACT SAME LANGUAGE as the input description
- If the input is in French, your entire output MUST be in French
- If the input is in English, your entire output MUST be in English
- PRESERVE all technical terminology exactly as provided

## YOUR TASK
1. Analyze the provided enhanced workflow description
2. Identify data dependencies between steps
3. Group steps that can run in parallel into the same layer
4. Restructure the description with layer-based numbering

## PARALLELIZATION RULES

### What CAN run in parallel (same layer):
- Steps that don't depend on each other's outputs
- Multiple extractions from different documents
- Multiple API calls with independent inputs
- Multiple analyses that don't share data dependencies

### What CANNOT run in parallel (must be in different layers):
- Steps where one needs the output of another
- Sequential processing where order matters
- Steps that modify shared state
- Aggregation/merge steps that need results from parallel steps

### Data Dependency Analysis:
- If Step A produces variable X and Step B needs variable X → B must be in a later layer than A
- If Steps A and B both only need variables from previous layers → A and B can be in the same layer
- Merge/combine steps ALWAYS come after the steps they merge

## OUTPUT FORMAT

Use this exact format for the layer-structured description:

```
LAYER 1:
  STEP 1.1: [Description of the step]
  [QUESTIONS AND LIMITATIONS if any]

---

LAYER 2 (PARALLEL):
  STEP 2.1: [First parallel step description]
  [QUESTIONS AND LIMITATIONS if any]

  STEP 2.2: [Second parallel step description]
  [QUESTIONS AND LIMITATIONS if any]

  STEP 2.3: [Third parallel step description]
  [QUESTIONS AND LIMITATIONS if any]

---

LAYER 3:
  STEP 3.1: [Merge/aggregate step that uses results from 2.1, 2.2, 2.3]
  [QUESTIONS AND LIMITATIONS if any]

---

[Continue for all layers...]

PARALLELIZATION SUMMARY:
- Total layers: X
- Parallel layers: Y (layers with multiple steps)
- Steps that run in parallel: [list the step numbers]
- Data dependencies: [brief description of key dependencies]
```

## IMPORTANT NOTES

1. **Layer numbering**: Layers are numbered 1, 2, 3, etc.
2. **Step numbering**: Steps within a layer are numbered X.1, X.2, X.3, etc.
3. **Single-step layers**: If a layer has only one step, number it as X.1
4. **Mark parallel layers**: Add "(PARALLEL)" after "LAYER X" if the layer has multiple steps
5. **Preserve all details**: Keep ALL the original step descriptions, just restructure them
6. **Keep QUESTIONS AND LIMITATIONS**: Preserve these sections under each step
7. **Always include summary**: End with PARALLELIZATION SUMMARY section

## EXAMPLE

Input (sequential):
```
STEP 1: Wait for documents to be indexed
STEP 2: Extract name from Document A
STEP 3: Extract date from Document B
STEP 4: Extract amount from Document C
STEP 5: Combine all extracted data into final report
```

Output (parallelized):
```
LAYER 1:
  STEP 1.1: Wait for documents to be indexed
  QUESTIONS AND LIMITATIONS: None

---

LAYER 2 (PARALLEL):
  STEP 2.1: Extract name from Document A
  QUESTIONS AND LIMITATIONS: None

  STEP 2.2: Extract date from Document B
  QUESTIONS AND LIMITATIONS: None

  STEP 2.3: Extract amount from Document C
  QUESTIONS AND LIMITATIONS: None

---

LAYER 3:
  STEP 3.1: Combine all extracted data into final report (uses outputs from 2.1, 2.2, 2.3)
  QUESTIONS AND LIMITATIONS: None

---

PARALLELIZATION SUMMARY:
- Total layers: 3
- Parallel layers: 1 (Layer 2)
- Steps that run in parallel: 2.1, 2.2, 2.3
- Data dependencies: Layer 2 needs indexed documents from Layer 1; Layer 3 needs extracted data from all Layer 2 steps
```

Now analyze and restructure the following workflow description:"""

    def _parse_parallelization_info(self, result_text: str) -> Dict[str, Any]:
        """
        Parse parallelization metadata from the LLM response.

        Args:
            result_text: The LLM response with layer-structured description

        Returns:
            Dict with parallelization metadata
        """
        info = {
            "total_layers": 1,
            "parallel_layers": 0,
            "parallel_steps_count": 0,
            "parallel_steps": [],
            "has_parallelization": False
        }

        try:
            # Count layers by looking for "LAYER X:" patterns
            import re
            layer_matches = re.findall(r'LAYER\s+(\d+)', result_text, re.IGNORECASE)
            if layer_matches:
                info["total_layers"] = max(int(m) for m in layer_matches)

            # Count parallel layers (those marked with PARALLEL)
            parallel_layer_matches = re.findall(r'LAYER\s+\d+\s*\(PARALLEL\)', result_text, re.IGNORECASE)
            info["parallel_layers"] = len(parallel_layer_matches)

            # Count steps in format X.Y
            step_matches = re.findall(r'STEP\s+(\d+\.\d+)', result_text, re.IGNORECASE)
            info["parallel_steps"] = step_matches

            # Count parallel steps (those not ending in .1 in parallel layers)
            # This is a rough estimate - multiple steps in same layer are parallel
            layer_step_counts = {}
            for step in step_matches:
                layer = step.split('.')[0]
                layer_step_counts[layer] = layer_step_counts.get(layer, 0) + 1

            # Steps in layers with more than 1 step are parallel
            info["parallel_steps_count"] = sum(
                count for count in layer_step_counts.values() if count > 1
            )

            info["has_parallelization"] = info["parallel_layers"] > 0

            # Try to extract from summary section if present
            if "PARALLELIZATION SUMMARY" in result_text.upper():
                summary_section = result_text.upper().split("PARALLELIZATION SUMMARY")[1]

                # Extract total layers
                total_match = re.search(r'TOTAL LAYERS:\s*(\d+)', summary_section)
                if total_match:
                    info["total_layers"] = int(total_match.group(1))

                # Extract parallel layers count
                parallel_match = re.search(r'PARALLEL LAYERS:\s*(\d+)', summary_section)
                if parallel_match:
                    info["parallel_layers"] = int(parallel_match.group(1))

        except Exception as e:
            logger.warning(f"Failed to parse parallelization info: {e}")

        return info
    