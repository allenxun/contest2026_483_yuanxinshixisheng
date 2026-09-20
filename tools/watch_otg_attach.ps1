param(
    [int]$TimeoutSeconds = 14400,
    [string]$LogPath = 'E:\openvela\VelaVision\evidence\voice-radio-refresh-20260914\otg-auto-attach.log'
)

$ErrorActionPreference = 'Continue'
$vmrun = 'D:\software\VM\vmrun.exe'
$vmx = 'D:\VMware\Ubuntu 64 位\Ubuntu 64 位.vmx'
$key = 'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519'
$knownHosts = 'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\known_hosts'
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
"started_at=$((Get-Date).ToString('o')) timeout_seconds=$TimeoutSeconds" |
    Set-Content -LiteralPath $LogPath -Encoding utf8

while ((Get-Date) -lt $deadline) {
    $guestUsb = & ssh.exe -i $key -o "UserKnownHostsFile=$knownHosts" `
        -o StrictHostKeyChecking=yes -o ConnectTimeout=3 swl@192.168.152.131 `
        'lsusb -d 18d1:4d00 2>/dev/null' 2>$null
    if ($LASTEXITCODE -eq 0 -and $guestUsb) {
        "attached_at=$((Get-Date).ToString('o')) guest=$guestUsb" |
            Add-Content -LiteralPath $LogPath -Encoding utf8
        exit 0
    }

    $device = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object {
            $_.InstanceId -like 'USB\VID_18D1&PID_4D00*' -or
            $_.FriendlyName -eq 'USB download gadget'
        } | Select-Object -First 1
    if ($device) {
        "seen_at=$((Get-Date).ToString('o')) status=$($device.Status) instance=$($device.InstanceId)" |
            Add-Content -LiteralPath $LogPath -Encoding utf8
        if ($device.Status -eq 'OK') {
            & $vmrun -T ws connectNamedDevice $vmx 'Google USB download gadget' 2>&1 |
                Add-Content -LiteralPath $LogPath -Encoding utf8
        }
    }
    Start-Sleep -Seconds 2
}

"timeout_at=$((Get-Date).ToString('o'))" |
    Add-Content -LiteralPath $LogPath -Encoding utf8
exit 2
