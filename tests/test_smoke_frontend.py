"""Frontend smoke tests.

Designed to catch the class of bug where the served page works against one
local origin (e.g. http://localhost:8000) but breaks against another
(e.g. http://127.0.0.1:8000) due to a hardcoded API URL in the JS that
collides with the browser's same-origin policy.

This test set is deliberately offline: it inspects index.html statically and
exercises the FastAPI app via TestClient. It does NOT spin up uvicorn or
Playwright. The static check is the real teeth — anyone reintroducing a
hardcoded ``http://localhost:8000`` fetch URL gets caught at CI time.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).parent.parent
INDEX_HTML_PATH = PROJECT_ROOT / "index.html"


@pytest.fixture(scope="module")
def index_html_source() -> str:
    """Load the builder's index.html once per module."""
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client() -> TestClient:
    """In-process FastAPI client — no network, no uvicorn."""
    from api.main import app
    return TestClient(app)


@pytest.mark.unit
def test_index_html_exists():
    """Sanity: the file the backend serves at GET / actually exists."""
    assert INDEX_HTML_PATH.exists(), "index.html missing — backend GET / will 404"


@pytest.mark.unit
def test_no_hardcoded_absolute_fetch_urls(index_html_source: str):
    """No fetch() / XHR call should hardcode an http:// or https:// origin.

    A hardcoded ``fetch('http://localhost:8000/api/...')`` works only when
    the page is also served from localhost:8000. Browsers treat 127.0.0.1
    and localhost as different origins; cross-origin fetches without a
    matching ``Access-Control-Allow-Origin`` header are blocked.

    Whitelist: external CDN scripts (jspdf, chart.js, etc.) are loaded via
    <script src="..."> and are not fetch calls.
    """
    # Match: fetch( "http..." ) or fetch( 'http...' ) or fetch( `http...` )
    bad_patterns = [
        r"""fetch\s*\(\s*['"`]https?://""",
        # XMLHttpRequest.open with absolute URL
        r"""\.open\s*\(\s*['"][A-Z]+['"]\s*,\s*['"]https?://""",
    ]
    offenders = []
    for pat in bad_patterns:
        for m in re.finditer(pat, index_html_source):
            line_start = index_html_source.rfind("\n", 0, m.start()) + 1
            line_end = index_html_source.find("\n", m.start())
            offenders.append(index_html_source[line_start:line_end].strip())
    assert not offenders, (
        "Found hardcoded absolute URLs in fetch/XHR calls — these break in "
        "browsers because of same-origin policy when the page is served "
        "from a different host (e.g. 127.0.0.1 vs localhost). Use a "
        "relative path or template `${{API_BASE}}/...`. Offenders:\n  - "
        + "\n  - ".join(offenders)
    )


@pytest.mark.unit
def test_api_base_is_same_origin_when_page_is_served(index_html_source: str):
    """The ``API_BASE`` constant must be relative (no hardcoded origin) when
    the page is being served by any host. The only valid hardcoded value is
    for the ``file://`` protocol case, where there is no host.

    Concretely: the JS we ship has the shape

        const API_BASE = (window.location.protocol === 'file:')
            ? 'http://localhost:8000/api'   // file:// fallback
            : '/api';                       // any served page

    This test parses out the second branch and asserts it is a relative
    path. If anyone changes the served-page branch to a hardcoded URL, the
    127.0.0.1 vs localhost CORS bug returns.
    """
    # Find the API_BASE declaration block. It can span a few lines.
    match = re.search(
        r"const\s+API_BASE\s*=\s*([^;]+?);",
        index_html_source,
        re.DOTALL,
    )
    assert match, (
        "Could not find `const API_BASE = ...;` in index.html. If you "
        "renamed it, update this test to match."
    )
    decl = match.group(1)

    # The expression must produce a relative path for any served page.
    # Either the entire RHS is a string literal that is relative, or it
    # is a ternary whose served-page branch is relative.
    served_page_branches = re.findall(r"['\"]([^'\"]*)['\"]", decl)
    assert served_page_branches, "Could not parse string literals in API_BASE"

    # A relative path: empty string or starts with '/' (and not '//').
    def is_relative(s: str) -> bool:
        return s == "" or (s.startswith("/") and not s.startswith("//"))

    relative_branches = [s for s in served_page_branches if is_relative(s)]
    absolute_branches = [s for s in served_page_branches if not is_relative(s)]

    assert relative_branches, (
        "API_BASE has no relative branch — every value is an absolute URL. "
        "At least one branch must be relative ('/api') so same-origin "
        "fetches work regardless of whether the page is served from "
        "localhost or 127.0.0.1. Found values: {}".format(served_page_branches)
    )

    # Absolute branches are only acceptable as a file:// fallback and must
    # be guarded by a `protocol === 'file:'` check, NOT by hostname.
    if absolute_branches:
        assert "protocol" in decl and "file:" in decl, (
            "API_BASE has an absolute URL branch ({}) that is NOT guarded "
            "by `window.location.protocol === 'file:'`. This brings back "
            "the 127.0.0.1 vs localhost CORS bug. Either remove the "
            "absolute URL or guard it on the file:// protocol.".format(absolute_branches)
        )
        # And the absolute branch must NOT be guarded only on hostname.
        assert "hostname" not in decl or "protocol" in decl, (
            "API_BASE branch is gated on hostname instead of protocol — "
            "this is the exact pattern that broke in production. Use "
            "`window.location.protocol === 'file:'` instead."
        )


@pytest.mark.unit
def test_get_root_serves_index_html(client: TestClient):
    """GET / must return the index.html the rest of these tests inspect.

    Catches: someone moves the file, renames the route, or breaks the
    no-cache headers in a way that throws a 500.
    """
    r = client.get("/")
    assert r.status_code == 200, "GET / failed: {} {}".format(r.status_code, r.text[:200])
    assert "<!DOCTYPE html>" in r.text or "<html" in r.text.lower(), (
        "GET / did not return HTML"
    )
    # The served version should match what we statically inspected (no
    # weird transformation in the route handler).
    assert "API_BASE" in r.text


@pytest.mark.unit
def test_critical_buttons_present(index_html_source: str):
    """The user-visible deploy/download buttons must exist with the IDs the
    JS expects, otherwise click handlers and "enable on workflow created"
    code can never fire.

    Catches: a stray edit that drops a button or renames its ID.
    """
    required_button_ids = [
        "packageButton",        # Download Workflow Package
        "deployWebButton",      # Deploy as Web App
        "deployMcpButton",      # Deploy as MCP Server
        "mcpPackageButton",     # Download MCP Package
    ]
    for bid in required_button_ids:
        # Match either id="x" or id='x' or id=x
        pat = r"""id=['"]?{}['"]?""".format(re.escape(bid))
        assert re.search(pat, index_html_source), (
            "Required button id `{}` is missing from index.html — the JS "
            "that toggles disabled state will throw on null element.".format(bid)
        )


@pytest.mark.unit
def test_cors_allows_same_origin_dev_hosts(client: TestClient):
    """Backend CORS must accept the two common local dev origins so that
    even if a future page IS served cross-origin (separate dev server),
    pre-flighted fetches don't get rejected.

    This is defence-in-depth: my preferred fix is "use relative paths"
    (covered above), but if someone bypasses that, CORS should still let
    real same-machine traffic through.
    """
    # We probe the CORS preflight by sending an OPTIONS request with the
    # standard headers a browser would send.
    for origin in ("http://localhost:8000", "http://127.0.0.1:8000"):
        r = client.options(
            "/api/files/upload",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # FastAPI/Starlette's CORSMiddleware returns 200 for accepted
        # preflights and 400 for rejected ones (when the origin isn't in
        # allow_origins).
        if r.status_code == 400:
            pytest.fail(
                "CORS preflight rejected origin {} with 400. Add it to the "
                "allow_origins list in api/main.py — otherwise a browser "
                "served the page from {} and fetching against /api/... "
                "will fail.".format(origin, origin)
            )
        # If accepted, the response should echo back the origin in
        # Access-Control-Allow-Origin.
        assert r.headers.get("access-control-allow-origin") in (origin, "*"), (
            "CORS preflight for {} did not return Access-Control-Allow-Origin "
            "matching the request origin (got: {!r}). The browser will "
            "block the real request.".format(
                origin, r.headers.get("access-control-allow-origin")
            )
        )
