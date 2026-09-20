$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& g++ -std=c++17 -O2 -Wall -Wextra -Werror -finput-charset=UTF-8 -fexec-charset=UTF-8 -I ../parallel-voicelink/include -I ../parallel-voicelink/vendor scripts/real_binding.cpp ../parallel-voicelink/src/audio.cpp runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib/sherpa-onnx-c-api.lib -o real_binding.exe
if ($LASTEXITCODE -ne 0) { throw 'Real library binding build failed' }
