import logging
from typing import Dict, Any, Optional

from ...clients import create_anthropic_client
from ...config import settings
from ..prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


def load_enhancement_prompt() -> str:
    """Load the workflow enhancement prompt template from markdown file."""
    return PromptLoader.load_optional("enhancer")


class WorkflowEnhancer:
    """Enhances raw workflow descriptions into detailed, actionable specifications using Claude AI."""

    def __init__(self, anthropic_client=None):
        self.anthropic_client = anthropic_client or create_anthropic_client()
        self._enhancement_prompt = None
    
    @property
    def enhancement_prompt(self) -> str:
        """Get the enhancement prompt, loading it lazily on first access."""
        if self._enhancement_prompt is None:
            self._enhancement_prompt = load_enhancement_prompt()
            
            if not self._enhancement_prompt:
                logger.warning("⚠️ Using fallback enhancement prompt")
                self._enhancement_prompt = self._get_fallback_prompt()
        
        return self._enhancement_prompt
    
    def _get_fallback_prompt(self) -> str:
        """Return a minimal fallback prompt if the main prompt file cannot be loaded."""
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

    async def enhance_workflow_description(
        self,
        raw_description: str,
        output_example: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enhance a raw workflow description into a detailed, actionable specification."""
        try:
            user_message = "Raw workflow description: {}".format(raw_description)

            if output_example:
                user_message += "\n\n## USER-PROVIDED OUTPUT EXAMPLE\n"
                user_message += "The user has provided the following example of their desired output format. "
                user_message += "Use this to understand the FORMAT, STRUCTURE, and LEVEL OF DETAIL expected:\n\n"
                user_message += "```\n{}\n```\n\n".format(output_example)
                user_message += "Incorporate insights from this example into your step descriptions, especially for the final step."
            
            logger.info(f"🔄 Enhancing workflow description: {raw_description[:100]}...")
            
            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=12000,  # Increased for complex workflows
                system=self.enhancement_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            result_text = response.content[0].text.strip()
            
            if not result_text:
                logger.warning("⚠️ Empty enhancement result, using original description")
                result_text = raw_description
            
            logger.info(f"✅ Enhanced workflow description ({len(result_text)} chars)")

            parallelization_info = self._parse_parallelization_info(result_text)
            logger.info(f"✅ Parallelization: {parallelization_info['total_layers']} layers, {parallelization_info['parallel_steps_count']} parallel steps")

            extracted = self._extract_questions_and_warnings(result_text)
            logger.info(f"✅ Extracted {len(extracted['questions'])} question(s) and {len(extracted['warnings'])} warning(s)")

            return {
                "enhanced_description": result_text,
                "questions": extracted["questions"],
                "warnings": extracted["warnings"],
                "parallelization_info": parallelization_info
            }

        except Exception as e:
            error_msg = f"Workflow description enhancement failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

    def _extract_questions_and_warnings(self, result_text: str) -> Dict[str, list]:
        """Extract questions and warnings from 'QUESTIONS AND LIMITATIONS:' sections."""
        import re

        questions = []
        warnings = []

        try:
            pattern = (
                r'QUESTIONS\s+(?:AND|ET)\s+LIMITATIONS:\s*\n?'
                r'(.*?)'
                r'(?=\n\s*(?:STEP|ÉTAPE|LAYER|COUCHE|---|PARALLELIZATION|SYNTHÈSE|QUESTIONS\s+(?:AND|ET)\s+LIMITATIONS:)|\Z)'
            )
            matches = re.findall(pattern, result_text, re.IGNORECASE | re.DOTALL)

            for match in matches:
                content = match.strip()

                if not content:
                    continue

                none_patterns = [r'^\s*none\.?\s*$', r'^\s*aucune?\.?\s*$']
                is_none = any(re.match(pat, content, re.IGNORECASE) for pat in none_patterns)
                if is_none:
                    continue

                if "AMBIGUITY DETECTED" in content.upper() or "⚠️" in content:
                    warnings.append(content)

                numbered_questions = re.findall(r'^\s*\d+\.\s*(.+)$', content, re.MULTILINE)

                if numbered_questions:
                    questions.extend([q.strip() for q in numbered_questions if q.strip()])
                elif content and not any(re.match(pat, content, re.IGNORECASE) for pat in none_patterns):
                    if content not in warnings:
                        if "AMBIGUITY DETECTED" not in content.upper() and "⚠️" not in content:
                            questions.append(content)

        except Exception as e:
            logger.warning(f"Failed to extract questions and warnings: {e}")

        return {
            "questions": questions,
            "warnings": warnings
        }

    def _parse_parallelization_info(self, result_text: str) -> Dict[str, Any]:
        """Parse parallelization metadata from the layer-structured LLM response."""
        info = {
            "total_layers": 1,
            "parallel_layers": 0,
            "parallel_steps_count": 0,
            "parallel_steps": [],
            "has_parallelization": False
        }

        try:
            import re
            layer_matches = re.findall(r'LAYER\s+(\d+)', result_text, re.IGNORECASE)
            if layer_matches:
                info["total_layers"] = max(int(m) for m in layer_matches)

            parallel_layer_matches = re.findall(r'LAYER\s+\d+\s*\(PARALLEL\)', result_text, re.IGNORECASE)
            info["parallel_layers"] = len(parallel_layer_matches)

            step_matches = re.findall(r'STEP\s+(\d+\.\d+)', result_text, re.IGNORECASE)
            info["parallel_steps"] = step_matches

            layer_step_counts = {}
            for step in step_matches:
                layer = step.split('.')[0]
                layer_step_counts[layer] = layer_step_counts.get(layer, 0) + 1

            info["parallel_steps_count"] = sum(
                count for count in layer_step_counts.values() if count > 1
            )

            info["has_parallelization"] = info["parallel_layers"] > 0

            if "PARALLELIZATION SUMMARY" in result_text.upper():
                summary_section = result_text.upper().split("PARALLELIZATION SUMMARY")[1]

                total_match = re.search(r'TOTAL LAYERS:\s*(\d+)', summary_section)
                if total_match:
                    info["total_layers"] = int(total_match.group(1))

                parallel_match = re.search(r'PARALLEL LAYERS:\s*(\d+)', summary_section)
                if parallel_match:
                    info["parallel_layers"] = int(parallel_match.group(1))

        except Exception as e:
            logger.warning(f"Failed to parse parallelization info: {e}")

        return info
    