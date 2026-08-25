[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$InstallDependencies,
    [string]$EvidencePath = "C:\ProgramData\LeanPlatform\evidence\windows-native-local-validation.json"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backend = Join-Path $root "web\backend"
$evidenceFile = [IO.Path]::GetFullPath($EvidencePath)
$startedAt = [DateTimeOffset]::UtcNow
$steps = [ordered]@{}

if (-not $Python) {
    $venvPython = Join-Path $backend ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $Python = $venvPython
    } else {
        $Python = (Get-Command python -ErrorAction Stop).Source
    }
}
$Python = [IO.Path]::GetFullPath($Python)

function Invoke-ValidationStep {
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
            error = $_.Exception.Message
        }
        throw
    }
}

function Write-ValidationEvidence {
    param([bool]$Passed)
    $commit = "unknown"
    try { $commit = (& git -C $root rev-parse HEAD).Trim() } catch {}
    $payload = [ordered]@{
        schemaVersion = 1
        status = if ($Passed) { "WINDOWS_NATIVE_LOCAL_VALIDATION_PASSED" } else { "WINDOWS_NATIVE_LOCAL_VALIDATION_FAILED" }
        passed = $Passed
        host = $env:COMPUTERNAME
        commit = $commit
        python = $Python
        startedAt = $startedAt.ToString("o")
        completedAt = [DateTimeOffset]::UtcNow.ToString("o")
        steps = $steps
        githubActionsRequired = $false
        productionCertified = $false
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $evidenceFile) -Force | Out-Null
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidenceFile -Encoding utf8NoBOM
}

Push-Location $root
try {
    Invoke-ValidationStep "python_version" {
        & $Python --version
        if ($LASTEXITCODE) { throw "python version check failed: $LASTEXITCODE" }
    }

    if ($InstallDependencies) {
        Invoke-ValidationStep "install_locked_dependencies" {
            & $Python -m pip install --require-hashes -r (Join-Path $backend "requirements.lock")
            if ($LASTEXITCODE) { throw "locked dependency install failed: $LASTEXITCODE" }
        }
    }

    Invoke-ValidationStep "pip_check" {
        & $Python -m pip check
        if ($LASTEXITCODE) { throw "pip check failed: $LASTEXITCODE" }
    }

    Invoke-ValidationStep "platformctl_contract" {
        & $Python scripts/platformctl.py --help | Out-Null
        if ($LASTEXITCODE) { throw "platformctl --help failed: $LASTEXITCODE" }
    }

    Invoke-ValidationStep "powershell_syntax" {
        $errors = @()
        foreach ($path in @(
            "deploy/windows/configure_windows_sandbox.ps1",
            "deploy/windows/build_native_lean_runtime.ps1",
            "deploy/windows/run_local_native_runtime_release.ps1",
            "deploy/windows/run_local_native_validation.ps1",
            "deploy/windows/run_dockerless_golden_acceptance.ps1"
        )) {
            [System.Management.Automation.Language.Parser]::ParseFile(
                (Resolve-Path $path), [ref]$null, [ref]$errors
            ) | Out-Null
        }
        if ($errors.Count) {
            throw (($errors | ForEach-Object { $_.Message }) -join "; ")
        }
    }

    Invoke-ValidationStep "json_contracts" {
        foreach ($path in @(
            "config/runtime/lean-native.lock.json",
            "config/runtime/windows-celery-certification.json"
        )) {
            Get-Content -LiteralPath $path -Raw | ConvertFrom-Json | Out-Null
        }
    }

    Invoke-ValidationStep "compileall" {
        & $Python -m compileall -q scripts web/backend/app
        if ($LASTEXITCODE) { throw "compileall failed: $LASTEXITCODE" }
    }

    Invoke-ValidationStep "windows_native_contract_tests" {
        Push-Location $backend
        try {
            & $Python -m pytest -q `
                tests/test_native_execution.py `
                tests/test_platformctl.py `
                tests/test_restricted_runner.py `
                tests/test_windows_native_contract.py `
                tests/test_windows_certification.py
            if ($LASTEXITCODE) { throw "Windows Native contract tests failed: $LASTEXITCODE" }
        } finally {
            Pop-Location
        }
    }

    Invoke-ValidationStep "repository_hygiene" {
        & $Python scripts/check_repository_hygiene.py
        if ($LASTEXITCODE) { throw "repository hygiene failed: $LASTEXITCODE" }
        & git diff --check main...HEAD
        if ($LASTEXITCODE) { throw "git diff --check failed: $LASTEXITCODE" }
    }

    Write-ValidationEvidence -Passed $true
    Write-Host "Windows Native local validation passed. Evidence: $evidenceFile"
} catch {
    Write-ValidationEvidence -Passed $false
    throw
} finally {
    Pop-Location
}
