[CmdletBinding()]
param(
    [string]$GuestHost = '192.168.152.131',
    [string]$GuestUser = 'swl',
    [string]$IdentityFile = 'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519',
    [string]$KnownHostsFile = 'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\known_hosts',
    [switch]$SkipGuest,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

function Invoke-CapturedNative {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )

    try {
        $lines = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        return [ordered]@{
            available = $true
            exit_code = $exitCode
            output = (($lines | ForEach-Object { $_.ToString() }) -join "`n").Trim()
        }
    }
    catch {
        return [ordered]@{
            available = $false
            exit_code = $null
            output = $_.Exception.Message
        }
    }
}

function Find-Vmrun {
    $known = @(
        'D:\software\VM\vmrun.exe',
        'C:\Program Files\VMware\VMware Workstation\vmrun.exe',
        'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
    )

    foreach ($candidate in $known) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

$service = $null
try {
    $s = Get-Service -Name VMUSBArbService
    $service = [ordered]@{
        found = $true
        status = $s.Status.ToString()
        start_type = $s.StartType.ToString()
    }
}
catch {
    $service = [ordered]@{
        found = $false
        error = $_.Exception.Message
    }
}

$processes = @()
foreach ($name in @('vmware', 'vmware-vmx', 'vmware-usbarbitrator64')) {
    foreach ($p in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        $processes += [ordered]@{
            name = $p.ProcessName
            pid = $p.Id
            start_time = if ($p.StartTime) { $p.StartTime.ToString('o') } else { $null }
            path_visible = [bool]$p.Path
        }
    }
}

$connectedUsb = Invoke-CapturedNative -FilePath 'pnputil.exe' -Arguments @('/enum-devices', '/connected', '/class', 'USB')
$connectedPorts = Invoke-CapturedNative -FilePath 'pnputil.exe' -Arguments @('/enum-devices', '/connected', '/class', 'Ports')
$problem43 = Invoke-CapturedNative -FilePath 'pnputil.exe' -Arguments @('/enum-devices', '/problem', '43')

$vmrunPath = Find-Vmrun
$vmrunList = if ($vmrunPath) {
    Invoke-CapturedNative -FilePath $vmrunPath -Arguments @('-T', 'ws', 'list')
}
else {
    [ordered]@{ available = $false; exit_code = $null; output = 'vmrun.exe not found' }
}

$guest = [ordered]@{
    attempted = $false
    available = $false
    exit_code = $null
    output = ''
}

if (-not $SkipGuest) {
    $guest.attempted = $true
    if ((Test-Path -LiteralPath $IdentityFile -PathType Leaf) -and
        (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf)) {
        $remote = @'
printf 'hostname='; hostname
printf 'vmtools='; vmware-toolbox-cmd -v 2>/dev/null || true
printf 'usb_begin\n'; lsusb 2>&1; printf 'usb_end\n'
printf 'tty_begin\n'; ls -l /dev/ttyUSB* 2>&1 || true; printf 'tty_end\n'
printf 'holders_begin\n'; fuser -v /dev/ttyUSB0 2>&1 || true; printf 'holders_end\n'
printf 'udev_begin\n'; udevadm info --query=property --name=/dev/ttyUSB0 2>&1 | sed -n '1,35p' || true; printf 'udev_end\n'
printf 'sysfs_begin\n'
tty_sys=$(readlink -f /sys/class/tty/ttyUSB0/device 2>/dev/null || true)
usb_sys=$(dirname "$(dirname "$tty_sys")")
for name in authorized idVendor idProduct power/control power/runtime_status; do printf '%s=' "$name"; cat "$usb_sys/$name" 2>&1 || true; done
printf 'sysfs_end\n'
printf 'kernel_begin\n'; journalctl -k -n 160 --no-pager 2>&1 | grep -Ei 'usb|ch34|ttyUSB|18d1|4d00' | tail -80 || true; printf 'kernel_end\n'
'@
        $ssh = Invoke-CapturedNative -FilePath 'ssh.exe' -Arguments @(
            '-i', $IdentityFile,
            '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=6',
            '-o', 'StrictHostKeyChecking=yes',
            '-o', ('UserKnownHostsFile=' + $KnownHostsFile),
            ($GuestUser + '@' + $GuestHost),
            $remote
        )
        $guest.available = $ssh.available -and ($ssh.exit_code -eq 0)
        $guest.exit_code = $ssh.exit_code
        $guest.output = $ssh.output
    }
    else {
        $guest.output = 'SSH identity or pinned known_hosts file is unavailable to this token'
    }
}

$hostUsbText = $connectedUsb.output + "`n" + $connectedPorts.output
$guestText = $guest.output
$signals = [ordered]@{
    vmware_service_running = ($service.found -and $service.status -eq 'Running')
    vmware_proxy_connected = ($hostUsbText -match '(?i)VID_0E0F&PID_0001')
    host_ch340_connected = ($connectedPorts.output -match '(?i)VID_1A86&PID_7523')
    host_fastboot_connected = ($connectedUsb.output -match '(?i)VID_18D1&PID_4D00')
    host_problem_43_present = ($problem43.exit_code -eq 0) -and -not ($problem43.output -match '(?i)No devices were found|未找到任何设备|没有找到任何设备')
    guest_ch340_present = ($guestText -match '(?i)1a86:7523') -and ($guestText -match '/dev/ttyUSB0')
    guest_fastboot_present = ($guestText -match '(?i)18d1:4d00')
    guest_usb_timeout_seen = ($guestText -match '(?i)control message: -110|modem status: -110')
}

$classification = 'inspect_current_ownership'
$nextAction = 'Compare the host and guest inventories; do not mutate USB state from this inspector.'
if ($signals.host_problem_43_present) {
    $classification = 'host_usb_problem_requires_manual_reenumeration'
    $nextAction = 'A host-side USB problem exists. Use the recorded physical or administrator-assisted recovery path, then rerun this inspector.'
}
elseif ($signals.guest_ch340_present -and $signals.guest_usb_timeout_seen) {
    $classification = 'ch340_transport_timeout_beyond_udev'
    $nextAction = 'The guest owns CH340 but kernel control transfers time out. Reconnect the exact CH340 device through VMware or physically re-enumerate it; udev and permissions are already past this layer.'
}
elseif ($signals.guest_ch340_present -and -not $signals.guest_fastboot_present) {
    $classification = 'ch340_ready_fastboot_gadget_absent'
    $nextAction = 'Serial is enumerated in the guest. The board must be placed at the U-Boot prompt and expose the USB download gadget before VMware can attach it.'
}
elseif ($signals.host_fastboot_connected -and -not $signals.guest_fastboot_present) {
    $classification = 'manual_vmware_fastboot_attach_required'
    $nextAction = 'Windows sees the gadget while the guest does not. Attach that exact removable USB device after Ubuntu has fully booted.'
}
elseif ($signals.guest_ch340_present -and $signals.guest_fastboot_present) {
    $classification = 'both_devices_visible_in_guest'
    $nextAction = 'Both endpoints are visible. Use the separate audited transfer workflow; this inspector intentionally performs no serial or Fastboot I/O.'
}

$report = [ordered]@{
    schema = 'velavision.vmware-usb-readonly-diagnostic.v1'
    timestamp = (Get-Date).ToString('o')
    constraints = [ordered]@{
        device_io = $false
        service_changes = $false
        process_changes = $false
        driver_changes = $false
        vmx_changes = $false
        host_or_guest_reboot = $false
    }
    host = [ordered]@{
        vmware_service = $service
        vmware_processes = $processes
        vmrun_path = $vmrunPath
        vmrun_list = $vmrunList
        connected_usb = $connectedUsb
        connected_ports = $connectedPorts
        problem_43 = $problem43
    }
    guest = $guest
    signals = $signals
    classification = $classification
    next_action = $nextAction
}

$json = $report | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $fullOutput = [System.IO.Path]::GetFullPath($OutputPath)
    if (Test-Path -LiteralPath $fullOutput) {
        throw "Refusing to overwrite existing report: $fullOutput"
    }
    [System.IO.File]::WriteAllText($fullOutput, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}
$json
