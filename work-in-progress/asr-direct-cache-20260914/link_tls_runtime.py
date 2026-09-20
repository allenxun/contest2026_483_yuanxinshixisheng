"""Resolve the clean ASR runtime's locked TLS self-test dependencies."""

import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path("/home/swl/openvela")
TLS_DIR = SDK / "work/velavision-project/work-in-progress/voice-ui-connect-20260913"
BASE = HERE / "speech-runtime-asr-direct-clean.arm64.o"
TLS = TLS_DIR / "native_tls_selftest.cpp.o"
EMUTLS = TLS_DIR / "emutls.c.o"
EXPECTED = {
    BASE: "ae19752636991600593d3399783c79097330b95a684a65cdf28c98dc06726510",
    TLS: "07aec7ab004e75fbf7a5f025409ecdc5cc06d41754f96014af3bf29f6ed284d3",
    EMUTLS: "acf96b8dcff8dce0a04d9ce03503b48ca4aca3e36b9c522288de3c85dbc326a5",
}
TOOL = SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for path, expected in EXPECTED.items():
    if digest(path) != expected:
        raise RuntimeError("locked TLS input changed: " + str(path))
output = HERE / "speech-runtime-asr-direct-clean-tls.arm64.o"
command = [str(TOOL / "aarch64-none-elf-ld"), "-r", "--strip-debug",
           "-o", str(output), str(BASE), str(TLS), str(EMUTLS)]
result = subprocess.run(command, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=300)
(HERE / "link-clean-tls.log").write_bytes(result.stdout)
if result.returncode:
    raise RuntimeError("TLS resolution link failed")
nm = subprocess.check_output([str(TOOL / "aarch64-none-elf-nm"), "-g", str(output)], text=True)
required = ("k7_tls_selftest", "__emutls_get_address", "k7_asr_audio_text",
            "k7_asr_runtime_reset", "SherpaOnnxCreateOnlineRecognizer")
counts = {name: nm.count(" T " + name + "\n") for name in required}
undefined = subprocess.check_output(
    [str(TOOL / "aarch64-none-elf-nm"), "-u", str(output)], text=True)
record = {
    "status": "pass",
    "inputs": {str(path): expected for path, expected in EXPECTED.items()},
    "output_bytes": output.stat().st_size,
    "output_sha256": digest(output),
    "required_strong_counts": counts,
    "emutls_undefined": "__emutls_get_address" in undefined,
    "tls_selftest_undefined": "k7_tls_selftest" in undefined,
    "command": command,
    "firmware_linked": False,
    "board_tested": False,
}
if (any(value != 1 for value in counts.values()) or
        record["emutls_undefined"] or record["tls_selftest_undefined"]):
    record["status"] = "fail"
(HERE / "clean-tls-runtime-result.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({key: value for key, value in record.items()
                  if key != "command"}, indent=2))
if record["status"] != "pass":
    raise SystemExit(1)
