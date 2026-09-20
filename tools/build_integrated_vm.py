"""Create a separate compile-only combined config; never flash or start devices."""
import hashlib, json, re, subprocess
from pathlib import Path
SDK = Path('/home/swl/openvela')
OUT = SDK / 'work/velavision-integration-20260909'
OUT.mkdir(parents=True, exist_ok=True)
board = SDK / 'nuttx/boards/arm64/rk3576/kickpi_k7/configs/velavision_integrated_local'
build = SDK / 'cmake_out/velavision_integrated_20260909'
base = SDK / 'cmake_out/rk3576_radiohost_sdio_build/.config'
enabled = ['CONFIG_EXAMPLES_GIMBAL', 'CONFIG_EXAMPLES_K7HOST', 'CONFIG_EXAMPLES_K7HOST_JPEG',
           'CONFIG_EXAMPLES_K7HOST_YUNET', 'CONFIG_EXAMPLES_K7HOST_TRACK', 'CONFIG_RK3576_NPU_DIAG',
           'CONFIG_EXAMPLES_K7NPU', 'CONFIG_K7NPU_MMU_TEST', 'CONFIG_K7NPU_RAW_TEST']
text = base.read_text()
for name in enabled:
    text = re.sub(r'^(?:' + name + r'=.*|# ' + name + r' is not set)\n?', '', text, flags=re.M)
text += '\n# VelaVision integrated diagnostic build; no auto-start.\n' + '\n'.join(n+'=y' for n in enabled)+'\n'
# Both BT TX queues hold 16 messages; reserve their total plus eight for other users.
text = re.sub(r'^CONFIG_PREALLOC_MQ_MSGS=.*$', 'CONFIG_PREALLOC_MQ_MSGS=40', text, flags=re.M)
board.mkdir(parents=True, exist_ok=True)
(board/'defconfig').write_text(text)
if (build/'.config').exists():
    current = (build/'.config').read_text()
    (build/'.config').write_text(re.sub(r'^CONFIG_PREALLOC_MQ_MSGS=.*$', 'CONFIG_PREALLOC_MQ_MSGS=40', current, flags=re.M))
if (OUT/'integrated-build.log').exists():
    count = len(list(OUT.glob('integrated-build-attempt-*.log'))) + 1
    (OUT/f'integrated-build-attempt-{count}.log').write_bytes((OUT/'integrated-build.log').read_bytes())
cmd = ('source build/envsetup.sh >/dev/null && '
       'cmake -S nuttx -B cmake_out/velavision_integrated_20260909 -G Ninja '
       '-DBOARD_CONFIG=kickpi_k7:velavision_integrated_local '
       '&& cmake --build cmake_out/velavision_integrated_20260909 -j6')
with (OUT/'integrated-build.log').open('w') as log:
    proc = subprocess.run(['bash', '-c', cmd], cwd=SDK, stdout=log, stderr=subprocess.STDOUT)
report = dict(command=cmd, exit_code=proc.returncode, build_directory=str(build), device_started=False,
              hardware_tested=False, emmc_written=False, profile='combined diagnostic; RAW NPU remains explicit-command-only')
if proc.returncode == 0:
    config = (build/'.config').read_text()
    required = enabled + ['CONFIG_EXAMPLES_K7RADIO', 'CONFIG_WIRELESS_BLUETOOTH_HOST', 'CONFIG_RK3576_USBHOST']
    report['required_config'] = {n: bool(re.search('^'+n+'=y$', config, re.M)) for n in required}
    assert all(report['required_config'].values()), report['required_config']
    report['files'] = {n: dict(bytes=(build/n).stat().st_size, sha256=hashlib.sha256((build/n).read_bytes()).hexdigest())
                       for n in ('.config', 'nuttx', 'nuttx.bin')}
    nm = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm'
    symbols = subprocess.check_output([str(nm), str(build/'nuttx')], text=True)
    report['linked_application_symbols'] = {n: bool(re.search(r'\b'+n+r'$', symbols, re.M))
                                          for n in ('k7host_main', 'gimbal_main', 'k7npu_main', 'k7radio_main')}
    assert all(report['linked_application_symbols'].values())
(OUT/'integrated-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(proc.returncode)
