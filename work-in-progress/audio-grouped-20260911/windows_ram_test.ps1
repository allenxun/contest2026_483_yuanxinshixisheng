param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Enter','Final','Probe')]
  [string]$Mode,
  [string]$Port = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $root ($Mode.ToLowerInvariant() + '-' + $stamp + '.log')
$script:log = [Text.StringBuilder]::new()

function Resolve-K7Port {
  param([string]$Requested)
  if ($Requested) { return $Requested }
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
    throw "Expected one active QinHeng serial port; found: $($matches -join ',')"
  }
  return $matches[0]
}

function Append-Output {
  param([string]$Text)
  if ($Text) {
    [void]$script:log.Append($Text)
    [Console]::Out.Write($Text)
  }
}

function Read-Until {
  param($Serial, [int]$Milliseconds, [string]$Pattern = '')
  $timer = [Diagnostics.Stopwatch]::StartNew()
  $text = ''
  while ($timer.ElapsedMilliseconds -lt $Milliseconds) {
    $text += $Serial.ReadExisting()
    if ($Pattern -and $text -match $Pattern) { break }
    Start-Sleep -Milliseconds 20
  }
  $text += $Serial.ReadExisting()
  Append-Output $text
  return $text
}

function Uboot-Command {
  param($Serial, [string]$Command, [int]$Milliseconds = 12000)
  $Serial.Write($Command + "`r")
  $text = Read-Until $Serial $Milliseconds '(?m)^=>\s*$'
  if ($text -notmatch '(?m)^=>\s*$') { throw "U-Boot prompt missing after: $Command" }
  if ($text -match 'Unknown command|Usage:') { throw "U-Boot rejected: $Command" }
  return $text
}

function Require-Crc {
  param($Serial, [string]$Address, [string]$Bytes, [string]$Expected)
  $text = Uboot-Command $Serial "crc32 $Address $Bytes" 30000
  if ($text -notmatch "==>\s+$Expected\b") {
    throw "CRC mismatch at $Address length $Bytes; expected $Expected"
  }
}

function Copy-Bytes {
  param($Serial, [uint64]$Source, [uint64]$Target, [uint64]$Bytes)
  if (($Source -lt $Target -and $Source + $Bytes -gt $Target) -or
      ($Target -lt $Source -and $Target + $Bytes -gt $Source)) {
    throw 'Overlapping U-Boot copy is not permitted'
  }
  $offset = [uint64]0
  while ($offset -lt $Bytes) {
    $count = [Math]::Min([uint64]0x400000, $Bytes - $offset)
    [void](Uboot-Command $Serial ('cp.b {0:x} {1:x} {2:x}' -f `
      ($Source + $offset), ($Target + $offset), $count))
    $offset += $count
  }
}

$resolved = Resolve-K7Port $Port
$serial = [System.IO.Ports.SerialPort]::new(
  $resolved, 1500000, [System.IO.Ports.Parity]::None, 8,
  [System.IO.Ports.StopBits]::One)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 1000
$serial.Open()
try {
  $serial.DiscardInBuffer()
  if ($Mode -eq 'Enter') {
    $serial.Write("`r")
    $nsh = Read-Until $serial 2500 'nsh>\s*(?:\x1b\[K)?$'
    if ($nsh -notmatch 'nsh>') { throw 'NSH prompt missing; reboot not sent' }
    $serial.Write("reboot`r")
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $boot = ''
    while ($timer.ElapsedMilliseconds -lt 25000) {
      $boot += $serial.ReadExisting()
      $serial.Write([char]3)
      if ($boot -match '(?m)^=>\s*$') { break }
      Start-Sleep -Milliseconds 50
    }
    $boot += $serial.ReadExisting()
    Append-Output $boot
    if ($boot -notmatch '(?m)^=>\s*$') { throw 'Autoboot was not interrupted' }
    $serial.DiscardOutBuffer()
    Start-Sleep -Milliseconds 400
    Append-Output $serial.ReadExisting()
    $serial.Write("`r")
    $clean = Read-Until $serial 2000 '(?m)^=>\s*$'
    if ($clean -notmatch '(?m)^=>\s*$') { throw 'Clean U-Boot prompt missing' }
    Require-Crc $serial '90000000' '44b0310' '2af64aa7'
    Require-Crc $serial '86000000' '3e7da30' 'b5f7ae2d'
    $serial.Write("fastboot usb 1`r")
    [void](Read-Until $serial 2500)
  }
  elseif ($Mode -eq 'Final') {
    $serial.Write([char]3)
    $prompt = Read-Until $serial 5000 '(?m)^=>\s*$'
    if ($prompt -notmatch '(?m)^=>\s*$') { throw 'Fastboot did not return to U-Boot prompt' }
    Require-Crc $serial '40c00800' '6e8e570' '5442081a'
    Require-Crc $serial '90000000' '44b0310' '2af64aa7'
    Require-Crc $serial '86000000' '3e7da30' 'b5f7ae2d'
    Copy-Bytes $serial ([Convert]::ToUInt64('40c00800', 16)) `
      ([Convert]::ToUInt64('80000000', 16)) ([Convert]::ToUInt64('6000000', 16))
    Require-Crc $serial '80000000' '9e7da30' 'b20f998f'
    Copy-Bytes $serial ([Convert]::ToUInt64('46c00800', 16)) `
      ([Convert]::ToUInt64('40400000', 16)) ([Convert]::ToUInt64('e8e570', 16))
    Require-Crc $serial '40400000' 'e8e570' 'ee4dacac'
    $dtb = Uboot-Command $serial 'md.l 48300000 1'
    if ($dtb.ToLowerInvariant() -notmatch 'edfe0dd0') { throw 'DTB magic mismatch' }
    $serial.Write("booti 40400000 - 48300000`r")
    $boot = Read-Until $serial 25000 'nsh>\s*(?:\x1b\[K)?$'
    if ($boot -notmatch 'nsh>') { throw 'New firmware did not reach NSH prompt' }
  }
  else {
    $serial.Write("`r")
    $nsh = Read-Until $serial 2500 'nsh>\s*(?:\x1b\[K)?$'
    if ($nsh -notmatch 'nsh>') { throw 'NSH prompt missing before grouped probe' }
    $serial.Write("k7sound capture-pga24-grouped 3200`r")
    $result = Read-Until $serial 15000 'nsh>\s*(?:\x1b\[K)?$'
    if ($result -notmatch 'SOUND pio=0 frames=3200') { throw 'Grouped capture did not complete 3200 frames' }
    if ($result -notmatch 'SOUND grouped words=51200 mismatches=(\d+)') { throw 'Grouped diagnostics missing' }
    if ($result -notmatch 'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0') {
      throw 'Grouped capture cleanup failed'
    }
  }
}
finally {
  $serial.Close()
  [IO.File]::WriteAllText($logPath, $script:log.ToString(), [Text.UTF8Encoding]::new($false))
  [Console]::Error.WriteLine("K7_SERIAL_PORT=$resolved")
  [Console]::Error.WriteLine("K7_LOG=$logPath")
}
