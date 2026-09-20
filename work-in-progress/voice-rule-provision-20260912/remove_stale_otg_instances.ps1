$ErrorActionPreference = 'Stop'
$evidenceDir = 'E:\openvela\VelaVision\evidence\voice-rule-wakepartial-20260912'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $evidenceDir ("remove-stale-otg-$stamp.log")
$instances = @(
    'USB\VID_18D1&PID_4D00\F71A9D152132DB55',
    'USB\VID_0E0F&PID_0001\5&5F5591A&0&5'
)

$records = @('timestamp=' + (Get-Date -Format o))
foreach ($instance in $instances) {
    $output = & pnputil.exe /remove-device $instance 2>&1
    $exitCode = $LASTEXITCODE
    $records += 'instance=' + $instance
    $records += 'exit_code=' + $exitCode
    $records += $output
    if ($exitCode -ne 0) {
        $records | Set-Content -LiteralPath $logPath -Encoding utf8
        exit $exitCode
    }
}
$records | Set-Content -LiteralPath $logPath -Encoding utf8
