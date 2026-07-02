"""
Legacy entry point for GenoScribe.

Kept for backwards compatibility with workflows that run `python genoscribe_app.py`.
This shim ensures the repository's `src/` directory is on `sys.path` and then delegates
to `genoscribe.app.main`, so all fixes live in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from genoscribe.app import main


if __name__ == "__main__":
    main()
