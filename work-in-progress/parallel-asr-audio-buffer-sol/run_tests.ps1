$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$compiler = (Get-Command g++).Source
New-Item -ItemType Directory -Force "$root/build", "$root/results" | Out-Null

foreach ($opt in @("O0", "O2")) {
  $exe = "$root/build/test_audio_buffer_$opt.exe"
  $buildLog = "$root/results/$opt-build.txt"
  $arguments = @("-$opt", "-std=c++17", "-Wall", "-Wextra", "-Werror",
    "-pthread", "-I", "$root/include", "-I", "$root/tests/fakes",
    "$root/src/native_asr_runtime.cpp", "$root/tests/test_audio_buffer.cpp",
    "-o", $exe)
  @("compiler=$compiler", "arguments=$($arguments -join ' ')") |
    Set-Content $buildLog
  & $compiler @arguments 2>&1 | Tee-Object -Append -FilePath $buildLog
  $compileExit = $LASTEXITCODE
  "exit_code=$compileExit" | Add-Content $buildLog
  if ($compileExit -ne 0) { throw "compile $opt failed" }
  & $exe 2>&1 | Tee-Object -FilePath "$root/results/$opt-test.txt"
  if ($LASTEXITCODE -ne 0) { throw "test $opt failed" }
}

& $compiler --version | Select-Object -First 1 | Set-Content "$root/results/compiler.txt"
