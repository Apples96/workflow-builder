"""Unit tests for enhancer questions/warnings extraction"""

from api.workflow.core.enhancer import WorkflowEnhancer


class TestEnhancerExtraction:
    """Test enhancer extraction methods"""

    def test_extract_questions_with_ambiguity(self):
        """Test extraction of numbered questions from QUESTIONS AND LIMITATIONS section"""
        enhancer = WorkflowEnhancer()

        output_with_questions = """
STEP 1.1: Extract reference number
QUESTIONS AND LIMITATIONS:
⚠️ AMBIGUITY DETECTED - Clarification needed:

1. Which reference number do you mean?
2. What format is expected?
"""

        extracted = enhancer._extract_questions_and_warnings(output_with_questions)

        assert len(extracted["questions"]) >= 2
        assert any("reference number" in q.lower() for q in extracted["questions"])
        assert any("format" in q.lower() for q in extracted["questions"])
        assert len(extracted["warnings"]) >= 1
        assert "AMBIGUITY" in extracted["warnings"][0]

    def test_extract_skips_none_entries(self):
        """Test that 'None' entries are filtered out"""
        enhancer = WorkflowEnhancer()

        output_with_none = """
STEP 1.1: Do something clear
QUESTIONS AND LIMITATIONS: None
"""

        extracted = enhancer._extract_questions_and_warnings(output_with_none)

        assert len(extracted["questions"]) == 0
        assert len(extracted["warnings"]) == 0

    def test_extract_handles_multiple_sections(self):
        """Test extraction from multiple QUESTIONS AND LIMITATIONS sections"""
        enhancer = WorkflowEnhancer()

        output_multiple = """
STEP 1.1: First step
QUESTIONS AND LIMITATIONS: None

STEP 2.1: Second step
QUESTIONS AND LIMITATIONS:
1. Question about step 2?

STEP 3.1: Third step
QUESTIONS AND LIMITATIONS:
⚠️ Warning about step 3
"""

        extracted = enhancer._extract_questions_and_warnings(output_multiple)

        assert len(extracted["questions"]) >= 1
        assert len(extracted["warnings"]) >= 1

    def test_extract_handles_empty_text(self):
        """Test extraction with empty or minimal text"""
        enhancer = WorkflowEnhancer()

        # Empty text
        extracted = enhancer._extract_questions_and_warnings("")
        assert len(extracted["questions"]) == 0
        assert len(extracted["warnings"]) == 0

        # Text without QUESTIONS AND LIMITATIONS sections
        output_no_sections = """
STEP 1.1: Do something
STEP 2.1: Do something else
"""
        extracted = enhancer._extract_questions_and_warnings(output_no_sections)
        assert len(extracted["questions"]) == 0
        assert len(extracted["warnings"]) == 0

    def test_extract_handles_french_none(self):
        """Test that French 'None' variants are filtered out"""
        enhancer = WorkflowEnhancer()

        output_french = """
STEP 1.1: Faire quelque chose
QUESTIONS AND LIMITATIONS: Aucune
"""

        extracted = enhancer._extract_questions_and_warnings(output_french)

        assert len(extracted["questions"]) == 0
        assert len(extracted["warnings"]) == 0

    def test_extract_non_numbered_question(self):
        """Test extraction of non-numbered question text"""
        enhancer = WorkflowEnhancer()

        output_non_numbered = """
STEP 1.1: Do something
QUESTIONS AND LIMITATIONS:
Please clarify what you mean by reference number.
"""

        extracted = enhancer._extract_questions_and_warnings(output_non_numbered)

        assert len(extracted["questions"]) >= 1
        assert any("reference number" in q.lower() for q in extracted["questions"])
