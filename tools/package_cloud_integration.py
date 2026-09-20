#!/usr/bin/env python3
"""Build a reviewable BLE + business API + cloud speech integration bundle."""

import hashlib
import json
import pathlib
import subprocess
import sys
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "deliveries" / "整机蓝牙联网云端接口_20260914.zip"
EVIDENCE = ROOT / "evidence" / "integration-api-20260914" / "interface-package.json"

FILES = [
    "host/streaming_asr/__init__.py",
    "host/streaming_asr/session.py",
    "host/streaming_asr/gateway.py",
    "host/streaming_asr/serve.py",
    "host/streaming_asr/client.py",
    "host/streaming_asr/test_gateway.py",
    "host/streaming_asr/requirements.txt",
    "docs/speech-service流式ASR接入_20260914.md",
    "docs/AI日志写入锁修复_20260914.md",
    "docs/云语音单任务运行时接入_20260914.md",
    "evidence/speech-stream-live-20260914/result.json",
    "evidence/cloud-radio-build-20260914/arm64-result-final.json",
    "app/k7agent/cloud/include/cloud_speech_runtime_owner.h",
    "app/k7agent/cloud/src/cloud_speech_runtime_owner.c",
    "tests/k7cloud/test_cloud_speech_runtime_owner.c",
    "tests/k7cloud/run_runtime_owner_tests.ps1",
    "frontend/vela-provision.mjs",
    "frontend/完整配网接入示例.mjs",
    "frontend/整机联网语音适配器.mjs",
    "frontend/speech-http-client.mjs",
    "frontend/整机BLE与云端语音拼接示例.mjs",
    "frontend/gimbal-cloud-client.mjs",
    "frontend/业务后端接入示例.mjs",
    "frontend/联网与云端语音前端接口.md",
    "frontend/业务后端接口接入_20260914.md",
    "frontend/交付入口.md",
    "frontend/test-vela-provision.mjs",
    "frontend/test-online-speech-adapter.mjs",
    "frontend/test-speech-http-client.mjs",
    "frontend/test-gimbal-cloud-client.mjs",
    "host/cloud_speech_bridge/__init__.py",
    "host/cloud_speech_bridge/bridge.py",
    "host/cloud_speech_bridge/server.py",
    "host/cloud_speech_bridge/README.md",
    "host/cloud_speech_bridge/test_bridge.py",
    "host/cloud_speech_bridge/test_server.py",
    "docs/整机云端联调契约_20260914.md",
    "docs/蓝牙配网与云语音整机接入_20260914.md",
    "docs/模型接力交接_20260914.md",
    "evidence/integration-api-20260914/openapi.json",
    "evidence/build/ble-wifi-cloud-speech-orchestrator-20260914/verification.json",
    "evidence/k7cloud-radio-readiness-20260914/host-verification.json",
    "app/k7agent/Kconfig",
    "app/k7agent/CMakeLists.txt",
    "app/k7radio/k7_radio_service.h",
    "app/k7radio/wifi_ip_service.inc",
    "app/k7agent/cloud/README.md",
    "app/k7agent/cloud/include/cloud_speech_orchestrator.h",
    "app/k7agent/cloud/include/cloud_speech_mimo_adapter.h",
    "app/k7agent/cloud/include/mimo_cloud_client.h",
    "app/k7agent/cloud/include/mimo_v25_profile.h",
    "app/k7agent/cloud/include/vv_dns_client.h",
    "app/k7agent/cloud/include/vv_dns_nuttx.h",
    "app/k7agent/cloud/include/vv_https_client.h",
    "app/k7agent/cloud/include/vv_https_mbedtls.h",
    "app/k7agent/cloud/include/cloud_speech_radio_bridge.h",
    "app/k7agent/cloud/src/cloud_speech_orchestrator.c",
    "app/k7agent/cloud/src/cloud_speech_mimo_adapter.c",
    "app/k7agent/cloud/src/k7cloud_main.c",
    "app/k7agent/cloud/src/mimo_cloud_client.c",
    "app/k7agent/cloud/src/mimo_v25_profile.c",
    "app/k7agent/cloud/src/vv_dns_client.c",
    "app/k7agent/cloud/src/vv_dns_nuttx.c",
    "app/k7agent/cloud/src/vv_https_client.c",
    "app/k7agent/cloud/src/vv_https_mbedtls.c",
    "app/k7agent/cloud/src/cloud_speech_radio_bridge.c",
    "app/k7agent/cloud/src/cloud_speech_k7radio_sync.c",
    "board/kickpi_k7/configs/velavision_cloud_speech_local/defconfig",
    "board/kickpi_k7/configs/velavision_cloud_speech_local/README.md",
    "tests/k7cloud/test_cloud_speech_orchestrator.c",
    "tests/k7cloud/test_cloud_speech_radio_bridge.c",
    "tests/k7cloud/run_host_tests.ps1",
]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command):
    result = subprocess.run(
        command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, encoding="utf-8",
    )
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout + result.stderr


def main() -> int:
    missing = [item for item in FILES if not (ROOT / item).is_file()]
    if missing:
        raise RuntimeError("missing integration files: " + ", ".join(missing))

    node_output = run([
        "node", "--test",
        "frontend/test-vela-provision.mjs",
        "frontend/test-online-speech-adapter.mjs",
        "frontend/test-speech-http-client.mjs",
        "frontend/test-gimbal-cloud-client.mjs",
    ])
    python_output = run([
        sys.executable, "-m", "unittest", "discover", "-s",
        "host/cloud_speech_bridge", "-p", "test_*.py", "-v",
    ])

    manifest_files = []
    for item in FILES:
        path = ROOT / item
        manifest_files.append({
            "path": item.replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    manifest = {
        "scope": "BLE Wi-Fi provisioning, exact business OpenAPI client, loopback MiMo ASR/TTS bridge, and compile-only ARM64 cloud speech candidate",
        "contains_credentials": False,
        "hardware_tested_by_package_step": False,
        "files": manifest_files,
    }
    encoded_manifest = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in FILES:
            archive.write(ROOT / item, "velavision-integration/" + item.replace("\\", "/"))
        archive.writestr("velavision-integration/SHA256SUMS.json", encoded_manifest)

    with zipfile.ZipFile(OUT) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("delivery ZIP integrity check failed")
        for item in manifest_files:
            payload = archive.read("velavision-integration/" + item["path"])
            if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                raise RuntimeError("delivery hash mismatch: " + item["path"])

    report = {
        "archive": str(OUT.relative_to(ROOT)).replace("\\", "/"),
        "bytes": OUT.stat().st_size,
        "sha256": sha256(OUT),
        "archive_verified": True,
        "file_count": len(FILES),
        "node_tests_passed": node_output.count("✔"),
        "python_tests_passed": python_output.count(" ... ok"),
        "real_backend_called": False,
        "real_mimo_called": False,
        "credentials_saved": False,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
