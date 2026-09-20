"""Delete only explicitly listed, regenerable Ubuntu CMake output trees."""

from pathlib import Path
import shutil


ROOT = Path("/home/swl/openvela/cmake_out").resolve()
KEEP = {
    "velavision_spoken_tts_gated_sharedcache2_20260914",
    "velavision_wifi_arp_20260909",
}
DELETE = {
    "velavision_spoken_tts_gated_sharedcache_20260914",
    "velavision_spoken_tts_gated_speechcache_20260914",
    "velavision_spoken_tts_gated_envalloc2_20260914",
    "velavision_spoken_tts_gated_pathdiag_20260914",
    "velavision_spoken_tts_gated_flowui2_20260914",
    "velavision_spoken_tts_gated_flowfix_20260914",
    "velavision_spoken_tts_gated_pathfix_20260914",
    "velavision_spoken_tts_gated_flowui_20260914",
    "velavision_spoken_tts_gated_20260913",
    "velavision_spoken_tts_arena_fix_20260913",
    "velavision_spoken_tts_asr_arena_fix_20260913",
    "velavision_spoken_tts_20260913",
    "velavision_voice_rule_provision_wakepartial_20260912",
    "velavision_voice_rule_provision_tlsrepeat_20260912",
    "velavision_voice_rule_provision_20260912",
    "velavision_voice_start_network_20260913",
    "velavision_voice_ui_connect_20260913",
    "velavision_audio_cued_capture_20260913",
    "velavision_asr_fixed_fixture_20260913",
    "velavision_speaker_csr_20260913",
    "velavision_voice_asr_audio_buffer_20260912",
    "velavision_voice_tls_20260911",
    "velavision_voice_asr_text_20260912",
    "velavision_k7cloud_link_attempt5_20260913",
    "velavision_k7cloud_link_attempt4_20260913",
    "velavision_k7cloud_link_attempt3_20260912",
    "velavision_k7cloud_link_attempt2_20260912",
    "velavision_k7cloud_link_20260912",
}


if not ROOT.is_dir() or str(ROOT) != "/home/swl/openvela/cmake_out":
    raise RuntimeError("unexpected build root")
if KEEP & DELETE:
    raise RuntimeError("keep/delete lists overlap")

removed = []
for name in sorted(DELETE):
    target = (ROOT / name).resolve()
    if target.parent != ROOT or target.name != name:
        raise RuntimeError("unsafe resolved target: " + str(target))
    if target.is_dir():
        shutil.rmtree(str(target))
        removed.append(name)

for name in KEEP:
    if not (ROOT / name).is_dir():
        raise RuntimeError("expected retained build is missing: " + name)

print("removed=%d" % len(removed))
for name in removed:
    print(name)
