$ErrorActionPreference = 'Stop'
$evidenceDir = 'E:\openvela\VelaVision\evidence\voice-rule-wakepartial-20260912'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $evidenceDir ("vmware-usb-proxy-restart-$stamp.log")
$instance = 'USB\Vid_0E0F&Pid_0001\5&5f5591a&0&5'

$output = & pnputil.exe /restart-device $instance 2>&1
$exitCode = $LASTEXITCODE
@(
    'timestamp=' + (Get-Date -Format o)
    'instance=' + $instance
    'exit_code=' + $exitCode
    $output
) | Set-Content -LiteralPath $logPath -Encoding utf8
if ($exitCode -ne 0) {
    exit $exitCode
}
