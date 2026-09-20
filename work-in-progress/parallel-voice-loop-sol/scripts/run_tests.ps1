param([string]$Cxx = "g++")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$candidate = Split-Path -Parent $PSScriptRoot
$run = Join-Path $candidate ("evidence/run-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"))
New-Item -ItemType Directory -Force $run | Out-Null
$common = @(
  "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
  "-I$($candidate)\include", "-I$($root)\app\voicelink\include",
  "$($candidate)\src\voice_loop.cpp",
  "$($root)\app\voicelink\src\core.cpp",
  "$($root)\app\voicelink\src\parsers.cpp",
  "$($candidate)\tests\test_voice_loop.cpp"
)
$records = @()
foreach ($opt in @("O0", "O2")) {
  $exe = Join-Path $run ("voice-loop-$opt.exe")
  $buildLog = Join-Path $run ("build-$opt.txt")
  $testLog = Join-Path $run ("test-$opt.txt")
  & $Cxx @common "-$opt" "-o" $exe 2>&1 | Tee-Object -FilePath $buildLog
  if ($LASTEXITCODE -ne 0) { throw "build $opt failed: $LASTEXITCODE" }
  if (-not (Test-Path $buildLog)) { New-Item -ItemType File $buildLog | Out-Null }
  & $exe 2>&1 | Tee-Object -FilePath $testLog
  if ($LASTEXITCODE -ne 0) { throw "test $opt failed: $LASTEXITCODE" }
  $records += [ordered]@{
    optimization = $opt
    executable_sha256 = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower()
    build_log_sha256 = (Get-FileHash -Algorithm SHA256 $buildLog).Hash.ToLower()
    test_log_sha256 = (Get-FileHash -Algorithm SHA256 $testLog).Hash.ToLower()
    output = (Get-Content -Raw $testLog).Trim()
  }
}
$result = [ordered]@{
  generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  scope = "host fake ports only; no device, SDK, serial, VM, network, or fixed prompt playback"
  source_contract = "VelaVision/app/voicelink Controller/ports/asr_runtime and app/k7radio shared transaction adapter"
  password_logged = $false
  records = $records
}
$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $run "results.json")
Write-Output $run
