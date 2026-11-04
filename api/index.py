"""Vercel entry point with robust path resolution."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

_flask = create_app()


def app(environ, start_response):
    # Vercel preserves the incoming URL in REQUEST_URI or RAW_URI
    raw_uri = environ.get("RAW_URI") or environ.get("REQUEST_URI") or ""
    incoming_path = raw_uri.split("?")[0] if raw_uri else ""

    path = (
        incoming_path
        or environ.get("HTTP_X_MATCHED_PATH")
        or environ.get("HTTP_X_INVOKE_PATH")
        or environ.get("PATH_INFO", "/")
    )

    if path.startswith("/api/index.py"):
        path = path[len("/api/index.py"):] or "/"
    elif path.startswith("/api/index"):
        path = path[len("/api/index"):] or "/"

    environ["PATH_INFO"] = path or "/"
    environ["SCRIPT_NAME"] = ""
    return _flask(environ, start_response)
