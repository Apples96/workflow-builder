# Entry point referenced by the Dockerfile CMD ("api.index:app") and
# therefore by Render's deploy. Do NOT remove — ruff sees `app` as unused
# but it is imported by uvicorn from outside the Python source tree.
from .main import app  # noqa: F401
