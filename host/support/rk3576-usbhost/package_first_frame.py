from pathlib import Path
import hashlib,json,zipfile,subprocess
r=Path('/home/swl/openvela');w=r/'work/rk3576-usbhost';b=r/'cmake_out/rk3576_uvc_v13'
image_hash='f51ae873c65447ff82b18aeed6e30999602545daf5f667e6eb95a0da6a5756a5'
frame_hash='b2399bf373b52efb71e079f7659a7cba365b3010980da044e851da860b7a202c'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(b/'nuttx.bin')==image_hash
assert sha(w/'k7-first-frame-v13.jpg')==frame_hash
assert (w/'decode-v13.stderr').stat().st_size==0
assert json.loads((w/'decode-v13.json').read_text())['shape']==[480,640,3]
assert 'JPEG_candidates=1 retained=33676' in (w/'uvc-snapshot-v13.log').read_text()
assert 'K7_FRAME_READY' in (w/'final-ready-v13.log').read_text()
with zipfile.ZipFile(w/'K7-usbenum-experimental-20260904.zip') as old:
    sources={n.removeprefix('source/') for n in old.namelist() if n.startswith('source/') and not n.endswith('/')}
for folder in ['nuttx/arch/arm64/include/rk3576','nuttx/arch/arm64/src/rk3576','nuttx/boards/arm64/rk3576','apps/examples/gimbal','apps/examples/k7usb','apps/examples/k7host']:
    sources.update(str(p.relative_to(r)) for p in (r/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
sources.update(['nuttx/arch/arm64/Kconfig','nuttx/arch/arm64/src/common/arm64_head.S','nuttx/boards/Kconfig','nuttx/drivers/serial/uart_16550.c'])
source_hashes={name:sha(r/name) for name in sorted(sources)}
manifest={'board':'KICKPI-K7/RK3576','checkpoint':'uvc-first-frame-v13','image_sha256':image_hash,
 'frame_sha256':frame_hash,'frame_bytes':33676,'frame_dimensions':[640,480],'frame_export_identical_reads':2,
 'frame_decoder':'OpenCV 4.10.0/libjpeg','decoder_stderr_bytes':0,'visual_check':'PASS: no corrupted image bands',
 'camera':'32e6:9221','port':'USB3.0-1','negotiated_usb_speed_mbps':480,
 'video':'MJPEG','requested_frame_interval_100ns':333333,'continuous_fps_measured':False,
 'requires_uboot_usb_start':False,'initialization_tests':'Repeated software reboots; true power-off cold boot pending',
 'boot':'RAM only, existing vendor DDR/ATF/U-Boot; no eMMC writes',
 'snapshot_limit':'One attempt per boot; up to four batches, each 2048 HS isoch packets',
 'unimplemented':['continuous frame delivery','safe hot unplug and endpoint teardown','in-OS JPEG decoding/inference','NPU runtime','automatic vision-to-gimbal loop','persistent eMMC boot'],
 'nuttx_base':subprocess.check_output(['git','-C',str(r/'nuttx'),'rev-parse','HEAD'],text=True).strip(),
 'source_scope':'Current K7 additions and changed common source files; requires matching complete openvela source tree',
 'source_sha256':source_hashes}
(w/'checkpoint-v13.json').write_text(json.dumps(manifest,indent=2))
evidence=['build-v13.log','provenance.json','host-start-v8.log','host-start-v9.log','host-start-v13.log','uvc-probe-v13.log','uvc-snapshot-v13.log','uart-ramboot-v13.stdout','reboot-for-v13.stdout','gimbal-v13.log','final-ready-v13.log','export-frame-v13.log','k7-first-frame-v13.json','decode-v13.json','decode-v13.stderr']
target=w/'K7-openvela-USB-first-frame-v13-20260904.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in ['nuttx','nuttx.bin','.config','System.map']:z.write(b/name,'firmware/'+name)
    for name in sorted(sources):z.write(r/name,'source/'+name)
    for name in evidence:z.write(w/name,'evidence/'+name)
    for name in ['combo-mode-v8.patch','uvc-probe-v9.patch','uvc-control-v10.patch','uvc-packets-v11.patch','uvc-batch-v12.patch','uvc-warmup-v13.patch']:
        z.write(w/name,'evidence/patch-history/'+name)
    for name in ['uart_ramboot.py','probe_with_recovery.py','export_nsh_frame.py']:
        z.write(w/name,'tools/'+name)
    for name in ['verify_image.py','uboot_commands.py','capture_boot.py']:
        z.write(r/'work/rk3576-bringup'/name,'tools/'+name)
    z.write(w/'k7-first-frame-v13.jpg','capture/k7-first-frame.jpg')
    z.write(w/'checkpoint-v13.json','manifest.json')
    z.write(w/'K7-openvela-摄像头首帧验证说明.md','README.md')
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('firmware/nuttx.bin')).hexdigest()==image_hash
    assert hashlib.sha256(z.read('capture/k7-first-frame.jpg')).hexdigest()==frame_hash
    for name,digest in source_hashes.items():assert hashlib.sha256(z.read('source/'+name)).hexdigest()==digest
print(json.dumps({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target),'source_files':len(sources)},indent=2))
