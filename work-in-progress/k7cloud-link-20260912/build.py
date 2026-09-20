"""Build a separate RK3576 DNS/HTTPS link probe; never touch the board."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela")
BUILD = SDK / "cmake_out/velavision_k7cloud_link_attempt5_20260913"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log, timeout, cwd=None, env=None):
    with log.open("wb") as output:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    return completed.returncode


def main():
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    for relative, expected in inputs.items():
        actual = sha256(PROJECT / relative)
        if actual != expected:
            raise RuntimeError(f"input hash changed: {relative}: {actual}")

    if BUILD.exists():
        raise RuntimeError(f"refusing to reuse build directory: {BUILD}")

    environment = dict(os.environ)
    toolchain = SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin"
    kconfig_tools = SDK / "prebuilts/tools/python/bin"
    build_tools = SDK / "prebuilts/build-tools/linux-x86_64/bin"
    environment["PATH"] = os.pathsep.join(
        [str(toolchain), str(kconfig_tools), str(build_tools), environment.get("PATH", "")]
    )
    kconfiglib = SDK / "prebuilts/tools/python/dist-packages/kconfiglib"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(kconfiglib), environment.get("PYTHONPATH", "")]
    )

    configure = [
        "cmake", "-S", "nuttx", "-B", str(BUILD), "-G", "Ninja",
        "-DBOARD_CONFIG=kickpi_k7:velavision_cloud_probe_local",
    ]
    configure_exit = run(configure, HERE / "configure.log", 600, SDK, environment)
    if configure_exit:
        raise RuntimeError("configure failed")

    build_command = ["cmake", "--build", str(BUILD), "-j4"]
    build_exit = run(build_command, HERE / "build.log", 2400, SDK, environment)

    config_text = (BUILD / ".config").read_text(encoding="utf-8")
    required_config = [
        "CONFIG_LIBC_NETDB=y",
        "CONFIG_NETDB_DNSCLIENT=y",
        "CONFIG_NETDB_DNSSERVER_NOADDR=y",
        "CONFIG_CRYPTO_MBEDTLS=y",
        "CONFIG_EXAMPLES_K7CLOUD=y",
    ]
    missing_config = [item for item in required_config if item not in config_text]

    symbols = {}
    if build_exit == 0:
        nm = subprocess.run(
            [str(toolchain / "aarch64-none-elf-nm"), "-g", str(BUILD / "nuttx")],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout
        for symbol in (
            "k7cloud_main", "vv_dns_resolve_ipv4", "vv_dns_nuttx_backend_init",
            "vv_https_perform", "vv_https_mbedtls_create",
        ):
            symbols[symbol] = any(line.rstrip().endswith(" " + symbol) for line in nm.splitlines())

    result = {
        "scope": "compile/link only; no DNS, socket, TLS, credential or board operation",
        "inputs": inputs,
        "configure_command": configure,
        "configure_exit_code": configure_exit,
        "build_command": build_command,
        "build_exit_code": build_exit,
        "required_config": {item: item not in missing_config for item in required_config},
        "strong_symbols": symbols,
        "board_tested": False,
        "network_accessed": False,
        "credentials_used": False,
        "flash_written": False,
    }
    if build_exit == 0:
        result["artifacts"] = {
            name: {"bytes": (BUILD / name).stat().st_size, "sha256": sha256(BUILD / name)}
            for name in ("nuttx", "nuttx.bin", ".config")
        }

    (HERE / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    if build_exit or missing_config or not all(symbols.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
