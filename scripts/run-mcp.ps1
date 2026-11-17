$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $PythonPath)) { throw 'Run scripts/setup.ps1 first.' }
& $PythonPath (Join-Path $ProjectRoot 'scripts/launch_mcp.py')
exit $LASTEXITCODE
