[CmdletBinding()]
param(
    [string]$AcceptanceSpec = "$PSScriptRoot\..\..\config\acceptance\windows-native-core.v1.json",
    [Parameter(Mandatory = $true)][string]$RunnerAccount,
    [string]$DotnetPath = "",
    [string]$Python = "python",
    [string]$EvidencePath = "C:\ProgramData\LeanPlatform\evidence\dockerless-golden.json"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$acceptanceSpecPath = [IO.Path]::GetFullPath($AcceptanceSpec)
$evidenceFile = [IO.Path]::GetFullPath($EvidencePath)
$startedAt = [DateTimeOffset]::UtcNow
$steps = [ordered]@{}
$preflight = [ordered]@{}
$productionOpsWarnings = @(
    [ordered]@{
        code = "rabbitmq_cli_cookie_not_core_gated"
        severity = "production-ops-warning"
        message = "RabbitMQ management CLI authentication is required for fault certification, not Core Golden."
    }
)
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
        preflight = $preflight
        dockerCleanHost = $preflight.dockerCleanHost
        productionOpsWarnings = $productionOpsWarnings
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

function Test-TcpPort {
    param([string]$HostName, [int]$Port)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.ConnectAsync($HostName, $Port)
        return $pending.Wait(2000) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-LocalAccount {
    param([string]$Account)
    try {
        $identity = [Security.Principal.NTAccount]::new($Account)
        $null = $identity.Translate([Security.Principal.SecurityIdentifier])
        return $true
    } catch {
        return $false
    }
}

function Get-DockerCleanHostStatus {
    $programRoots = @(
        [Environment]::GetEnvironmentVariable("ProgramFiles"),
        [Environment]::GetEnvironmentVariable("ProgramW6432"),
        [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    ) | Where-Object { $_ } | Select-Object -Unique
    $dockerDirectories = @($programRoots | ForEach-Object { Join-Path $_ "Docker" })
    $desktopExecutables = @(
        $dockerDirectories | ForEach-Object {
            Join-Path $_ "Docker\Docker Desktop.exe"
            Join-Path $_ "Docker Desktop.exe"
        }
    )
    $registryRoots = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $dockerRegistration = @(
        foreach ($registryRoot in $registryRoots) {
            Get-ItemProperty -Path $registryRoot -ErrorAction SilentlyContinue |
                Where-Object { [string]$_.DisplayName -like "Docker Desktop*" }
        }
    )
    $wslAbsent = $true
    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        $wslOutput = & wsl.exe -l -q 2>$null
        if ($LASTEXITCODE) {
            $wslAbsent = $false
        } else {
            $wslAbsent = -not @(
                $wslOutput | ForEach-Object { ([string]$_).Replace([char]0, "").Trim() } |
                    Where-Object { $_ -like "docker-desktop*" }
            )
        }
    }
    return [ordered]@{
        cliAbsent = -not (Get-Command docker.exe -ErrorAction SilentlyContinue)
        serviceAbsent = -not (Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue)
        desktopAbsent = -not @($desktopExecutables | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        })
        wslDistrosAbsent = $wslAbsent
        installationAbsent = (
            -not @($dockerDirectories | Where-Object { Test-Path -LiteralPath $_ }) -and
            -not $dockerRegistration
        )
    }
}

function Resolve-GoldenDotnet {
    $resolverArgs = @(
        (Join-Path $root "scripts\resolve_dotnet.py"),
        "--require",
        "runtime"
    )
    if ($DotnetPath) { $resolverArgs += @("--path", $DotnetPath) }
    $output = & $Python @resolverArgs
    if ($LASTEXITCODE) { return $null }
    return [IO.Path]::GetFullPath([string]($output | Select-Object -Last 1))
}

Push-Location $root
try {
    $dockerCleanHost = Get-DockerCleanHostStatus
    $dockerClean = -not ($dockerCleanHost.Values -contains $false)
    $dotnet = Resolve-GoldenDotnet
    $dotnetExists = [bool]$dotnet -and (
        Test-Path -LiteralPath $dotnet -PathType Leaf
    )
    $runtime10 = $dotnetExists

    $requiredEnvironmentPaths = @(
        "LEAN_NATIVE_RUNTIME_ROOT",
        "LEAN_DATA_DIR",
        "LEAN_RUNTIME_DIR",
        "LEAN_WINDOWS_SANDBOX_POLICY_FILE"
    )
    $environmentPathsReady = $true
    foreach ($name in $requiredEnvironmentPaths) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not $value -or -not [IO.Path]::IsPathFullyQualified($value)) {
            $environmentPathsReady = $false
        }
    }

    $specReady = $false
    $specSha256 = ""
    $algorithmSha256 = ""
    if (Test-Path -LiteralPath $acceptanceSpecPath -PathType Leaf) {
        try {
            $specPayload = Get-Content -LiteralPath $acceptanceSpecPath -Raw |
                ConvertFrom-Json
            $projectDir = [string]$specPayload.projectDir
            $projectPath = if ([IO.Path]::IsPathFullyQualified($projectDir)) {
                [IO.Path]::GetFullPath($projectDir)
            } else {
                [IO.Path]::GetFullPath(
                    (Join-Path (Split-Path -Parent $acceptanceSpecPath) $projectDir)
                )
            }
            $algorithmPath = Join-Path $projectPath ([string]$specPayload.mainFile)
            $specSha256 = (
                Get-FileHash -LiteralPath $acceptanceSpecPath -Algorithm SHA256
            ).Hash.ToLowerInvariant()
            $algorithmSha256 = (
                Get-FileHash -LiteralPath $algorithmPath -Algorithm SHA256
            ).Hash.ToLowerInvariant()
            $specReady = (
                $specPayload.schemaVersion -eq 1 -and
                $specPayload.qualificationId -eq "windows-native-core-v1" -and
                $specPayload.runId -and
                $specPayload.algorithmClass -and
                $specPayload.parameters -and
                $specPayload.parameters.ticker -eq $specPayload.fixture.symbol -and
                $specPayload.parameters.market -eq $specPayload.fixture.market -and
                $specPayload.fixture.rows.Count -ge 2 -and
                $specPayload.expected.minimumOrders -ge 1 -and
                (Test-Path -LiteralPath $algorithmPath -PathType Leaf)
            )
        } catch {
            $specReady = $false
        }
    }

    $runtimeLockReady = $false
    $runtimeLockPath = Join-Path $root "config\runtime\lean-native.lock.json"
    try {
        $runtimeLock = Get-Content -LiteralPath $runtimeLockPath -Raw |
            ConvertFrom-Json
        $windowsArtifact = $runtimeLock.artifacts.'windows-x64'
        $runtimeLockReady = (
            $runtimeLock.supported -eq $true -and
            $runtimeLock.runtimeId -and
            $runtimeLock.leanCommit -match '^[0-9a-f]{40}$' -and
            $runtimeLock.leanCommit -ne ("0" * 40) -and
            $windowsArtifact.url -and
            $windowsArtifact.sha256 -match '^[0-9a-f]{64}$' -and
            $windowsArtifact.signatureUrl -and
            $windowsArtifact.sbomUrl
        )
    } catch {
        $runtimeLockReady = $false
    }

    $productionModeDisabled = (
        [Environment]::GetEnvironmentVariable("LEAN_WINDOWS_PRODUCTION_MODE") -notin
            @("1", "true", "yes", "on")
    )
    $runnerServiceAccount = [Environment]::GetEnvironmentVariable(
        "LEAN_WINDOWS_RUNNER_ACCOUNT"
    )
    $platformServiceAccount = [Environment]::GetEnvironmentVariable(
        "LEAN_WINDOWS_PLATFORM_ACCOUNT"
    )
    $serviceAccountsReady = (
        $runnerServiceAccount -eq $RunnerAccount -and
        (Test-LocalAccount $runnerServiceAccount) -and
        (Test-LocalAccount $platformServiceAccount)
    )
    # Presence is checked without retrieving either credential value.
    $serviceCredentialVariablesPresent = (
        (Test-Path Env:LEAN_WINDOWS_RUNNER_PASSWORD) -and
        (Test-Path Env:LEAN_WINDOWS_PLATFORM_PASSWORD)
    )
    $preflight = [ordered]@{
        passed = $false
        dockerCleanHost = $dockerCleanHost
        dotnetPathResolved = $dotnetExists
        dotnetRuntime10Available = $runtime10
        environmentPathsReady = $environmentPathsReady
        signedRuntimeLockReady = $runtimeLockReady
        acceptanceSpecReady = $specReady
        acceptanceSpecSha256 = $specSha256
        acceptanceAlgorithmSha256 = $algorithmSha256
        serviceAccountsReady = $serviceAccountsReady
        serviceCredentialVariablesPresent = $serviceCredentialVariablesPresent
        postgresqlReady = Test-TcpPort "127.0.0.1" (
            [int]([Environment]::GetEnvironmentVariable("LEAN_POSTGRES_PORT") ?? "5432")
        )
        rabbitmqAmqpReady = Test-TcpPort "127.0.0.1" (
            [int]([Environment]::GetEnvironmentVariable("LEAN_RABBITMQ_PORT") ?? "5672")
        )
        productionModeDisabled = $productionModeDisabled
    }
    $preflight.passed = (
        $dockerClean -and
        $preflight.dotnetPathResolved -and
        $preflight.dotnetRuntime10Available -and
        $preflight.environmentPathsReady -and
        $preflight.signedRuntimeLockReady -and
        $preflight.acceptanceSpecReady -and
        $preflight.serviceAccountsReady -and
        $preflight.serviceCredentialVariablesPresent -and
        $preflight.postgresqlReady -and
        $preflight.rabbitmqAmqpReady -and
        $preflight.productionModeDisabled
    )
    $steps["preflight"] = $preflight
    Write-Host ($preflight | ConvertTo-Json -Depth 6)
    if (-not $preflight.passed) {
        throw "Windows Dockerless Golden preflight failed before system mutation."
    }

    $env:LEAN_DOTNET_PATH = $dotnet
    $runtimeRoot = Require-AbsoluteEnvironmentPath "LEAN_NATIVE_RUNTIME_ROOT"
    $dataRoot = Require-AbsoluteEnvironmentPath "LEAN_DATA_DIR"
    $workRoot = Require-AbsoluteEnvironmentPath "LEAN_RUNTIME_DIR"
    $policyPath = Require-AbsoluteEnvironmentPath "LEAN_WINDOWS_SANDBOX_POLICY_FILE"

    Invoke-CheckedStep "bootstrap" {
        & $Python scripts/platformctl.py --mode native --profile core bootstrap --install-deps
        if ($LASTEXITCODE) { throw "platformctl bootstrap failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "acceptance_fixture_prepare" {
        & (Join-Path $root "web\backend\.venv\Scripts\python.exe") scripts/prepare_windows_native_acceptance.py --spec $acceptanceSpecPath
        if ($LASTEXITCODE) { throw "acceptance fixture preparation failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "runtime_install" {
        & $Python scripts/platformctl.py --mode native runtime install
        if ($LASTEXITCODE) { throw "native runtime install failed: $LASTEXITCODE" }
    }
    Invoke-CheckedStep "sandbox_configure" {
        & (Join-Path $PSScriptRoot "configure_windows_sandbox.ps1") `
            -RunnerAccount $RunnerAccount -RuntimeRoot $runtimeRoot -DotnetPath $dotnet `
            -DataRoot $dataRoot -WorkRoot $workRoot -PolicyPath $policyPath -Python $Python
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
