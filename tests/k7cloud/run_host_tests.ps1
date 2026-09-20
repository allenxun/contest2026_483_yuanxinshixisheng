$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$out = Join-Path $PSScriptRoot 'out'
New-Item -ItemType Directory -Force $out | Out-Null
$include = Join-Path $repo 'app\k7agent\cloud\include'
$dnsSource = Join-Path $repo 'app\k7agent\cloud\src\vv_dns_client.c'
$httpsSource = Join-Path $repo 'app\k7agent\cloud\src\vv_https_client.c'
$dnsTest = Join-Path $repo 'work-in-progress\parallel-dns-client-sol\tests\test_dns_client.c'
$httpsTest = Join-Path $repo 'work-in-progress\parallel-https-client-sol\tests\test_https_client.c'
$mimoSource = Join-Path $repo 'app\k7agent\cloud\src\mimo_cloud_client.c'
$mimoProfile = Join-Path $repo 'app\k7agent\cloud\src\mimo_v25_profile.c'
$mimoTest = Join-Path $repo 'tests\k7cloud\test_mimo_cloud_client.c'
$speechSource = Join-Path $repo 'app\k7agent\cloud\src\cloud_speech_orchestrator.c'
$speechTest = Join-Path $repo 'tests\k7cloud\test_cloud_speech_orchestrator.c'
$radioBridgeSource = Join-Path $repo 'app\k7agent\cloud\src\cloud_speech_radio_bridge.c'
$radioBridgeTest = Join-Path $repo 'tests\k7cloud\test_cloud_speech_radio_bridge.c'

foreach ($optimization in @('O0', 'O2')) {
  $dnsExe = Join-Path $out "dns_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic `
    -D_POSIX_C_SOURCE=200809L -I $include $dnsSource $dnsTest -o $dnsExe
  if ($LASTEXITCODE -ne 0) { throw "DNS $optimization compile failed" }
  & $dnsExe
  if ($LASTEXITCODE -ne 0) { throw "DNS $optimization tests failed" }

  $httpsExe = Join-Path $out "https_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror `
    -I $include $httpsSource $httpsTest -o $httpsExe
  if ($LASTEXITCODE -ne 0) { throw "HTTPS $optimization compile failed" }
  & $httpsExe
  if ($LASTEXITCODE -ne 0) { throw "HTTPS $optimization tests failed" }

  $mimoExe = Join-Path $out "mimo_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic `
    -I $include $httpsSource $mimoSource $mimoProfile $mimoTest -o $mimoExe
  if ($LASTEXITCODE -ne 0) { throw "MiMo $optimization compile failed" }
  & $mimoExe
  if ($LASTEXITCODE -ne 0) { throw "MiMo $optimization tests failed" }

  $speechExe = Join-Path $out "speech_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic `
    -I $include $speechSource $speechTest -o $speechExe
  if ($LASTEXITCODE -ne 0) { throw "speech orchestrator $optimization compile failed" }
  & $speechExe
  if ($LASTEXITCODE -ne 0) { throw "speech orchestrator $optimization tests failed" }

  $radioBridgeExe = Join-Path $out "speech_radio_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic `
    -I $include $speechSource $radioBridgeSource $radioBridgeTest -o $radioBridgeExe
  if ($LASTEXITCODE -ne 0) { throw "speech radio bridge $optimization compile failed" }
  & $radioBridgeExe
  if ($LASTEXITCODE -ne 0) { throw "speech radio bridge $optimization tests failed" }
}
