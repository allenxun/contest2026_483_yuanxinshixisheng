$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$out = Join-Path $PSScriptRoot 'out'
New-Item -ItemType Directory -Force $out | Out-Null
$include = Join-Path $repo 'app\k7agent\cloud\include'
$sources = @(
  (Join-Path $repo 'app\k7agent\cloud\src\cloud_speech_orchestrator.c'),
  (Join-Path $repo 'app\k7agent\cloud\src\cloud_speech_radio_bridge.c'),
  (Join-Path $repo 'app\k7agent\cloud\src\cloud_speech_runtime_owner.c'),
  (Join-Path $PSScriptRoot 'test_cloud_speech_runtime_owner.c')
)
foreach ($optimization in @('O0', 'O2')) {
  $exe = Join-Path $out "speech_runtime_owner_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic -I $include @sources -o $exe
  if ($LASTEXITCODE -ne 0) { throw "runtime owner $optimization compile failed" }
  & $exe
  if ($LASTEXITCODE -ne 0) { throw "runtime owner $optimization tests failed" }
}
