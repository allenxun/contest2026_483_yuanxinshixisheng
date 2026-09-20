$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Build = Join-Path $Root 'build'
New-Item -ItemType Directory -Force $Build | Out-Null
$Results = Join-Path $Root 'results'
New-Item -ItemType Directory -Force $Results | Out-Null
foreach ($Optimization in @('O0', 'O2')) {
  $Exe = Join-Path $Build "test_worker_$Optimization.exe"
  & g++ -std=c++17 "-$Optimization" -g -Wall -Wextra -Werror -pthread `
    -I (Join-Path $Root 'include') `
    (Join-Path $Root 'src/capture_asr_worker.cpp') `
    (Join-Path $Root 'tests/test_worker.cpp') -o $Exe
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
  & $Exe | Tee-Object -FilePath (Join-Path $Results "$Optimization.txt")
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
