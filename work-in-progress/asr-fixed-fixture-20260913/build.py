"""Build the bounded multi-turn voice provisioning image and a separate RK3576 RAM image."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela")
ASR_PRIOR = Path("/home/swl/openvela/work/native-asr-recognizer")
TLS_PRIOR = Path("/home/swl/openvela/work/native-emutls-fix")
BUILD = SDK / "cmake_out/velavision_asr_fixed_fixture_20260913"
GENERATED = SDK / "cmake_out/velavision_voice_tls_20260911"
STALE_GENERATED = "/dev/shm/velavision_audio_sound_20260910"
SHERPA_HEADER_ROOT = Path("/home/swl/openvela/work/native-vits-lexicon-20260911/sherpa")
SHERPA_C_API_SHA256 = "e286ded904e93b670ad229d88151dfade58671fc2740a0afb11b0372f3595100"
SUPPORT = PROJECT / "work-in-progress/voice-rule-provision-20260912/support"
SUPPORT_HASHES = {
    "add_probe.o": "ffa27d89dfd6c62aea709a1f01d2c93384a95f399072f15612761c7c92185354",
    "legacychars.h": "68abfad867f517a18804b15bd5bfe8fd03c8401b6f5727a7248a0e78d86c8fbe",
    "lib_iconv.c": "a841584dbfcba8f0f149852882dac654ed82a7de681dbf49687fcf64854b9814",
    "libk7_locale.a": "c7c3e30d92e59d8c88389e5f083f9acd45d3cb5b67b8c0fa6c7c8de5709fa60c",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log, timeout, cwd=None, env=None):
    with log.open("wb") as output:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    return result.returncode


def main():
    expected = json.loads((HERE / "inputs.json").read_text(encoding="utf-8-sig"))
    for relative, digest in expected.items():
        path = PROJECT / relative
        if sha(path) != digest:
            raise RuntimeError("input hash changed: " + relative)
    if BUILD.exists():
        raise RuntimeError("refusing to reuse build directory: " + str(BUILD))
    for name, digest in SUPPORT_HASHES.items():
        path = SUPPORT / name
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError("support input is missing or changed: " + name)

    compile_base = json.loads(
        (ASR_PRIOR / "compile-attempt2.json").read_text(encoding="utf-8-sig")
    )["command"]
    required_generated = [
        GENERATED / "apps/include",
        GENERATED / "include/nuttx/config.h",
        GENERATED / "include/arch/types.h",
        GENERATED / "include/libcxx",
        GENERATED / "include/libcxx_config",
        GENERATED / "include/libcxxabi",
    ]
    missing_generated = [str(path) for path in required_generated if not path.exists()]
    if missing_generated:
        raise RuntimeError("missing retained generated inputs: " + ", ".join(missing_generated))
    compile_base = [
        item.replace(STALE_GENERATED, str(GENERATED)) for item in compile_base
    ]
    sherpa_c_api = SHERPA_HEADER_ROOT / "sherpa-onnx/c-api/c-api.h"
    if not sherpa_c_api.is_file() or sha(sherpa_c_api) != SHERPA_C_API_SHA256:
        raise RuntimeError("locked Sherpa C API header is missing or changed")
    compile_base += ["-I" + str(SHERPA_HEADER_ROOT)]
    objects = []
    compile_records = []
    sources = [
        PROJECT / "app/voicelink/src/native_asr_runtime.cpp",
        PROJECT / "app/voicelink/src/native_tls_selftest.cpp",
        TLS_PRIOR / "emutls.c",
    ]
    for source in sources:
        obj = HERE / (source.name + ".o")
        command = list(compile_base)
        command[command.index("-c") + 1] = str(source)
        command[command.index("-o") + 1] = str(obj)
        command += ["-I" + str(ASR_PRIOR)]
        if source.suffix == ".c":
            command = [x for x in command if not x.startswith("-std=") and x != "-nostdinc++"]
            command[0] = command[0].replace("-g++", "-gcc")
        exit_code = run(command, HERE / (source.name + ".log"), 180)
        compile_records.append({"source": str(source), "command": command, "exit_code": exit_code})
        if exit_code:
            raise RuntimeError("compile failed: " + source.name)
        objects.append(obj)

    iconv_object = HERE / "iconv.o"
    iconv_archive = HERE / "libk7_iconv.a"
    iconv_compile = [
        str(SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-gcc"),
        "-D__NuttX__",
        "-I" + str(SDK / "apps/include"),
        "-I" + str(GENERATED / "apps/include"),
        "-I" + str(SUPPORT),
        "-isystem", str(SDK / "nuttx/include"),
        "-isystem", str(GENERATED / "include"),
        "-march=armv8-a", "-mcpu=cortex-a53", "-Os",
        "-fno-strict-aliasing", "-fno-omit-frame-pointer", "-D_LDBL_EQ_DBL",
        "-fno-common", "-Wall", "-Wshadow", "-Wundef", "-Wno-attributes",
        "-Wno-unknown-pragmas", "-Werror", "-Wstrict-prototypes", "-Wno-psabi",
        "-ffunction-sections", "-fdata-sections", "-DCONFIG_ALLOW_MIT_COMPONENTS=1",
        "-c", str(SUPPORT / "lib_iconv.c"), "-o", str(iconv_object),
    ]
    if run(iconv_compile, HERE / "iconv-compile.log", 180):
        raise RuntimeError("iconv support compile failed")
    iconv_archive_command = [
        str(SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-ar"),
        "rcs", str(iconv_archive), str(iconv_object),
    ]
    if run(iconv_archive_command, HERE / "iconv-archive.log", 60):
        raise RuntimeError("iconv support archive failed")

    prior_link = json.loads(
        (ASR_PRIOR / "link2/result.json").read_text(encoding="utf-8-sig")
    )["link_command"]
    runtime = HERE / "runtime.o"
    link = list(prior_link)
    link[link.index("-o") + 1] = str(runtime)
    replacements = {
        str(ASR_PRIOR / "link2/recognizer_probe.cpp.o"): str(objects[0]),
        "/dev/shm/velavision-native-asr-add-probe-20260911/add_probe.o":
            str(SUPPORT / "add_probe.o"),
        "/dev/shm/velavision-ort-session-20260911/config-attempt9/libk7_iconv.a":
            str(iconv_archive),
        "/dev/shm/velavision-ort-session-20260911/support-attempt1/libk7_locale.a":
            str(SUPPORT / "libk7_locale.a"),
    }
    for old in replacements:
        if link.count(old) != 1:
            raise RuntimeError("expected exactly one locked link input: " + old)
    link = [replacements.get(item, item) for item in link]
    link += [str(objects[1]), str(objects[2])]
    link_exit = run(link, HERE / "link.log", 300)
    if link_exit:
        raise RuntimeError("relocatable runtime link failed")
    runtime_hash = sha(runtime)

    configure = [
        "cmake", "-S", "nuttx", "-B", str(BUILD), "-G", "Ninja",
        "-DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local",
        "-DK7VOICE_NATIVE_ORT_ADD=ON",
        "-DK7VOICE_NATIVE_ASR_MODEL=ON",
        "-DK7VOICE_NATIVE_ASR_MIC=ON",
        "-DK7VOICE_ORT_OBJECT=" + str(runtime),
        "-DK7VOICE_ORT_OBJECT_SHA256=" + runtime_hash,
    ]
    environment = dict(os.environ)
    toolchain = str(SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin")
    kconfig_tools = str(SDK / "prebuilts/tools/python/bin")
    build_tools = str(SDK / "prebuilts/build-tools/linux-x86_64/bin")
    environment["PATH"] = (
        toolchain + os.pathsep + kconfig_tools + os.pathsep + build_tools
        + os.pathsep + environment.get("PATH", "")
    )
    python_packages = str(SDK / "prebuilts/tools/python/dist-packages/kconfiglib")
    environment["PYTHONPATH"] = python_packages + os.pathsep + environment.get("PYTHONPATH", "")
    configure_exit = run(configure, HERE / "configure.log", 600, SDK, environment)
    if configure_exit:
        raise RuntimeError("firmware configure failed")
    build_command = ["cmake", "--build", str(BUILD), "-j4"]
    build_exit = run(build_command, HERE / "build.log", 2400, SDK, environment)

    result = {
        "runtime_sha256": runtime_hash,
        "compile": compile_records,
        "support_inputs": SUPPORT_HASHES,
        "iconv_compile_command": iconv_compile,
        "iconv_archive_command": iconv_archive_command,
        "link_command": link,
        "link_exit_code": link_exit,
        "configure_command": configure,
        "configure_exit_code": configure_exit,
        "build_command": build_command,
        "build_exit_code": build_exit,
        "inputs": expected,
        "board_tested": False,
    }
    if build_exit == 0:
        result["artifacts"] = {
            name: {
                "bytes": (BUILD / name).stat().st_size,
                "sha256": sha(BUILD / name),
            }
            for name in ("nuttx", "nuttx.bin", ".config")
        }
    (HERE / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8-sig"
    )
    print(json.dumps(result, indent=2), flush=True)
    if build_exit:
        raise SystemExit(build_exit)


if __name__ == "__main__":
    main()


