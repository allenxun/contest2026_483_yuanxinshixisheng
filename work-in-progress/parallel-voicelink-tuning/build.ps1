$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskLibrary = '../parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib/sherpa-onnx-c-api.lib'
& g++ -std=c++17 -O2 -Wall -Wextra -Werror -finput-charset=UTF-8 -fexec-charset=UTF-8 -I ../parallel-voicelink/vendor src/probe.cpp $taskLibrary -o probe.exe
if ($LASTEXITCODE -ne 0) { throw 'Probe build failed' }
& g++ -std=c++17 -O2 -Wall -Wextra -Werror -finput-charset=UTF-8 -fexec-charset=UTF-8 -I include -I ../parallel-voicelink/vendor src/candidate_test.cpp src/audio.cpp $taskLibrary -o candidate_test.exe
if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed' }
