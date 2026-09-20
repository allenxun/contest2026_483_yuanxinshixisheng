#!/usr/bin/env python3
"""Static verifier for the speech + cloud link-only combined profile.

This script reads repository evidence and writes verification.json.  It does
not invoke Kconfig, build a firmware image, access a network, or touch a board.
"""

import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPOKEN = ROOT / "board/kickpi_k7/configs/velavision_spoken_tts_local/defconfig"
CLOUD = ROOT / "board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig"
FRAGMENT = HERE / "combined-linkonly.fragment"
CONTRACT = HERE / "combined-build-contract.json"
PACKAGE = ROOT / "work-in-progress/tts-arena-fix-20260913/gated-prefix-package.json"
FIRMWARE = ROOT / "work-in-progress/tts-arena-fix-20260913/gated-firmware-result.json"
TTS_HEADER = ROOT / "work-in-progress/tts-spoken-flow-20260913/k7tts_assets_generated.h"
ARENA_HEADER = ROOT / "port/new/nuttx/include/nuttx/mm/k7_model_arena.h"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_config(path):
    values = {}
    occurrences = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        match = re.match(r"^CONFIG_([^=]+)=(.*)$", raw)
        if match:
            name, value = match.groups()
        else:
            match = re.match(r"^# CONFIG_(.+) is not set$", raw)
            if not match:
                continue
            name, value = match.group(1), "n"
        values[name] = value
        occurrences.setdefault(name, []).append({"line": line_number, "value": value})
    return values, occurrences


def integer_define(text, name):
    match = re.search(r"^#define\s+" + re.escape(name) +
                      r"\s+(?:UINT(?:32|64)_C\()?((?:0x)?[0-9a-fA-F]+)\)?$",
                      text, re.MULTILINE)
    if not match:
        raise RuntimeError("missing numeric define: " + name)
    return int(match.group(1), 0)


def no_overlap(regions):
    ordered = sorted(regions, key=lambda item: item[1])
    return all(left[2] <= right[1] for left, right in zip(ordered, ordered[1:]))


def main():
    spoken, spoken_occurrences = parse_config(SPOKEN)
    cloud, _ = parse_config(CLOUD)
    fragment, fragment_occurrences = parse_config(FRAGMENT)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    firmware = json.loads(FIRMWARE.read_text(encoding="utf-8"))

    expected_cloud_overlay = {
        "LIBC_NETDB": "y",
        "NETDB_DNSCLIENT": "y",
        "NETDB_DNSCLIENT_ENTRIES": "2",
        "NETDB_DNSCLIENT_NAMESIZE": "128",
        "NETDB_DNSCLIENT_MAXRESPONSE": "512",
        "NETDB_DNSCLIENT_SEND_TIMEOUT": "1",
        "NETDB_DNSCLIENT_RECV_TIMEOUT": "1",
        "NETDB_DNSCLIENT_RETRIES": "1",
        "NETDB_DNSSERVER_NAMESERVERS": "1",
        "NETDB_DNSSERVER_NOADDR": "y",
        "CRYPTO_MBEDTLS": "y",
        "MBEDTLS_SSL_SRV_C": "n",
        "MBEDTLS_SSL_PROTO_DTLS": "n",
        "MBEDTLS_SSL_IN_CONTENT_LEN": "16384",
        "MBEDTLS_SSL_OUT_CONTENT_LEN": "16384",
        "EXAMPLES_K7CLOUD": "y",
    }
    speech_contract = {
        "RK3576_MODEL_ARENA": "y",
        "EXAMPLES_K7RADIO_IP": "y",
        "EXAMPLES_K7RADIO_SHARED": "y",
        "EXAMPLES_K7SOUND": "y",
        "EXAMPLES_K7VOICE": "y",
        "FS_ROMFS": "y",
        "EXAMPLES_K7VOICE_STAGED_ASSETS": "y",
        "NET": "y",
        "NET_IPv4": "y",
        "NET_TCP": "y",
        "NET_UDP": "y",
        "NET_SOCKOPTS": "y",
    }
    trust_blockers = {
        "CLOCK_TIMEKEEPING": "n",
        "DEV_URANDOM": "n",
        "RTC": "n",
    }

    combined = dict(spoken)
    combined.update(fragment)
    profile_diff = {
        name: {"spoken": spoken.get(name, "<absent>"),
               "cloud": cloud.get(name, "<absent>")}
        for name in sorted(set(spoken) | set(cloud))
        if spoken.get(name) != cloud.get(name)
    }
    expected_diff_names = set(expected_cloud_overlay) | {
        "FS_ROMFS", "EXAMPLES_K7VOICE_STAGED_ASSETS"
    }

    arena_text = ARENA_HEADER.read_text(encoding="utf-8")
    tts_text = TTS_HEADER.read_text(encoding="utf-8")
    arena_base = integer_define(arena_text, "K7_MODEL_ARENA_BASE")
    window_size = integer_define(arena_text, "K7_MODEL_WINDOW_SIZE")
    arena_size = 0x20000000
    tts_base = integer_define(tts_text, "K7_TTS_ROM_ADDRESS")
    tts_bytes = integer_define(tts_text, "K7_TTS_ROM_BYTES")
    staged_regions = [
        ("encoder", 0x80000000, 0x80000000 + 0x09E7DA30),
        ("decoder", 0x90000000, 0x90000000 + 0x044B0310),
        ("tts_romfs", tts_base, tts_base + tts_bytes),
    ]
    package_limit = contract["package_policy"]["download_payload_limit_bytes"]
    package_headroom = package_limit - package["bytes"]

    voicelink_cmake = (ROOT / "app/voicelink/CMakeLists.txt").read_text(encoding="utf-8")
    agent_cmake = (ROOT / "app/k7agent/CMakeLists.txt").read_text(encoding="utf-8")
    agent_kconfig = (ROOT / "app/k7agent/Kconfig").read_text(encoding="utf-8")
    tls_source = (ROOT / "app/k7agent/cloud/src/vv_https_mbedtls.c").read_text(encoding="utf-8")
    cloud_main = (ROOT / "app/k7agent/cloud/src/k7cloud_main.c").read_text(encoding="utf-8")

    checks = {
        "source_profiles_exist": all(path.is_file() for path in (SPOKEN, CLOUD)),
        "source_profile_diff_is_known": set(profile_diff) == expected_diff_names,
        "cloud_profile_matches_overlay": all(cloud.get(k) == v for k, v in expected_cloud_overlay.items()),
        "fragment_cloud_overlay_exact": all(fragment.get(k) == v for k, v in expected_cloud_overlay.items()),
        "fragment_preserves_speech_contract": all(fragment.get(k) == v for k, v in speech_contract.items()),
        "fragment_symbol_set_exact": set(fragment) == set(expected_cloud_overlay) | set(speech_contract) | set(trust_blockers),
        "combined_contract_resolves": all(combined.get(k) == v for k, v in {**speech_contract, **expected_cloud_overlay}.items()),
        "linkonly_trust_gates_remain_closed": all(combined.get(k) == v for k, v in trust_blockers.items()),
        "fragment_has_no_duplicate_assignments": all(len(items) == 1 for items in fragment_occurrences.values()),
        "spoken_duplicate_romfs_is_last_value_y": spoken.get("FS_ROMFS") == "y" and len(spoken_occurrences.get("FS_ROMFS", [])) == 2,
        "voice_cmake_hash_pins_runtime": all(token in voicelink_cmake for token in ("K7VOICE_ORT_OBJECT_SHA256", "file(SHA256", "hash mismatch")),
        "voice_cmake_requires_asr_tts_romfs": "Spoken provisioning requires microphone ASR and ROMFS resources" in voicelink_cmake,
        "cloud_cmake_has_all_five_sources": all(name in agent_cmake for name in ("vv_dns_client.c", "vv_dns_nuttx.c", "vv_https_client.c", "vv_https_mbedtls.c", "k7cloud_main.c")),
        "cloud_kconfig_dependencies_present": all(name in agent_kconfig for name in ("EXAMPLES_K7RADIO_IP", "NET_TCP", "NET_SOCKOPTS", "NETDB_DNSCLIENT", "CRYPTO_MBEDTLS")),
        "tls_requires_ca_security_gate_and_sni": all(token in tls_source for token in ("cfg->ca_pem", "cfg->security_ready", "mbedtls_ssl_set_hostname", "mbedtls_ssl_get_verify_result")),
        "cloud_command_still_disables_requests": "network_request=disabled" in cloud_main,
        "arena_is_lower_half_of_staged_window": arena_base == 0x60000000 and arena_size == 0x20000000 and window_size == 0x40000000,
        "staged_assets_are_disjoint": no_overlap(staged_regions),
        "staged_assets_inside_upper_half": all(arena_base + arena_size <= start < end <= arena_base + window_size for _, start, end in staged_regions),
        "current_ram_package_within_limit": package_headroom >= 0,
        "current_package_is_ram_only": package.get("flash_commands") is False,
        "gated_runtime_hash_is_pinned": firmware.get("runtime_sha256") == contract["cmake_cache_required"]["K7VOICE_ORT_OBJECT_SHA256"],
    }

    result = {
        "status": "pass" if all(checks.values()) else "fail",
        "scope": "static combined-profile audit only; no SDK/config mutation, build, network, credential, board or flash operation",
        "checks": checks,
        "inputs": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
                   for path in (SPOKEN, CLOUD, FRAGMENT, CONTRACT, PACKAGE, FIRMWARE,
                                TTS_HEADER, ARENA_HEADER,
                                ROOT / "app/voicelink/Kconfig",
                                ROOT / "app/voicelink/CMakeLists.txt",
                                ROOT / "app/k7agent/Kconfig",
                                ROOT / "app/k7agent/CMakeLists.txt",
                                ROOT / "app/k7agent/cloud/src/k7cloud_main.c",
                                ROOT / "app/k7agent/cloud/src/vv_https_mbedtls.c")},
        "source_profile_differences": profile_diff,
        "combined_profile": {
            "base": str(SPOKEN.relative_to(ROOT)).replace("\\", "/"),
            "overlay": str(FRAGMENT.relative_to(ROOT)).replace("\\", "/"),
            "runtime_https_ready": False,
            "reason": "entropy, trusted wall time and caller-owned CA are not validated or provisioned",
        },
        "memory": {
            "allocator": {"start": hex(arena_base), "end": hex(arena_base + arena_size), "bytes": arena_size},
            "staged_window": {"start": hex(arena_base + arena_size), "end": hex(arena_base + window_size), "bytes": window_size - arena_size},
            "regions": [{"name": name, "start": hex(start), "end": hex(end), "bytes": end - start}
                        for name, start, end in staged_regions],
            "current_package_bytes": package["bytes"],
            "download_payload_limit_bytes": package_limit,
            "combined_firmware_growth_budget_bytes": package_headroom,
            "growth_budget_gate": "a combined nuttx.bin larger by more than this budget requires a reviewed package-layout change",
        },
        "unresolved_runtime_gates": [
            "Choose and validate an RK3576 hardware entropy source; merely enabling DEV_URANDOM is insufficient.",
            "Choose and validate trusted wall time for X.509 validity; RTC and CLOCK_TIMEKEEPING are currently disabled.",
            "Provide a minimal caller-owned CA bundle for the selected MiMo Token Plan endpoint.",
            "Install DHCP option 6 DNS servers and bind DNS/TLS cancellation to a Wi-Fi lease generation.",
            "Build the combined ELF and require every symbol in combined-build-contract.json exactly once.",
            "Repackage RAM-only and recheck the 117440512-byte OTG payload ceiling; current headroom is small.",
        ],
        "claims": {
            "formal_config_modified": False,
            "sdk_modified": False,
            "firmware_built": False,
            "network_accessed": False,
            "credentials_used": False,
            "board_tested": False,
            "flash_written": False,
        },
    }
    output = HERE / "verification.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
