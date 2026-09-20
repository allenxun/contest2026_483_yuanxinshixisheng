$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Resolve-Path (Join-Path $here '..\..')
$vendor = Join-Path $project 'work-in-progress\parallel-voicelink\vendor'
$include = Join-Path $project 'app\voicelink\include'
$formal = Join-Path $project 'app\voicelink\src\native_asr_runtime.cpp'
$compiler = 'D:\software\mingw64\mingw64\bin\g++.exe'
$common = @('-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', "-I$here", "-I$include", "-I$vendor")

foreach ($optimization in @('O0', 'O2')) {
  $flag = "-$optimization"
  $baselineExe = Join-Path $here "baseline_$optimization.exe"
  $candidateExe = Join-Path $here "candidate_$optimization.exe"

  & $compiler @common $flag $formal (Join-Path $here 'fake_runtime_test.cpp') '-o' $baselineExe
  if ($LASTEXITCODE) { throw "baseline $optimization compile failed: $LASTEXITCODE" }
  & $baselineExe baseline *>&1 | Tee-Object -FilePath (Join-Path $here "baseline-$optimization-result.txt")
  if ($LASTEXITCODE) { throw "baseline $optimization test failed: $LASTEXITCODE" }

  & $compiler @common $flag (Join-Path $here 'runtime_candidate.cpp') (Join-Path $here 'fake_runtime_test.cpp') '-o' $candidateExe
  if ($LASTEXITCODE) { throw "candidate $optimization compile failed: $LASTEXITCODE" }
  & $candidateExe *>&1 | Tee-Object -FilePath (Join-Path $here "candidate-$optimization-result.txt")
  if ($LASTEXITCODE) { throw "candidate $optimization test failed: $LASTEXITCODE" }
}
