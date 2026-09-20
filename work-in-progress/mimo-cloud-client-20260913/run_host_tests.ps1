$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $root '..\..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Force $out | Out-Null

foreach ($optimization in @('O0', 'O2')) {
  $exe = Join-Path $out "mimo_cloud_$optimization.exe"
  & gcc -std=c11 "-$optimization" -Wall -Wextra -Werror -pedantic `
    -I (Join-Path $root 'include') `
    -I (Join-Path $repo 'app\k7agent\cloud\include') `
    (Join-Path $repo 'app\k7agent\cloud\src\vv_https_client.c') `
    (Join-Path $root 'src\mimo_cloud_client.c') `
    (Join-Path $root 'src\mimo_v25_profile.c') `
    (Join-Path $root 'tests\test_mimo_cloud_client.c') -o $exe
  if ($LASTEXITCODE -ne 0) { throw "$optimization compile failed" }
  & $exe
  if ($LASTEXITCODE -ne 0) { throw "$optimization tests failed" }
}
