[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$LeanCommit,
    [Parameter(Mandatory = $true)][string]$RuntimeId,
    [Parameter(Mandatory = $true)][string]$PythonRoot,
    [Parameter(Mandatory = $true)][string]$SigningPrivateKeyPath,
    [string]$DotnetPath = "",
    [string]$Repository = "magic-alt/platform",
    [string]$OutputDir = "$PSScriptRoot\..\..\web\runtime\release",
    [switch]$PublishDraft
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$output = [IO.Path]::GetFullPath($OutputDir)
$key = [IO.Path]::GetFullPath($SigningPrivateKeyPath)
$publicKey = Join-Path $root "config\release-signing-public.pem"
$tag = "native-$RuntimeId"

foreach ($command in @("python", "git", "openssl")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $command"
    }
}
if (-not (Test-Path -LiteralPath $key -PathType Leaf)) {
    throw "Signing private key is missing: $key"
}
if (-not (Test-Path -LiteralPath $publicKey -PathType Leaf)) {
    throw "Checked-in release public key is missing: $publicKey"
}

New-Item -ItemType Directory -Path $output -Force | Out-Null

$buildJson = & (Join-Path $PSScriptRoot "build_native_lean_runtime.ps1") `
    -LeanCommit $LeanCommit `
    -RuntimeId $RuntimeId `
    -PythonRoot $PythonRoot `
    -DotnetPath $DotnetPath `
    -OutputDir $output
if ($LASTEXITCODE) { throw "native runtime build failed: $LASTEXITCODE" }
$build = ($buildJson | Out-String) | ConvertFrom-Json

$archive = [IO.Path]::GetFullPath([string]$build.artifact)
$sbom = [IO.Path]::GetFullPath([string]$build.sbom)
$signature = "$archive.sig"
$sha = [string]$build.artifactSha256

& openssl pkeyutl -sign -rawin -inkey $key -in $archive -out $signature
if ($LASTEXITCODE) { throw "runtime signing failed: $LASTEXITCODE" }

& openssl pkeyutl -verify -rawin -pubin -inkey $publicKey -in $archive -sigfile $signature
if ($LASTEXITCODE) {
    Remove-Item -LiteralPath $signature -Force -ErrorAction SilentlyContinue
    throw "runtime signature does not verify against config/release-signing-public.pem"
}

$metadata = [ordered]@{
    schemaVersion = 1
    runtimeId = $RuntimeId
    leanCommit = $LeanCommit.ToLowerInvariant()
    platform = "windows-x64"
    artifact = $archive
    artifactSha256 = $sha
    signature = $signature
    sbom = $sbom
    releaseTag = $tag
    draftPublished = $false
    generatedAt = [DateTimeOffset]::UtcNow.ToString("o")
}

if ($PublishDraft) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI is required only when -PublishDraft is used."
    }
    & gh auth status | Out-Null
    if ($LASTEXITCODE) { throw "GitHub CLI is not authenticated." }

    $existing = & gh release view $tag --repo $Repository --json tagName 2>$null
    if ($LASTEXITCODE -eq 0 -and $existing) {
        throw "Release tag already exists: $tag"
    }

    & gh release create $tag `
        --repo $Repository `
        --draft `
        --title "Native LEAN $RuntimeId" `
        --notes "Pinned LEAN $LeanCommit Windows x64 native runtime. Promote only after local validation, Dockerless Golden Acceptance, and backend parity." `
        $archive $signature $sbom
    if ($LASTEXITCODE) { throw "draft release creation failed: $LASTEXITCODE" }

    $base = "https://github.com/$Repository/releases/download/$tag"
    $archiveName = Split-Path -Leaf $archive
    $signatureName = Split-Path -Leaf $signature
    $sbomName = Split-Path -Leaf $sbom
    $lockPath = Join-Path $output "lean-native.lock.generated.json"
    & python (Join-Path $root "scripts\render_native_runtime_lock.py") `
        --runtime-id $RuntimeId `
        --lean-commit $LeanCommit `
        --platform windows-x64 `
        --artifact-url "$base/$archiveName" `
        --artifact-sha256 $sha `
        --signature-url "$base/$signatureName" `
        --sbom-url "$base/$sbomName" `
        --output $lockPath
    if ($LASTEXITCODE) { throw "runtime lock rendering failed: $LASTEXITCODE" }

    $metadata.draftPublished = $true
    $metadata.generatedLock = $lockPath
    $metadata.releaseUrl = "https://github.com/$Repository/releases/tag/$tag"
}

$metadataPath = Join-Path $output "$RuntimeId-windows-x64.release.json"
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metadataPath -Encoding utf8NoBOM
$metadata | ConvertTo-Json -Depth 5
