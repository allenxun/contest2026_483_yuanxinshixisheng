$ErrorActionPreference = 'Stop'
$evidenceDir = 'E:\openvela\VelaVision\evidence\voice-rule-wakepartial-20260912'
$logPath = Join-Path $evidenceDir 'vmware-usb-admin-restart-20260913.log'

$before = Get-Service -Name VMUSBArbService
Restart-Service -Name VMUSBArbService -Force
$after = Get-Service -Name VMUSBArbService

@(
    'timestamp=' + (Get-Date -Format o)
    'before=' + $before.Status
    'after=' + $after.Status
) | Set-Content -LiteralPath $logPath -Encoding utf8
