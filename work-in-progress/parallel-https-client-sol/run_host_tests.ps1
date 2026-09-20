$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Force $out | Out-Null
$exe = Join-Path $out 'test_https_client.exe'
& gcc -std=c11 -O0 -g -Wall -Wextra -Werror `
  -I (Join-Path $root 'include') `
  (Join-Path $root 'src/vv_https_client.c') `
  (Join-Path $root 'tests/test_https_client.c') -o $exe
if ($LASTEXITCODE -ne 0) { throw "O0 compile failed: $LASTEXITCODE" }
& $exe
if ($LASTEXITCODE -ne 0) { throw "O0 tests failed: $LASTEXITCODE" }
& gcc -std=c11 -O2 -Wall -Wextra -Werror `
  -I (Join-Path $root 'include') `
  (Join-Path $root 'src/vv_https_client.c') `
  (Join-Path $root 'tests/test_https_client.c') -o $exe
if ($LASTEXITCODE -ne 0) { throw "O2 compile failed: $LASTEXITCODE" }
& $exe
if ($LASTEXITCODE -ne 0) { throw "O2 tests failed: $LASTEXITCODE" }
