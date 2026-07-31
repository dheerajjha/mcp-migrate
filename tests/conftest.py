"""Make the package and the standalone scripts importable without a real
editable install (the project's README.md doesn't exist yet, which makes
`pip install -e .` fail on the hatchling readme check)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"

for path in (SRC, SCRIPTS):
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)
