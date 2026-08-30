[CmdletBinding()]
param(
    [ValidateSet("core", "ml", "observability", "full", "dev")]
    [string]$Profile = "core"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "web\backend\.venv\Scripts\python.exe"
$controller = Join-Path $root "scripts\platformctl.py"
$envFile = Join-Path $root ".env"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment is missing. Run: python scripts/platformctl.py --mode native --profile $Profile bootstrap --install-deps"
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Repository .env is missing. Copy .env.example to .env and configure it before startup."
}

# Workstation startup is intentionally process-managed. Production Windows
# deployments opt into SCM separately with LEAN_NATIVE_MANAGER=windows-scm.
$env:LEAN_NATIVE_MANAGER = "local"

Push-Location $root
try {
    & $python $controller --mode native --profile $Profile restart
    if ($LASTEXITCODE -ne 0) {
        throw "Platform restart failed with exit code $LASTEXITCODE."
    }

    Start-Sleep -Seconds 2
    & $python $controller --mode native --profile $Profile status
    if ($LASTEXITCODE -ne 0) {
        throw "Platform started but one or more processes are not ready. Check web\runtime\logs."
    }

    Write-Host "Platform is running at http://127.0.0.1:8000"
}
finally {
    Pop-Location
}
