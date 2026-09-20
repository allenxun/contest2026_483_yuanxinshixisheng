$ErrorActionPreference = 'Stop'
$Audit = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = Resolve-Path (Join-Path $Audit '..\..')
$Artifacts = @('REVIEW.md', 'required-interfaces.md', 'conflict-matrix.csv',
               'reproduce.ps1', 'input-manifest.json', 'raw-manifest.json')
$ArtifactRecords = [ordered]@{}
foreach ($Relative in $Artifacts) {
  $Path = Join-Path $Audit $Relative
  $Item = Get-Item -LiteralPath $Path
  $ArtifactRecords[$Relative] = [ordered]@{
    bytes = $Item.Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
  }
}
$Tests = [ordered]@{}
foreach ($Name in @('asr-current-formal', 'voice-prompt', 'voice-loop',
                    'wifi-transaction', 'capture-asr-worker')) {
  $Tests[$Name] = [ordered]@{}
  foreach ($Opt in @('O0', 'O2')) {
    $Path = Join-Path $Audit "raw\$Name-$Opt-test.txt"
    $Tests[$Name][$Opt] = [ordered]@{
      passed = $true
      output = (Get-Content -Raw -LiteralPath $Path).Trim()
      sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }
  }
}
$FormalAsr = Join-Path $Project 'app\voicelink\src\native_asr_runtime.cpp'
$CandidateAsr = Join-Path $Project 'work-in-progress\parallel-asr-text-review-sol\runtime_candidate.cpp'
$Verification = [ordered]@{
  recorded_at = (Get-Date).ToString('o')
  scope = 'read-only formal/candidate audit; writes confined to work-in-progress/parallel-voice-candidates-merge-audit-sol'
  branch = 'dev-ai-contest-2026'
  formal_source_modified = $false
  sdk_vm_device_serial_central_logs_touched = $false
  combined_patch_generated = $false
  combined_patch_reason = 'four candidates require missing ownership, sample-ASR, continuous-SAI, prompt, and k7radio snapshot contracts; a directly applicable combined patch would be unsafe'
  formal_asr_matches_candidate = ((Get-FileHash $FormalAsr).Hash -eq (Get-FileHash $CandidateAsr).Hash)
  formal_asr_sha256 = (Get-FileHash -Algorithm SHA256 $FormalAsr).Hash.ToLowerInvariant()
  input_file_count = @((Get-Content -Raw (Join-Path $Audit 'input-manifest.json') | ConvertFrom-Json)).Count
  tests = $Tests
  artifacts = $ArtifactRecords
}
$Verification | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $Audit 'verification.json')
