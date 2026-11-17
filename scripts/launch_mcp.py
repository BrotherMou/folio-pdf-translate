#!/usr/bin/env python3
"""Launch the configured project interpreter without shell or global installs."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
interpreter = root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
if not interpreter.is_file():
    print("Project environment is missing. Run scripts/setup.ps1 on Windows or scripts/setup.sh on macOS.",
          file=sys.stderr)
    raise SystemExit(1)
os.chdir(root)
os.execv(str(interpreter), [str(interpreter), "-m", "server", "serve"])
