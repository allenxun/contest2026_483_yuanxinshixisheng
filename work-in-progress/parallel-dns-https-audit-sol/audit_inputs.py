#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only verifier for the DNS/HTTPS audit inputs.

The script hashes files and reports selected Kconfig symbols.  It never edits
the repository or SDK.  Run it on Windows for repository inputs and inside the
Ubuntu VM (or over an already-authorized remote shell) with --sdk for SDK
inputs.
"""

import argparse
import hashlib
import json
from pathlib import Path


LOCAL_FILES = [
    "README.md",
    "project-manifest.json",
    "docs/代码日志对应表.md",
    "artifacts/audio-pause-20260911/.config",
    "board/kickpi_k7/configs/velavision_wifi_ip_local/defconfig",
    "app/k7radio/skw_netdev.c",
    "app/k7radio/wifi_ip_service.inc",
    "evidence/build/audio-pause-20260911/verification.json",
    "evidence/wifi-arp-20260910/final-status.json",
]

SDK_FILES = [
    "nuttx/libs/libc/netdb/Kconfig",
    "nuttx/include/nuttx/net/dns.h",
    "nuttx/libs/libc/netdb/lib_dnsaddserver.c",
    "nuttx/libs/libc/netdb/lib_getaddrinfo.c",
    "nuttx/drivers/crypto/Kconfig",
    "nuttx/libs/libc/misc/lib_getrandom.c",
    "nuttx/arch/arm64/src/rk3576/CMakeLists.txt",
    "apps/crypto/mbedtls/Kconfig",
    "apps/crypto/mbedtls/CMakeLists.txt",
    "apps/crypto/mbedtls/include/mbedtls/mbedtls_config.h",
    "apps/crypto/mbedtls/mbedtls/library/entropy_poll.c",
    "apps/netutils/webclient/Kconfig",
    "apps/include/netutils/webclient.h",
    "apps/netutils/webclient/webclient.c",
    "apps/netutils/libcurl4nx/Kconfig",
    "apps/netutils/libcurl4nx/curl4nx_easy_setopt.c",
    "apps/netutils/dhcpc/Kconfig",
    "apps/include/netutils/dhcpc.h",
    "apps/netutils/dhcpc/dhcpc.c",
    "apps/netutils/netlib/netlib_setipv4dnsaddr.c",
]

CONFIG_SYMBOLS = [
    "CONFIG_NET",
    "CONFIG_NET_IPv4",
    "CONFIG_NET_TCP",
    "CONFIG_NET_UDP",
    "CONFIG_NET_SOCKOPTS",
    "CONFIG_NETUTILS_DHCPC",
    "CONFIG_NETUTILS_NETLIB",
    "CONFIG_LIBC_NETDB",
    "CONFIG_NETDB_DNSCLIENT",
    "CONFIG_NETUTILS_WEBCLIENT",
    "CONFIG_NETUTILS_LIBCURL4NX",
    "CONFIG_UTILS_CURL",
    "CONFIG_CRYPTO_MBEDTLS",
    "CONFIG_ARCH_HAVE_RNG",
    "CONFIG_DEV_RANDOM",
    "CONFIG_DEV_URANDOM",
    "CONFIG_DEV_URANDOM_XORSHIFT128",
    "CONFIG_RTC",
    "CONFIG_CLOCK_TIMEKEEPING",
]


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def config_state(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    result = {}
    for symbol in CONFIG_SYMBOLS:
        enabled = next((line for line in lines if line.startswith(symbol + "=")), None)
        disabled = f"# {symbol} is not set" in lines
        result[symbol] = enabled.split("=", 1)[1] if enabled else ("n" if disabled else "absent")
    return result


def collect(root, names):
    output = {}
    for name in names:
        path = root / name
        output[name] = digest(path) if path.is_file() else {"missing": True}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).resolve().with_name("inputs.json"))
    args = parser.parse_args()

    repo = args.repo.resolve()
    expected = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = {
        "read_only": True,
        "repo": str(repo),
        "local_files": collect(repo, LOCAL_FILES),
        "current_config": config_state(repo / "artifacts/audio-pause-20260911/.config"),
    }
    if args.sdk:
        sdk = args.sdk.resolve()
        report["sdk"] = str(sdk)
        report["sdk_files"] = collect(sdk, SDK_FILES)
    mismatches = []
    for group, expected_group in (("local_files", expected["repository_files"]),
                                  ("sdk_files", expected["sdk_files"] if args.sdk else {})):
        for name, wanted in expected_group.items():
            actual = report[group].get(name, {"missing": True})
            if actual != wanted:
                mismatches.append({"group": group, "path": name,
                                   "expected": wanted, "actual": actual})
    report["mismatches"] = mismatches
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    missing = any(value.get("missing") for value in report["local_files"].values())
    if args.sdk:
        missing = missing or any(value.get("missing") for value in report["sdk_files"].values())
    return 1 if missing or mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
