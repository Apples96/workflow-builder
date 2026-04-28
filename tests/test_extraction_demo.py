"""
Demo script to show the extraction functionality without requiring API calls
"""

from api.workflow.core.enhancer import WorkflowEnhancer


def demo_extraction():
    """Demonstrate the extraction functionality"""
    enhancer = WorkflowEnhancer()

    # Example enhanced description with questions and warnings
    example_output = """
LAYER 1:
  STEP 1.1: Extract reference number from invoice
  QUESTIONS AND LIMITATIONS:
  ⚠️ AMBIGUITY DETECTED - Clarification needed:

  1. Which reference number do you mean (invoice number, transaction ID, or customer reference)?
  2. What format is expected for the output?

LAYER 2:
  STEP 2.1: Extract date from document
  QUESTIONS AND LIMITATIONS: None

LAYER 3:
  STEP 3.1: Compare amounts
  QUESTIONS AND LIMITATIONS:
  ⚠️ AMBIGUITY DETECTED - The term "amounts" is unclear.

  1. Which amounts should be compared?
  2. What should happen if amounts don't match?
"""

    print("=" * 80)
    print("ENHANCED DESCRIPTION:")
    print("=" * 80)
    print(example_output)
    print()

    # Extract questions and warnings
    extracted = enhancer._extract_questions_and_warnings(example_output)

    print("=" * 80)
    print("EXTRACTED QUESTIONS:")
    print("=" * 80)
    for i, question in enumerate(extracted["questions"], 1):
        print(f"{i}. {question}")
    print()

    print("=" * 80)
    print("EXTRACTED WARNINGS:")
    print("=" * 80)
    for i, warning in enumerate(extracted["warnings"], 1):
        print(f"{i}. {warning}")
    print()

    print("=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    print(f"Total questions extracted: {len(extracted['questions'])}")
    print(f"Total warnings extracted: {len(extracted['warnings'])}")


if __name__ == "__main__":
    demo_extraction()
