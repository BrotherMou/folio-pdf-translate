#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$(uname -s)" != Darwin ]; then
  echo 'Use scripts/setup.ps1 on Windows; other systems are not supported.' >&2
  exit 1
fi
command -v python3 >/dev/null
command -v swift >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
swift --version
# Never reuse a virtual environment that can import global packages.
if [ -f "$PROJECT_ROOT/.venv/pyvenv.cfg" ] && grep -qi 'include-system-site-packages = true' "$PROJECT_ROOT/.venv/pyvenv.cfg"; then
  echo 'Existing .venv uses global packages. Rename it, then run setup again.' >&2
  exit 1
fi
python3 -m venv "$PROJECT_ROOT/.venv"
PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"
"$PROJECT_PYTHON" -m pip install --require-hashes -r "$PROJECT_ROOT/requirements.lock"
"$PROJECT_PYTHON" -m pip install --no-deps --no-build-isolation -e "$PROJECT_ROOT"
sh "$PROJECT_ROOT/scripts/build-engine.sh"
"$PROJECT_PYTHON" -m pip check
echo 'Setup complete. Configure your MCP client using README.md.'
