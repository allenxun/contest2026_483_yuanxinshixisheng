from pathlib import Path
import hashlib, json, zipfile
root=Path('/home/swl/openvela')
work=root/'work/rk3576-usbhost'
build=root/'cmake_out/rk3576_usbenum_v7'
expected='6be693f9f3126961e9192027e09506e46dcf7608c85355128daea8f0e0fa34bd'
assert hashlib.sha256((build/'nuttx.bin').read_bytes()).hexdigest()==expected
assert 'K7 CAMERA ENUMERATED: 32e6:9221' in (work/'final-enumeration.log').read_text()
manifest={'board':'KICKPI-K7/RK3576', 'version':'usbenum-v7', 'image_sha256':expected,
 'hardware_verified':['RAM CRC and real NSH boot','USB2 root port 480Mbps','4-port Hub address 1','camera 32e6:9221 address 2, 613-byte configuration','software reboot'],
 'required_precondition':'U-Boot usb start, halt controllers, then RAM boot openvela',
 'not_verified_or_implemented':['independent USB initialization without U-Boot usb start','UVC streaming/frame capture','NPU runtime'],
 'data_cache_enabled':True, 'flashed_to_emmc':False,
 'source_scope':'Incremental sources; requires the existing K7 BSP and matching openvela tree',
 'runtime_log':'evidence/final-enumeration.log'}
(work/'checkpoint-v7.json').write_text(json.dumps(manifest,indent=2))
with zipfile.ZipFile(work/'K7-usbenum-experimental-20260904.zip') as old:
    source={name for name in old.namelist() if name.startswith('source/') and not name.endswith('/')}
source.add('source/nuttx/drivers/serial/uart_16550.c')
evidence=['build-v7.log','verify-v7.json','provenance.json','host-start-v3.log','host-start-v4.log','host-start-v5.log','host-start-v7.log','host-start-v7-preinit.log','final-enumeration.log','final-ramboot-retry.stdout','camera-v7-preinit.log','gimbal-v7-preinit.log','reboot-v4.log','uboot-host-baseline.log','uboot-host-registers.log','uboot-dma-prerequisites.log','uboot-platform-before.json','uboot-platform-after.json','uboot-platform-diff.json']
target=work/'K7-openvela-camera-enumeration-v7-20260904.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in ['nuttx','nuttx.bin','.config','System.map']:z.write(build/name,'firmware/'+name)
    for name in sorted(source):
        p=root/name.removeprefix('source/')
        assert p.is_file(),p
        z.write(p,name)
    for name in evidence:z.write(work/name,'evidence/'+name)
    for p in sorted(work.glob('*.patch')):z.write(p,'evidence/history/'+p.name)
    for name in ['uart_ramboot.py','probe_with_recovery.py','compare_uboot_usb.py']:
        z.write(work/name,'tools/'+name)
    for name in ['verify_image.py','uboot_commands.py','capture_boot.py']:
        z.write(root/'work/rk3576-bringup'/name,'tools/'+name)
    z.write(work/'checkpoint-v7.json','manifest.json')
    z.write(work/'K7-USB摄像头枚举验证说明.md','README.md')
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('firmware/nuttx.bin')).hexdigest()==expected
print(json.dumps({'path':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_files':len(source)},indent=2))
