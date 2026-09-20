import hashlib, importlib.util, json, os, pathlib, subprocess, sys, time, zlib

PROJECT = pathlib.Path('/home/swl/openvela/work/velavision-project')
BUILD = pathlib.Path('/home/swl/openvela/cmake_out/velavision_photo_foreground_20260917')
SERIAL = 'f71a9d152132db55'
OUT = PROJECT / 'evidence/photo-foreground-20260918/wifi-fix-bg'
spec = importlib.util.spec_from_file_location('radio', PROJECT / 'work-in-progress/asr-direct-cache-20260914/radio_refresh.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
fw = (BUILD / 'nuttx.bin').read_bytes(); fw_sha = hashlib.sha256(fw).hexdigest()
buf = bytearray(0x1000000 + len(fw)); segments = []
for name, off, target, size, sha in r.INPUTS:
    data = (r.RADIO_DIR / name).read_bytes()
    assert len(data) == size and hashlib.sha256(data).hexdigest() == sha
    buf[off:off + size] = data; segments.append((off, target, data))
buf[0x1000000:] = fw; segments.append((0x1000000, 0x40400000, fw))
OUT.mkdir(parents=True, exist_ok=False); payload = OUT / 'ram.bin'; payload.write_bytes(buf)
sha = hashlib.sha256(buf).hexdigest(); env = os.environ.copy(); env['PYTHONPATH'] = str(r.USB_DEPS)
subprocess.run([sys.executable, str(r.DOWNLOADER), str(payload), '--sha256', sha, '--vid', '0x18d1', '--pid', '0x4d00', '--serial', SERIAL, '--audited-running-buffer', '0x40c00800:0x07000000', '--result', str(OUT / 'usb.json')], env=env, check=True)
with r.open_port() as s:
    s.write(b'\x03'); s.flush(); r.read_to_prompt(s, 5)
    r.check_crc(s, r.DOWNLOAD_BASE, len(buf), '%08x' % (zlib.crc32(buf) & 0xffffffff))
    for off, target, data in segments:
        r.copy_chunks(s, r.DOWNLOAD_BASE + off, target, len(data)); r.check_crc(s, target, len(data), '%08x' % (zlib.crc32(data) & 0xffffffff))
    def nsh(cmd, timeout):
        s.write(cmd.encode() + b'\r'); s.flush(); end = time.monotonic() + timeout; out = bytearray()
        while time.monotonic() < end:
            out.extend(s.read(8192))
            if b'nsh>' in out: break
        if b'nsh>' not in out: raise RuntimeError('NSH timeout: ' + cmd)
        (OUT / (cmd.split()[0] + '.log')).write_bytes(out); print(out.decode(errors='replace'), flush=True); return out
    nsh('booti 40400000 - 48300000', 45)
    nsh('k7radio sdio-boot &', 5)
    time.sleep(8)
    for cmd, timeout in [('k7radio host-status', 10), ('k7radio bt-host', 40), ('k7radio wifi-service-start', 40), ('k7radio provision-status', 10)]: nsh(cmd, timeout)
(OUT / 'result.json').write_text(json.dumps({'firmware_sha256': fw_sha, 'ram_sha256': sha, 'bytes': len(fw), 'emmc_written': False}, indent=2))
