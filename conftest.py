"""Ensures the stephen/ directory is importable so `import el406_backend` works
under a bare `pytest` invocation as well as `python3 -m pytest`."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
