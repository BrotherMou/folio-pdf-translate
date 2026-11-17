#!/usr/bin/env python3
"""Print a generic JSON stdio MCP entry for this checkout; do not edit client config."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
if not python.is_file():
    raise SystemExit("Run scripts/setup.ps1 or scripts/setup.sh first.")
print(json.dumps({"mcpServers": {"folio-pdf-translate": {
    "command": str(python), "args": [str(root / "scripts/launch_mcp.py")]
}}}, ensure_ascii=False, indent=2))
