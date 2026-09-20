"""Record the reviewed wake-partial build stage without overstating board coverage."""

from __future__ import print_function

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "voice-rule-wakepartial-20260912"
OUTPUT = EVIDENCE / "acceptance.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


build = json.loads((EVIDENCE / "build-result.json").read_text(encoding="utf-8"))
package = json.loads(
    (EVIDENCE / "ram-package-wakepartial.json").read_text(encoding="utf-8")
)
elf = json.loads(
    (EVIDENCE / "elf-audit-wakepartial.json").read_text(encoding="utf-8")
)
host = json.loads(
    (
        ROOT
        / "evidence"
        / "voicelink-core-integration-20260910"
        / "run-20260912T122301237955Z"
        / "result.json"
    ).read_text(encoding="utf-8")
)
prior_result = json.loads(
    (EVIDENCE / "voice-provision-20260912-201907.json").read_text(
        encoding="utf-8"
    )
)
prior_log = (EVIDENCE / "voice-provision-20260912-201907.log").read_bytes()
uboot_prompt = (EVIDENCE / "current-uboot-prompt.log").read_bytes()

assert build["build_exit_code"] == 0
assert build["artifacts"]["nuttx.bin"]["sha256"] == package["firmware_sha256"]
assert package["firmware_sha256"] == (
    "f96ecdb89b13af582428494c0cc903e66061ede1e3e0ec419e7512a509fe46e5"
)
assert package["sha256"] == (
    "12426051aa50132bcb2a8c4ed13cf9d1611aa01ca221c7eada09b1cce123a70d"
)
assert package["flash_commands"] is False
assert elf["passed"] is True
assert host["passed"] is True and host["source_unchanged"] is True
assert b"ASR_INFER RESULT" in prior_log and "你好 open".encode("utf-8") in prior_log
assert b"TLS_CHECK PASS" in prior_log
assert b"live=0" in prior_log
assert prior_result["assertion"] is False and prior_result["tls_failure"] is False
assert b"=>" in uboot_prompt

source_paths = (
    "app/voicelink/src/parsers.cpp",
    "app/voicelink/include/voicelink/parsers.hpp",
    "app/voicelink/tests/test_flow.cpp",
    "app/voicelink/src/native_tls_selftest.cpp",
)
source_hashes = {path: sha256(ROOT / path) for path in source_paths}
for path, digest in source_hashes.items():
    assert build["inputs"][path] == digest

record = {
    "stage": "wake-partial-built-not-loaded",
    "passed": True,
    "host_flow_test": {
        "passed": True,
        "evidence": (
            "evidence/voicelink-core-integration-20260910/"
            "run-20260912T122301237955Z/result.json"
        ),
    },
    "prior_board_observation": {
        "firmware": "voice-rule-provision-tlsrepeat-20260912",
        "microphone_asr_text": "你好 open",
        "repeated_tls_pass": True,
        "model_storage_released": True,
        "flow_completed": False,
        "reason": "unattended later turns had no speech and the bounded session timed out",
        "evidence": "evidence/voice-rule-wakepartial-20260912/voice-provision-20260912-201907.log",
    },
    "new_build": {
        "elf_sha256": build["artifacts"]["nuttx"]["sha256"],
        "firmware_sha256": package["firmware_sha256"],
        "payload_sha256": package["sha256"],
        "payload_crc32": package["crc32"],
        "payload_bytes": package["bytes"],
        "elf_audit_passed": True,
        "flash_commands": False,
        "source_hashes": source_hashes,
    },
    "new_firmware_board_tested": False,
    "current_board_state": "U-Boot prompt",
    "current_board_evidence": (
        "evidence/voice-rule-wakepartial-20260912/current-uboot-prompt.log"
    ),
    "blocker": (
        "Windows VMware USB proxy entered Code 43 after OTG re-enumeration; "
        "Ubuntu VM and SSH were recovered by removing boot-time OTG autoconnect, "
        "but the new payload has not been transferred"
    ),
    "next": (
        "restart VMUSBArbService with an administrator token or physically "
        "replug OTG, attach 18d1:4d00 after Ubuntu boots, transfer payload, "
        "verify RAM/model/firmware CRCs, boot, and run the real voice flow"
    ),
    "boundaries": {
        "emmc_written": False,
        "stm32_written": False,
        "gimbal_started": False,
        "remote_pushed": False,
        "credentials_logged": False,
    },
}

if OUTPUT.exists():
    raise RuntimeError("refusing to overwrite acceptance evidence")
OUTPUT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUTPUT)
