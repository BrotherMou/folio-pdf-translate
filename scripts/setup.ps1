param(
    [ValidateSet("win-x64", "win-arm64")]
    [string]$Runtime = "win-x64"
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source
Get-Command dotnet -ErrorAction Stop | Out-Null
& $Python -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
$VenvConfig = Join-Path $ProjectRoot '.venv/pyvenv.cfg'
if ((Test-Path $VenvConfig) -and (Select-String -Path $VenvConfig -Pattern 'include-system-site-packages = true' -Quiet)) {
    throw 'Existing .venv uses global packages. Rename it, then run setup again.'
}
& $Python -m venv (Join-Path $ProjectRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$ProjectPython = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
& $ProjectPython -m pip install --require-hashes -r (Join-Path $ProjectRoot 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $ProjectPython -m pip install --no-deps --no-build-isolation -e $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
& (Join-Path $PSScriptRoot 'build-engine.ps1') -Runtime $Runtime
if ($LASTEXITCODE -ne 0) { throw 'Engine build failed.' }
& $ProjectPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
Write-Host 'Setup complete. Configure your MCP client using README.md.'
