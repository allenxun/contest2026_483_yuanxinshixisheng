$ErrorActionPreference = 'Stop'

$evidenceDir = 'E:\openvela\VelaVision\evidence\voice-rule-wakepartial-20260912'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $evidenceDir ("vmware-usb-isolation-$stamp.log")
$pattern = 'VID_18D1&PID_4D00|VID_0E0F&PID_0001|VID_1A86&PID_7523'

function Add-Snapshot {
    param([string]$Label)

    Add-Content -LiteralPath $logPath -Encoding utf8 -Value ("[$Label]")
    Add-Content -LiteralPath $logPath -Encoding utf8 -Value ("timestamp=" + (Get-Date -Format o))
    $devices = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.PNPDeviceID -match $pattern }
    if (-not $devices) {
        Add-Content -LiteralPath $logPath -Encoding utf8 -Value 'devices=none'
        return
    }

    foreach ($device in $devices) {
        Add-Content -LiteralPath $logPath -Encoding utf8 -Value @(
            'name=' + $device.Name
            'pnp_id=' + $device.PNPDeviceID
            'status=' + $device.Status
            'problem=' + $device.ConfigManagerErrorCode
            'service=' + $device.Service
            ''
        )
    }
}

New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
Set-Content -LiteralPath $logPath -Encoding utf8 -Value @(
    'operation=temporarily stop VMware USB arbitration, inspect exact devices, restore service'
    'flash_commands=false'
    'driver_changes=false'
)

Add-Snapshot -Label 'before-stop'
try {
    Stop-Service -Name VMUSBArbService -Force
    Start-Sleep -Seconds 3
    & pnputil.exe /scan-devices | Add-Content -LiteralPath $logPath -Encoding utf8
    Start-Sleep -Seconds 3
    Add-Snapshot -Label 'service-stopped'
}
finally {
    Start-Service -Name VMUSBArbService
    Start-Sleep -Seconds 3
    Add-Snapshot -Label 'service-restored'
}

Add-Content -LiteralPath $logPath -Encoding utf8 -Value ('service_final=' + (Get-Service VMUSBArbService).Status)
Write-Output $logPath
