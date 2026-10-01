#!/usr/bin/env python3
"""Compatibility entry point for the separately preserved cleanup tool."""
from pathlib import Path
import runpy

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "least-used-cleanup" / "least_used_cleanup_server.py"

if __name__ == "__main__":
    runpy.run_path(str(_TOOL), run_name="__main__")
else:
    _namespace = runpy.run_path(str(_TOOL))
    globals().update({name: value for name, value in _namespace.items() if not name.startswith("__")})
