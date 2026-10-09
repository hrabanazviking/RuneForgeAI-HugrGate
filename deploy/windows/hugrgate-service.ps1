<#
.SYNOPSIS
    Install HugrGate as a Windows service via NSSM.
    Gjallarbrú slice 448.

.DESCRIPTION
    Uses NSSM (the Non-Sucking Service Manager) to run
    `hugrgate serve` as a Windows service with automatic restart
    and log rotation. Run from an elevated PowerShell:

        .\deploy\windows\hugrgate-service.ps1 -Install

    Requires: Python 3.10+, `pip install "hugrgate[server]"`,
    and nssm.exe on PATH (https://nssm.cc/download).

.PARAMETER Install
    Install (or re-install) the service.

.PARAMETER Uninstall
    Stop and remove the service.

.PARAMETER ConfigPath
    Daemon config file. Defaults to hugrgate.yaml next to this script.
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [string]$ConfigPath = (Join-Path $PSScriptRoot "hugrgate.yaml")
)

$ErrorActionPreference = "Stop"
$ServiceName = "HugrGate"
$AppDir = "C:\Program Files\HugrGate"

function Assert-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated PowerShell."
    }
}

function Assert-Nssm {
    if (-not (Get-Command nssm.exe -ErrorAction SilentlyContinue)) {
        throw "nssm.exe not found on PATH. Install from https://nssm.cc/download"
    }
}

function Get-HugrGateExe {
    $exe = Join-Path $AppDir "Scripts\hugrgate.exe"
    if (-not (Test-Path $exe)) {
        # fall back to whatever `hugrgate` resolves to on PATH
        $cmd = Get-Command hugrgate.exe -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        throw "hugrgate.exe not found. Run: pip install `"hugrgate[server]`""
    }
    return $exe
}

if ($Install -and $Uninstall) { throw "Pass -Install or -Uninstall, not both." }

if ($Uninstall) {
    Assert-Elevated
    Assert-Nssm
    nssm stop $ServiceName
    nssm remove $ServiceName confirm
    Write-Host "Service '$ServiceName' removed."
    exit 0
}

if ($Install) {
    Assert-Elevated
    Assert-Nssm
    if (-not (Test-Path $ConfigPath)) {
        throw "Config file not found: $ConfigPath"
    }
    $exe = Get-HugrGateExe

    # Re-install cleanly if a previous registration exists.
    nssm stop $ServiceName 2>$null
    nssm remove $ServiceName confirm 2>$null

    nssm install $ServiceName $exe
    nssm set $ServiceName AppDirectory $AppDir
    nssm set $ServiceName AppParameters "serve --config `"$ConfigPath`""
    nssm set $ServiceName DisplayName "HugrGate Decision Service"
    nssm set $ServiceName Description "HugrGate probabilistic decision service"
    nssm set $ServiceName Start SERVICE_AUTO_START
    nssm set $ServiceName AppStdout (Join-Path $AppDir "logs\service.log")
    nssm set $ServiceName AppStderr (Join-Path $AppDir "logs\service-error.log")
    nssm set $ServiceName AppRotateFiles 1
    nssm set $ServiceName AppRotateBytes 10485760

    # Health-based recovery: restart on failure, with backoff.
    nssm set $ServiceName AppThrottle 5000
    nssm set $ServiceName AppExit Default Restart
    nssm set $ServiceName AppRestartDelay 5000

    nssm start $ServiceName
    Write-Host "Service '$ServiceName' installed and started."
    Write-Host "Health: http://127.0.0.1:8377/health"
    exit 0
}

throw "Pass -Install or -Uninstall. See .SYNOPSIS."
