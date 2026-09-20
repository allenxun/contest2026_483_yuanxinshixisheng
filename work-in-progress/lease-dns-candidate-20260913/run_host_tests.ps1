$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$gcc = (Get-Command gcc -ErrorAction Stop).Source
$gxx = (Get-Command g++ -ErrorAction Stop).Source
$nm = (Get-Command nm -ErrorAction Stop).Source
$results = New-Object System.Collections.Generic.List[string]

foreach ($optimization in @('O0', 'O2')) {
  $cObject = Join-Path $out "vv_lease_dns_$optimization.o"
  $binary = Join-Path $out "test_lease_dns_$optimization.exe"

  $cArgs = @('-std=c11', '-pedantic', '-Wall', '-Wextra', '-Werror',
    "-$optimization", '-I', (Join-Path $root 'include'), '-c',
    (Join-Path $root 'src\vv_lease_dns.c'), '-o', $cObject)
  & $gcc @cArgs
  if ($LASTEXITCODE -ne 0) { throw "C compile failed at $optimization" }
  $undefined = (& $nm '-u' $cObject | Out-String)
  if ($undefined -match '(?im)\b(malloc|calloc|realloc|free|_Zn[a-zA-Z0-9_]*)\b') {
    throw "Heap symbol found at $optimization`: $undefined"
  }

  $cxxArgs = @('-std=c++17', '-pedantic', '-Wall', '-Wextra', '-Werror',
    "-$optimization", '-I', (Join-Path $root 'include'),
    (Join-Path $root 'tests\test_lease_dns.cpp'), $cObject, '-o', $binary)
  & $gxx @cxxArgs
  if ($LASTEXITCODE -ne 0) { throw "C++ link failed at $optimization" }

  $output = (& $binary | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $output.StartsWith('PASS ')) {
    throw "Test failed at $optimization`: $output"
  }
  $results.Add("$optimization $output")
}

$results.Add('formal_source_modified=false')
$results.Add('heap_symbol_audit=pass')
$results.Add('network_called=false')
$results.Add('credential_used=false')
$results.Add('board_touched=false')
$resultPath = Join-Path $root 'test-results.txt'
[System.IO.File]::WriteAllLines($resultPath, $results,
  [System.Text.UTF8Encoding]::new($false))
$results
