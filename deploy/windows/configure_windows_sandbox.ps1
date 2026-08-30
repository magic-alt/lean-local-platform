[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$RunnerAccount,
    [string]$ProgramDataRoot = "C:\ProgramData\LeanPlatform",
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [string]$DotnetPath = "",
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [string]$WorkRoot = "",
    [string]$PolicyPath = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$resolvedProgramData = [IO.Path]::GetFullPath($ProgramDataRoot)
$resolvedRuntime = [IO.Path]::GetFullPath($RuntimeRoot)
$dotnetResolverArgs = @(
    (Join-Path $root "scripts\resolve_dotnet.py"),
    "--require",
    "runtime"
)
if ($DotnetPath) { $dotnetResolverArgs += @("--path", $DotnetPath) }
$dotnetOutput = & $Python @dotnetResolverArgs
if ($LASTEXITCODE) {
    throw ".NET runtime 10.x is required on the deployment host."
}
$resolvedDotnet = [IO.Path]::GetFullPath(
    [string]($dotnetOutput | Select-Object -Last 1)
)
$resolvedData = [IO.Path]::GetFullPath($DataRoot)
$resolvedWork = if ($WorkRoot) {
    [IO.Path]::GetFullPath($WorkRoot)
} else {
    Join-Path $resolvedProgramData "runtime"
}
$resolvedPolicy = if ($PolicyPath) {
    [IO.Path]::GetFullPath($PolicyPath)
} else {
    Join-Path $resolvedProgramData "sandbox-policy.json"
}
if (-not $resolvedProgramData.StartsWith("C:\ProgramData\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "ProgramDataRoot must be below C:\ProgramData."
}
if (-not $resolvedPolicy.StartsWith(($resolvedProgramData.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "PolicyPath must be below ProgramDataRoot."
}
$runtimeWork = $resolvedWork
$results = Join-Path $runtimeWork "runs"
$research = Join-Path $runtimeWork "research"
foreach ($path in @($resolvedProgramData, $resolvedRuntime, $resolvedData, $runtimeWork, $results, $research, (Split-Path -Parent $resolvedPolicy))) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

if ($PSCmdlet.ShouldProcess($RunnerAccount, "Apply restricted runner ACLs")) {
    & icacls.exe $resolvedRuntime /inheritance:r /grant:r "${RunnerAccount}:(OI)(CI)(RX)" | Out-Null
    & icacls.exe $resolvedData /inheritance:r /grant:r "${RunnerAccount}:(OI)(CI)(RX)" | Out-Null
    & icacls.exe $runtimeWork /inheritance:r /grant:r "${RunnerAccount}:(OI)(CI)(M)" | Out-Null
}

$firewallRule = "LeanPlatform-RestrictedRunner-BlockOutbound"
if ($PSCmdlet.ShouldProcess($resolvedDotnet, "Block outbound network access")) {
    Get-NetFirewallRule -DisplayName $firewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $firewallRule -Direction Outbound -Action Block `
        -Program $resolvedDotnet -Profile Any -Enabled True | Out-Null
}

$policy = [ordered]@{
    schemaVersion = 1
    runnerAccount = $RunnerAccount
    firewallRule = $firewallRule
    dotnetPath = $resolvedDotnet
    dataRoot = $resolvedData
    runtimeRoot = $resolvedRuntime
    workRoot = $runtimeWork
}
$policy | ConvertTo-Json | Set-Content -LiteralPath $resolvedPolicy -Encoding utf8NoBOM
Write-Host "Sandbox policy written to $resolvedPolicy"
Write-Host "Set LEAN_WINDOWS_SANDBOX_POLICY_FILE=$resolvedPolicy"
Write-Host "Set LEAN_RUNTIME_DIR=$runtimeWork"
