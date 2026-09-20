$ErrorActionPreference = 'Stop'
$Audit = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = Resolve-Path (Join-Path $Audit '..\..')
$Raw = Join-Path $Audit 'raw'
New-Item -ItemType Directory -Force $Raw | Out-Null
$Cxx = 'g++'

function Invoke-BuildAndTest {
  param([string]$Name, [string[]]$Sources, [string[]]$Includes, [string[]]$Extra = @())
  foreach ($Opt in @('O0', 'O2')) {
    $Exe = Join-Path $Raw "$Name-$Opt.exe"
    $BuildLog = Join-Path $Raw "$Name-$Opt-build.txt"
    $TestLog = Join-Path $Raw "$Name-$Opt-test.txt"
    $Args = @('-std=c++17', "-$Opt", '-Wall', '-Wextra', '-Werror', '-pedantic')
    foreach ($Include in $Includes) { $Args += "-I$Include" }
    $Args += $Extra
    $Args += $Sources
    $Args += @('-o', $Exe)
    & $Cxx @Args 2>&1 | Tee-Object -FilePath $BuildLog
    if ($LASTEXITCODE -ne 0) { throw "$Name $Opt build failed: $LASTEXITCODE" }
    if (-not (Test-Path $BuildLog)) { New-Item -ItemType File $BuildLog | Out-Null }
    & $Exe 2>&1 | Tee-Object -FilePath $TestLog
    if ($LASTEXITCODE -ne 0) { throw "$Name $Opt test failed: $LASTEXITCODE" }
  }
}

$Asr = Join-Path $Project 'work-in-progress\parallel-asr-text-review-sol'
Invoke-BuildAndTest 'asr-current-formal' @(
  (Join-Path $Project 'app\voicelink\src\native_asr_runtime.cpp'),
  (Join-Path $Asr 'fake_runtime_test.cpp')
) @((Join-Path $Asr ''), (Join-Path $Project 'app\voicelink\include'),
    (Join-Path $Project 'work-in-progress\parallel-voicelink\vendor')) @('-pthread')

$Prompt = Join-Path $Project 'work-in-progress\parallel-voice-prompt-adapter-sol'
Invoke-BuildAndTest 'voice-prompt' @(
  (Join-Path $Prompt 'voice_prompt_adapter.cpp'),
  (Join-Path $Prompt 'test_voice_prompt_adapter.cpp')
) @($Prompt)

$Loop = Join-Path $Project 'work-in-progress\parallel-voice-loop-sol'
Invoke-BuildAndTest 'voice-loop' @(
  (Join-Path $Loop 'src\voice_loop.cpp'),
  (Join-Path $Project 'app\voicelink\src\core.cpp'),
  (Join-Path $Project 'app\voicelink\src\parsers.cpp'),
  (Join-Path $Loop 'tests\test_voice_loop.cpp')
) @((Join-Path $Loop 'include'), (Join-Path $Project 'app\voicelink\include'))

$Wifi = Join-Path $Project 'work-in-progress\parallel-wifi-transaction-adapter-sol'
Invoke-BuildAndTest 'wifi-transaction' @(
  (Join-Path $Wifi 'src\wifi_transaction_adapter.cpp'),
  (Join-Path $Project 'app\voicelink\src\core.cpp'),
  (Join-Path $Project 'app\voicelink\src\parsers.cpp'),
  (Join-Path $Wifi 'tests\test_wifi_transaction_adapter.cpp')
) @((Join-Path $Wifi 'include'), (Join-Path $Project 'app\voicelink\include'))

$Worker = Join-Path $Project 'work-in-progress\parallel-capture-asr-worker-sol'
Invoke-BuildAndTest 'capture-asr-worker' @(
  (Join-Path $Worker 'src\capture_asr_worker.cpp'),
  (Join-Path $Worker 'tests\test_worker.cpp')
) @((Join-Path $Worker 'include')) @('-pthread')

Get-ChildItem -LiteralPath $Raw -File | Sort-Object Name | ForEach-Object {
  [pscustomobject]@{
    file = $_.Name
    bytes = $_.Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
  }
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $Audit 'raw-manifest.json')

$CandidateNames = @(
  'parallel-asr-text-review-sol',
  'parallel-voice-prompt-adapter-sol',
  'parallel-voice-loop-sol',
  'parallel-wifi-transaction-adapter-sol',
  'parallel-capture-asr-worker-sol'
)
$Inputs = @()
foreach ($Name in $CandidateNames) {
  $Root = Join-Path $Project "work-in-progress\$Name"
  Get-ChildItem -LiteralPath $Root -Recurse -File |
    Where-Object { $_.Extension -ne '.exe' } | ForEach-Object {
      $Inputs += $_.FullName
    }
}
$Inputs += @(
  (Join-Path $Project 'app\voicelink\include\voicelink\ports.hpp'),
  (Join-Path $Project 'app\voicelink\include\voicelink\controller.hpp'),
  (Join-Path $Project 'app\voicelink\include\voicelink\types.hpp'),
  (Join-Path $Project 'app\voicelink\include\voicelink\asr_runtime.h'),
  (Join-Path $Project 'app\voicelink\src\core.cpp'),
  (Join-Path $Project 'app\voicelink\src\k7voice_main.cpp'),
  (Join-Path $Project 'app\voicelink\src\native_asr_runtime.cpp'),
  (Join-Path $Project 'app\voicelink\src\voice_wifi_adapter.cpp'),
  (Join-Path $Project 'app\k7sound\k7sound_main.c'),
  (Join-Path $Project 'app\k7sound\pio.h'),
  (Join-Path $Project 'app\k7sound\pio.c'),
  (Join-Path $Project 'app\k7radio\wifi_broker.h'),
  (Join-Path $Project 'app\k7radio\wifi_broker.c'),
  (Join-Path $Project 'app\k7radio\wifi_dispatch.h'),
  (Join-Path $Project 'app\k7radio\wifi_dispatch.c'),
  (Join-Path $Project 'app\k7radio\radio_backend.inc'),
  (Join-Path $Project 'app\k7radio\radio_backend_state.inc'),
  (Join-Path $Project 'app\k7radio\wifi_ip_service.inc')
)
$Inputs | Sort-Object -Unique | ForEach-Object {
  $Item = Get-Item -LiteralPath $_
  [pscustomobject]@{
    path = $Item.FullName.Substring($Project.Path.Length + 1).Replace('\', '/')
    bytes = $Item.Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Item.FullName).Hash.ToLowerInvariant()
  }
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $Audit 'input-manifest.json')
