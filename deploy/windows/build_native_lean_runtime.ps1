[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$LeanCommit,
    [Parameter(Mandatory = $true)][string]$RuntimeId,
    [Parameter(Mandatory = $true)][string]$PythonRoot,
    [string]$OutputDir = "$PSScriptRoot\..\..\web\runtime\release",
    [string]$WorkDir = "$env:RUNNER_TEMP\lean-native-build"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$output = [IO.Path]::GetFullPath($OutputDir)
$work = [IO.Path]::GetFullPath($WorkDir)
$pythonRootResolved = [IO.Path]::GetFullPath($PythonRoot)
$source = Join-Path $work "Lean"
$stage = Join-Path $work "stage"
$archive = Join-Path $output "$RuntimeId-windows-x64.zip"
$sbom = Join-Path $output "$RuntimeId-windows-x64.cyclonedx.json"

foreach ($command in @("git", "dotnet", "python")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $command"
    }
}
if (-not (Test-Path -LiteralPath $pythonRootResolved -PathType Container)) {
    throw "PythonRoot does not exist: $pythonRootResolved"
}
$pythonDll = Join-Path $pythonRootResolved "python311.dll"
if (-not (Test-Path -LiteralPath $pythonDll -PathType Leaf)) {
    throw "Python 3.11 runtime DLL is missing: $pythonDll"
}

Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $work, $output, $stage -Force | Out-Null

Push-Location $work
try {
    git init Lean | Out-Null
    Push-Location $source
    try {
        git remote add origin https://github.com/QuantConnect/Lean.git
        git fetch --depth 1 origin $LeanCommit
        git checkout --detach FETCH_HEAD
        $actualCommit = (git rev-parse HEAD).Trim().ToLowerInvariant()
        if ($actualCommit -ne $LeanCommit.ToLowerInvariant()) {
            throw "LEAN checkout mismatch: $actualCommit"
        }
        # Upstream LEAN does not publish a repository-level packages.lock.json;
        # reproducibility is anchored to the exact Git commit plus the emitted
        # archive/SBOM digests rather than a non-existent NuGet lock file.
        dotnet restore Launcher/QuantConnect.Lean.Launcher.csproj
        if ($LASTEXITCODE) { throw "dotnet restore failed: $LASTEXITCODE" }
        dotnet build Launcher/QuantConnect.Lean.Launcher.csproj -c Release --no-restore
        if ($LASTEXITCODE) { throw "dotnet build failed: $LASTEXITCODE" }
    } finally {
        Pop-Location
    }

    $launcherSource = Join-Path $source "Launcher\bin\Release"
    $launcherTarget = Join-Path $stage "Launcher\bin\Release"
    New-Item -ItemType Directory -Path $launcherTarget -Force | Out-Null
    Copy-Item -Path (Join-Path $launcherSource "*") -Destination $launcherTarget -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $launcherTarget "QuantConnect.Lean.Launcher.dll") -PathType Leaf)) {
        throw "Built LEAN launcher was not found in Release output."
    }

    $pythonTarget = Join-Path $stage "python"
    New-Item -ItemType Directory -Path $pythonTarget -Force | Out-Null
    Copy-Item -Path (Join-Path $pythonRootResolved "*") -Destination $pythonTarget -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $pythonTarget "python311.dll") -PathType Leaf)) {
        throw "Packaged Python runtime is incomplete."
    }

    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal
    $artifactSha = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    & python (Join-Path $root "scripts\generate_native_runtime_sbom.py") `
        --runtime-root $stage `
        --runtime-id $RuntimeId `
        --lean-commit $LeanCommit `
        --artifact-sha256 $artifactSha `
        --output $sbom
    if ($LASTEXITCODE) { throw "SBOM generation failed: $LASTEXITCODE" }

    $result = [ordered]@{
        schemaVersion = 1
        runtimeId = $RuntimeId
        leanCommit = $LeanCommit.ToLowerInvariant()
        platform = "windows-x64"
        artifact = $archive
        artifactSha256 = $artifactSha
        sbom = $sbom
        launcher = "Launcher/bin/Release/QuantConnect.Lean.Launcher.dll"
        pythonHome = "python"
        pythonLibrary = "python/python311.dll"
    }
    $result | ConvertTo-Json -Depth 4
} finally {
    Pop-Location
}
