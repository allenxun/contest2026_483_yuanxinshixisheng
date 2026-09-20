param([string]$Run = "evidence/run-20260912T090603012Z")
$ErrorActionPreference = "Stop"
$candidate = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent (Split-Path -Parent $candidate)
& (Join-Path $PSScriptRoot "package.ps1")
$runPath = Join-Path $candidate $Run
$inputs = @(
  "app/voicelink/include/voicelink/controller.hpp",
  "app/voicelink/include/voicelink/ports.hpp",
  "app/voicelink/include/voicelink/types.hpp",
  "app/voicelink/include/voicelink/asr_runtime.h",
  "app/voicelink/src/core.cpp",
  "app/voicelink/src/parsers.cpp",
  "app/voicelink/src/voice_wifi_adapter.cpp"
)
$inputHashes = [ordered]@{}
foreach ($input in $inputs) {
  $inputHashes[$input] = (Get-FileHash -Algorithm SHA256 (Join-Path $project $input)).Hash.ToLower()
}
$delivery = [ordered]@{
  generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  candidate = "VelaVision/work-in-progress/parallel-voice-loop-sol"
  candidate_patch_sha256 = (Get-FileHash -Algorithm SHA256 (Join-Path $candidate "candidate.patch")).Hash.ToLower()
  manifest_sha256 = (Get-FileHash -Algorithm SHA256 (Join-Path $candidate "MANIFEST.sha256")).Hash.ToLower()
  accepted_run = $Run.Replace("\\", "/")
  accepted_results_sha256 = (Get-FileHash -Algorithm SHA256 (Join-Path $runPath "results.json")).Hash.ToLower()
  input_contract_sha256 = $inputHashes
  hardware_tested = $false
  sdk_or_device_touched = $false
  fixed_prompt_playback_implemented = $false
  unfinished_hardware = @(
    "continuous microphone capture adapter",
    "asynchronous k7_asr_microphone_text worker adapter",
    "board fixed-prompt TtsPort",
    "real shared Wi-Fi scan/connect joint run",
    "device cancellation, timeout, open-network, and stale-event cleanup",
    "long multi-turn and rekey validation"
  )
}
$delivery | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $candidate "evidence/delivery.json")
$delivery | ConvertTo-Json -Depth 8
