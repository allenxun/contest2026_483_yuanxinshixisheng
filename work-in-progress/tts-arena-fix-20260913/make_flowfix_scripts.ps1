$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$pairs = @(
  @('rebuild_tts_envalloc2.py', 'rebuild_tts_flowfix.py'),
  @('build_envalloc2_runtime.py', 'build_flowfix_runtime.py'),
  @('package_envalloc2.py', 'package_flowfix.py'),
  @('verify_envalloc2_package.py', 'verify_flowfix_package.py'),
  @('load_envalloc2.py', 'load_flowfix.py'),
  @('watch_and_transfer_envalloc2.py', 'watch_and_transfer_flowfix.py')
)

foreach ($pair in $pairs) {
  $content = Get-Content -LiteralPath (Join-Path $here $pair[0]) -Raw
  $content = $content.Replace('envalloc2', 'flowfix').Replace('ENVALLOC2', 'FLOWFIX')
  Set-Content -LiteralPath (Join-Path $here $pair[1]) -Value $content -Encoding utf8NoBOM
}
