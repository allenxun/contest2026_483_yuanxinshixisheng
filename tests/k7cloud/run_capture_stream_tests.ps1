$ErrorActionPreference='Stop'
$root=Resolve-Path "$PSScriptRoot\..\.."
$cc='D:\software\mingw64\mingw64\bin\gcc.exe'
$out=Join-Path $root 'evidence\capture-stream-20260914'
New-Item -ItemType Directory -Force $out | Out-Null
foreach($opt in @('O0','O2')) {
  foreach($entry in @(@('test_capture_stream.c','pio.c'),@('test_stream_ring.c','stream_ring.c'))) {
    $exe=Join-Path $out ($entry[0]+"-$opt.exe")
    & $cc "-$opt" -std=c11 -Wall -Wextra -Wpedantic -Werror "-I$root/app/k7sound" "$PSScriptRoot/$($entry[0])" "$root/app/k7sound/$($entry[1])" -o $exe
    if($LASTEXITCODE -ne 0){throw 'compile failed'}
    & $exe
    if($LASTEXITCODE -ne 0){throw 'capture stream test failed'}
  }
}
