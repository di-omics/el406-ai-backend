"""Ensures the repository root is importable so `import el406_backend` works
under a bare `pytest` invocation as well as `python3 -m pytest`.

This file sits at the repository root, next to `el406_backend/` and `tests/`, so
its own directory is the path to add."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
