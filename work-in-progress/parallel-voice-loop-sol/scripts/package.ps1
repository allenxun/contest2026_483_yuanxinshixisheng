$ErrorActionPreference = "Stop"
$candidate = Split-Path -Parent $PSScriptRoot
$files = Get-ChildItem -Recurse -File $candidate | Where-Object {
  $_.FullName -notmatch "\\evidence\\" -and $_.Name -notin @("MANIFEST.sha256", "candidate.patch")
} | Sort-Object FullName
$manifest = foreach ($file in $files) {
  $relative = $file.FullName.Substring($candidate.Length + 1).Replace("\\", "/")
  "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower(), $relative
}
$manifest | Set-Content -Encoding ascii (Join-Path $candidate "MANIFEST.sha256")
$prefix = "VelaVision/work-in-progress/parallel-voice-loop-sol"
$patch = [System.Collections.Generic.List[string]]::new()
foreach ($file in $files) {
  $relative = $file.FullName.Substring($candidate.Length + 1).Replace("\\", "/")
  $target = "$prefix/$relative"
  $lines = @(Get-Content -Encoding utf8 $file.FullName)
  $patch.Add("diff --git a/$target b/$target")
  $patch.Add("new file mode 100644")
  $patch.Add("--- /dev/null")
  $patch.Add("+++ b/$target")
  $patch.Add("@@ -0,0 +1,$($lines.Count) @@")
  foreach ($line in $lines) { $patch.Add("+$line") }
}
$patch | Set-Content -Encoding utf8 (Join-Path $candidate "candidate.patch")
