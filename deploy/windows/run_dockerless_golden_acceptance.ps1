[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AcceptanceSpec,
    [Parameter(Mandatory = $true)][string]$RunnerAccount,
    [Parameter(Mandatory = $true)][string]$DotnetPath,
    [string]$Python = "python",
    [string]$EvidencePath = "C:\ProgramData\LeanPlatform\evidence\dockerless-golden.json"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$acceptanceSpecPath = [IO.Path]::GetFullPath($AcceptanceSpec)
$evidenceFile = [IO.Path]::GetFullPath($EvidencePath)
$startedAt = [DateTimeOffset]::UtcNow
$steps = [ordered]@{}
$servicesStarted = $false

function Invoke-CheckedStep {
    param([string]$Name, [scriptblock]$Action)
    $stepStarted = [DateTimeOffset]::UtcNow
    try {
        & $Action
        $steps[$Name] = [ordered]@{
            passed = $true
            durationSeconds = [Math]::Round(
                ([DateTimeOffset]::UtcNow - $stepStarted).TotalSeconds,
                3
            )
        }
    } catch {
        $steps[$Name] = [ordered]@{
            passed = $false
            durationSeconds = [Math]::Round(
                ([DateTimeOffset]::UtcNow - $stepStarted).TotalSeconds,
                3
            )
        }
        throw
    }
}

function Write-AcceptanceEvidence {
    param([bool]$Passed)
    $payload = [ordered]@{
        schemaVersion = 1
        status = if ($Passed) {
            "WINDOWS_DOCKERLESS_CORE_ACCEPTED"
        } else {
            "WINDOWS_DOCKERLESS_CORE_REJECTED"
        }
        passed = $Passed
        host = $env:COMPUTERNAME
        startedAt = $startedAt.ToString("o")
        completedAt = [DateTimeOffset]::UtcNow.ToString("o")
        acceptanceSpec = $acceptanceSpecPath
        steps = $steps
        productionCertified = $false
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $evidenceFile) -Force |
        Out-Null
    $payload | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $evidenceFile -Encoding utf8NoBOM
}

function Require-AbsoluteEnvironmentPath {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value -or -not [IO.Path]::IsPathFullyQualified($value)) {
        throw "$Name must be configured as an absolute path."
    }
    return [IO.Path]::GetFullPath($value)
}

Push-Location $root
try {
    $docker = & where.exe docker 2>$null
    if ($LASTEXITCODE -eq 0 -or $docker) {
        throw "Docker must not be installed or available on PATH for dockerless acceptance."
    }
    $steps["docker_absent"] = @{ passed = $true; command = "where.exe docker" }
    if ([Environment]::GetEnvironmentVariable("LEAN_WINDOWS_PRODUCTION_MODE") -in
        @("1", "true", "yes", "on")) {
        throw "Golden acceptance must run before production mode is enabled."
    }

    $runtimeRoot = Require-AbsoluteEnvironmentPath "LEAN_NATIVE_RUNTIME_ROOT"
    $dataRoot = Require-AbsoluteEnvironmentPath "LEAN_DATA_DIR"
    $workRoot = Require-AbsoluteEnvironmentPath "LEAN_RUNTIME_DIR"
    $policyPath = Require-AbsoluteEnvironmentPath "LEAN_WINDOWS_SANDBOX_POLICY_FILE"
    if (-not (Test-Path -LiteralPath $acceptanceSpecPath -PathType Leaf)) {
        throw "LEAN native acceptance spec is missing: $acceptanceSpecPath"
    }

    Invoke-CheckedStep "bootstrap" {
        & $Python scripts/platformctl.py --mode native --profile core bootstrap --install-deps
        if ($LASTEXITCODE) { throw "platformctl bootstrap failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "runtime_install" {
        & $Python scripts/platformctl.py --mode native runtime install
        if ($LASTEXITCODE) { throw "native runtime install failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "sandbox_configure" {
        & (Join-Path $PSScriptRoot "configure_windows_sandbox.ps1") `
            -RunnerAccount $RunnerAccount -RuntimeRoot $runtimeRoot -DotnetPath $DotnetPath `
            -DataRoot $dataRoot -WorkRoot $workRoot -PolicyPath $policyPath
    }
    Invoke-CheckedStep "doctor" {
        & $Python scripts/platformctl.py --mode native --profile core doctor
        if ($LASTEXITCODE) { throw "platformctl doctor failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "database_init" {
        & $Python scripts/platformctl.py --mode native db init
        if ($LASTEXITCODE) { throw "database initialization failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "service_install" {
        & $Python scripts/platformctl.py --mode native install --system
        if ($LASTEXITCODE) { throw "Windows service installation failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "service_start" {
        & $Python scripts/platformctl.py --mode native --profile core start
        if ($LASTEXITCODE) { throw "Windows service startup failed: $LASTEXITCODE" }
        $script:servicesStarted = $true
        $health = $null
        $deadline = [DateTimeOffset]::UtcNow.AddMinutes(3)
        do {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 3
                if ($health) { break }
            } catch {
                Start-Sleep -Seconds 2
            }
        } while ([DateTimeOffset]::UtcNow -lt $deadline)
        if (-not $health) { throw "API health did not become ready within three minutes." }
    }
    Invoke-CheckedStep "native_lean_backtest" {
        $env:RUN_LEAN_NATIVE_INTEGRATION = "1"
        $env:LEAN_NATIVE_ACCEPTANCE_SPEC = $acceptanceSpecPath
        Push-Location (Join-Path $root "web\backend")
        try {
            & (Join-Path $root "web\backend\.venv\Scripts\python.exe") -m pytest -q `
                tests/test_ashare_native_integration.py
            if ($LASTEXITCODE) {
                throw "native LEAN acceptance backtest failed: $LASTEXITCODE"
            }
        } finally {
            Pop-Location
        }
    }
    Invoke-CheckedStep "backup_and_isolated_restore" {
        $backupRoot = Join-Path $workRoot "backups\postgres"
        $backupJson = & $Python scripts/platformctl.py --mode native backup --output $backupRoot
        if ($LASTEXITCODE) { throw "PostgreSQL backup failed: $LASTEXITCODE" }
        $backupResult = ($backupJson | Out-String) | ConvertFrom-Json
        if ($backupResult.status -ne "success") { throw "PostgreSQL backup failed." }
        $suffix = [DateTimeOffset]::UtcNow.ToString("yyyyMMddHHmmss")
        & $Python scripts/platformctl.py --mode native restore --backup $backupResult.backup `
            --target-prefix "lean_restore_golden_$suffix"
        if ($LASTEXITCODE) { throw "isolated PostgreSQL restore failed: $LASTEXITCODE" }
    }

    Write-AcceptanceEvidence -Passed $true
    Write-Host "Dockerless Golden Acceptance passed. Evidence: $evidenceFile"
} catch {
    Write-AcceptanceEvidence -Passed $false
    throw
} finally {
    if ($servicesStarted) {
        & $Python scripts/platformctl.py --mode native --profile core stop
    }
    Pop-Location
}
