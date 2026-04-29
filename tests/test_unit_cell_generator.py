"""Unit tests for CellCodeGenerator's prompt-building safety.

Designed to catch the class of bug where a contributor adds a literal `{...}`
to the f-style format template of `_build_user_message` without escaping it
to `{{...}}`. The bug observed in production:

    "5. ... they may contain { } that break .format()"

is parsed by `str.format` as a placeholder named `' '` (single space) and
raises `KeyError(' ')` before any LLM call. This test scans the rendered
prompt for that failure shape and parametrises across adversarial inputs to
confirm the template tolerates user-supplied braces in workflow descriptions
and cell metadata.
"""

import string

import pytest

from api.workflow.cell.generator import CellCodeGenerator
from api.workflow.models import CellStatus, WorkflowCell


def _make_generator() -> CellCodeGenerator:
    """Build a CellCodeGenerator without instantiating the Anthropic client.

    `_build_user_message` doesn't touch the client, so we skip __init__ to
    keep this test offline and deterministic.
    """
    return CellCodeGenerator.__new__(CellCodeGenerator)


def _make_cell(**overrides) -> WorkflowCell:
    """Build a minimal WorkflowCell, override fields per-test."""
    defaults = dict(
        id="c1",
        step_number=1,
        name="Document Indexing Setup",
        description="Wait for embeddings, build mapping",
        layer=1,
        inputs_required=[],
        outputs_produced=["document_mapping"],
        status=CellStatus.PENDING,
    )
    defaults.update(overrides)
    return WorkflowCell(**defaults)


@pytest.mark.unit
def test_build_user_message_returns_string():
    """Smoke test: the format template renders without KeyError on plain inputs."""
    g = _make_generator()
    msg = g._build_user_message(
        cell=_make_cell(),
        available_context={},
        workflow_description="A simple workflow that uploads a document.",
    )
    assert isinstance(msg, str)
    assert len(msg) > 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "workflow_description",
    [
        "plain description with no braces",
        # Real-world failure trigger: a URL with a templated placeholder.
        "Call https://api.example.com/search?q={nom_commercial}",
        # The exact pattern that broke production: literal { } as documentation.
        "they may contain { } that break .format()",
        # Doubled braces in user input.
        "JSON example: {{\"key\": \"value\"}}",
        # Only one open or close (malformed but still must not crash).
        "missing close { brace",
        "missing open } brace",
        # Unicode + braces.
        "Recherche d'entreprise pour {entreprise}",
    ],
    ids=[
        "plain",
        "named-placeholder",
        "literal-spaced-braces",
        "doubled-braces",
        "open-only",
        "close-only",
        "unicode-placeholder",
    ],
)
def test_build_user_message_tolerates_braces_in_workflow_description(workflow_description):
    """Adversarial inputs in the workflow_description value must NOT cause format errors.

    The bug we hit was in the TEMPLATE (literal { } between placeholder
    names). This parametrisation locks down the OTHER failure mode: a future
    change that inadvertently double-applies .format() to a value, or a
    template that interpolates a value somewhere that gets re-formatted.
    """
    g = _make_generator()
    msg = g._build_user_message(
        cell=_make_cell(),
        available_context={},
        workflow_description=workflow_description,
    )
    # Value should round-trip into the rendered prompt unchanged.
    assert workflow_description in msg


@pytest.mark.unit
@pytest.mark.parametrize(
    "cell_kwargs",
    [
        {"description": "Plain description"},
        {"description": "URL with {placeholder}"},
        {"description": "literal { } in description"},
        {"name": "Cell with {weird} name"},
        {"inputs_required": ["var_with_{brace}"]},
        {"outputs_produced": ["output_{x}"]},
    ],
    ids=[
        "plain-desc",
        "named-placeholder-desc",
        "spaced-braces-desc",
        "named-placeholder-name",
        "braces-in-input-name",
        "braces-in-output-name",
    ],
)
def test_build_user_message_tolerates_braces_in_cell_metadata(cell_kwargs):
    """Cell metadata fed by the planner must also pass through cleanly."""
    g = _make_generator()
    cell = _make_cell(**cell_kwargs)
    msg = g._build_user_message(
        cell=cell,
        available_context={"var_with_{brace}": "Any"},
        workflow_description="any workflow",
    )
    assert isinstance(msg, str)
    assert len(msg) > 0


@pytest.mark.unit
def test_build_user_message_template_has_only_known_placeholders():
    """Static guard: every {token} in the rendered output must be either
    one of the known named-placeholder slots OR a literal that was meant to
    pass through (in which case the test should be updated explicitly).

    Catches: a future contributor adding a new {something} reference to the
    docstring or instructions section without realising it'll be parsed by
    str.format.
    """
    g = _make_generator()
    g._build_user_message(
        cell=_make_cell(),
        available_context={},
        workflow_description="WORKFLOW_DESC_MARKER",
    )

    # str.Formatter walks the format spec the same way str.format does, so
    # parsing the RENDERED prompt for any remaining {…} groups would fall
    # over because the original placeholders have been substituted away.
    # Instead, parse the SOURCE template directly and check every parsed
    # field name is either: (a) a known placeholder we substitute, or
    # (b) escaped as {{ }} (which the parser surfaces as field_name == "").
    import inspect
    import re

    source = inspect.getsource(CellCodeGenerator._build_user_message)
    # Find the multi-line """...""".format(...) block — its content is the
    # template literal we must vet.
    template_match = re.search(r'message\s*=\s*"""(.*?)"""\.format\(', source, re.DOTALL)
    assert template_match, (
        "could not locate the format template in _build_user_message; "
        "if you refactored it, update this test to point at the new template"
    )
    template = template_match.group(1)

    known_names = {
        "workflow_description",
        "cell_name",
        "cell_description",
        "step_number",
        "tools",
        "inputs",
        "outputs",
    }

    parsed = list(string.Formatter().parse(template))
    seen_names = set()
    for literal_text, field_name, format_spec, conversion in parsed:
        if field_name is None:
            # Plain literal segment, no placeholder. (Doubled braces also
            # surface here as literal text in literal_text.)
            continue
        if field_name == "":
            # Empty field name = positional placeholder ({}). Not used here;
            # if it appears it's a bug. Note: doubled braces ({{ }}) do NOT
            # produce empty-name fields — they show up only in literal_text.
            pytest.fail(
                "Found a positional {{}} placeholder in the format template. "
                "Either name it explicitly or escape literal braces as {{{{ }}}}."
            )
        seen_names.add(field_name)

    unknown = seen_names - known_names
    assert not unknown, (
        "Unknown placeholder(s) in _build_user_message template: {}. "
        "Either add them as kwargs to .format(...), or escape literal braces "
        "in the docstring as {{ }}.".format(sorted(unknown))
    )
