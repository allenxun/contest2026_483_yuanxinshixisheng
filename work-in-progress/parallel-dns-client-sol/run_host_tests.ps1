$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$output = Join-Path $root "out"
New-Item -ItemType Directory -Force $output | Out-Null

$common = @(
  "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
  "-D_POSIX_C_SOURCE=200809L",
  "-I$root/include",
  "$root/src/vv_dns_client.c",
  "$root/tests/test_dns_client.c"
)

foreach ($optimization in @("O0", "O2")) {
  $binary = Join-Path $output "test_dns_client_$optimization.exe"
  & gcc @common "-$optimization" "-o" $binary
  if ($LASTEXITCODE -ne 0) { throw "gcc $optimization failed: $LASTEXITCODE" }
  & $binary
  if ($LASTEXITCODE -ne 0) { throw "tests $optimization failed: $LASTEXITCODE" }
}
