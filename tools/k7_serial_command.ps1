param(
  [string]$Command = '',
  [int]$ReadMilliseconds = 1500,
  [int]$Baud = 1500000,
  [string]$Port = '',
  [switch]$KeepBuffered,
  [switch]$RequirePrompt
)

$ErrorActionPreference = 'Stop'
if ($ReadMilliseconds -lt 0 -or $ReadMilliseconds -gt 60000) {
  throw 'ReadMilliseconds must be between 0 and 60000'
}
if (-not $Port) {
  $active = [System.IO.Ports.SerialPort]::GetPortNames()
  $known = @()
  $key = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\USB\VID_1A86&PID_7523'
  if (Test-Path -LiteralPath $key) {
    $known = Get-ChildItem -LiteralPath $key | ForEach-Object {
      (Get-ItemProperty -LiteralPath ($_.PSPath + '\Device Parameters') `
        -Name PortName -ErrorAction SilentlyContinue).PortName
    }
  }
  $matches = @($active | Where-Object { $known -contains $_ } | Sort-Object -Unique)
  if ($matches.Count -ne 1) {
    throw "Expected one active QinHeng VID_1A86/PID_7523 port; found: $($matches -join ',')"
  }
  $Port = $matches[0]
}

$serial = [System.IO.Ports.SerialPort]::new(
  $Port, $Baud, [System.IO.Ports.Parity]::None, 8,
  [System.IO.Ports.StopBits]::One)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 1000
$serial.Open()
try {
  if (-not $KeepBuffered) { $serial.DiscardInBuffer() }
  $serial.Write($Command + "`r")
  $timer = [Diagnostics.Stopwatch]::StartNew()
  $text = ''
  while ($timer.ElapsedMilliseconds -lt $ReadMilliseconds) {
    $text += $serial.ReadExisting()
    if ($RequirePrompt -and $text -match 'nsh>\s*(?:\x1b\[K)?$') { break }
    Start-Sleep -Milliseconds 20
  }
  $text += $serial.ReadExisting()
  [Console]::Out.Write($text)
  [Console]::Error.WriteLine("K7_SERIAL_PORT=$Port")
  if ($RequirePrompt -and $text -notmatch 'nsh>\s*(?:\x1b\[K)?$') {
    throw 'NSH prompt not observed before deadline'
  }
}
finally {
  $serial.Close()
}
