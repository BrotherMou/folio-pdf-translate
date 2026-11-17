param(
    [ValidateSet("win-x64", "win-arm64")]
    [string]$Runtime = "win-x64"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET 10 SDK is required to build. Install it from https://dotnet.microsoft.com/download/dotnet/10.0"
}
$output = Join-Path $projectRoot "bin/windows"
& dotnet publish (Join-Path $projectRoot "engine-windows/PDFTranslateEngine.csproj") -c Release -r $Runtime --self-contained true -o $output
if ($LASTEXITCODE -ne 0) { throw "Windows translation engine build failed." }
Copy-Item (Join-Path $projectRoot "LICENSE") (Join-Path $output "LICENSE") -Force
Copy-Item (Join-Path $projectRoot "engine-windows/THIRD-PARTY-NOTICES.md") (Join-Path $output "THIRD-PARTY-NOTICES.md") -Force
Copy-Item (Join-Path $projectRoot "engine-windows/EXTRACTION.md") (Join-Path $output "EXTRACTION.md") -Force
$notices = Join-Path $output "third-party"
New-Item -ItemType Directory -Path $notices -Force | Out-Null
Copy-Item (Join-Path $projectRoot "engine-windows/third-party/*") $notices -Force
Write-Output (Join-Path $output "pdf-translate-engine.exe")
