[CmdletBinding()]
param(
    [ValidateSet('bootstrap', 'install', 'uninstall')][string]$Mode = 'install',
    [string]$Distribution = 'Ubuntu',
    [string]$TargetHost,
    [string]$User,
    [ValidateRange(1, 65535)][int]$Port = 22,
    [string]$Identity,
    [string]$Namespace = 'awx',
    [ValidateRange(30000, 32767)][int]$NodePort = 30080,
    [string]$PublicUrl,
    [switch]$AskBecomePass,
    [string]$ConfirmDelete
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($Distribution.StartsWith('-') -or $Distribution -match '[\x00-\x1f]') {
    throw 'Invalid WSL distribution name'
}
$converted = & wsl.exe --distribution $Distribution --exec wslpath -a -u $root
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$wslRoot = ($converted -join "`n").Trim()
if (-not $wslRoot.StartsWith('/') -or $wslRoot.Contains("`n")) { throw 'Invalid WSL project path' }
$python = if ($Mode -eq 'bootstrap') { 'python3' } else { "$wslRoot/.venv/bin/python" }
$arguments = @('--distribution', $Distribution, '--cd', $wslRoot, '--exec', $python,
    "$wslRoot/scripts/controller.py", $Mode, '--port', "$Port", '--namespace', $Namespace,
    '--nodeport', "$NodePort")
foreach ($pair in @(@('--host', $TargetHost), @('--user', $User), @('--identity', $Identity),
    @('--public-url', $PublicUrl), @('--confirm-delete', $ConfirmDelete))) {
    if ($pair[1]) { $arguments += "$($pair[0])=$($pair[1])" }
}
if ($AskBecomePass) { $arguments += '--ask-become-pass' }
& wsl.exe @arguments
exit $LASTEXITCODE
