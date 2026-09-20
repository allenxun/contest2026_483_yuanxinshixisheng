"""Load the hash-pinned cloud candidate to RAM and start BLE provisioning."""
from cloud_radio_stage_audit import remote, ROOT

CODE = r'''
import importlib.util,pathlib,hashlib,zlib,json,os,subprocess,sys,time
p=pathlib.Path('/home/swl/openvela/work/velavision-project')
spec=importlib.util.spec_from_file_location('radio',p/'work-in-progress/asr-direct-cache-20260914/radio_refresh.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
out=p/'evidence/board-speech-bridge-20260914';out.mkdir(exist_ok=True)
fw=pathlib.Path('/home/swl/openvela/cmake_out/velavision_board_speech_bridge_20260914/nuttx.bin').read_bytes()
assert len(fw)==2787024 and hashlib.sha256(fw).hexdigest()=='a41b79abeba09972c1197c6833dc04146f7992e72063c351f8c1df7ab17563a7'
buf=bytearray(0x1000000+len(fw));segments=[]
for name,off,target,size,sha in r.INPUTS:
 data=(r.RADIO_DIR/name).read_bytes()
 assert len(data)==size and hashlib.sha256(data).hexdigest()==sha
 buf[off:off+size]=data;segments.append((off,target,data))
buf[0x1000000:]=fw;segments.append((0x1000000,0x40400000,fw))
payload=out/'ram.bin';payload.write_bytes(buf)
sha=hashlib.sha256(buf).hexdigest()
env=os.environ.copy();env['PYTHONPATH']=str(r.USB_DEPS)
subprocess.run([sys.executable,str(r.DOWNLOADER),str(payload),'--sha256',sha,'--vid','0x18d1','--pid','0x4d00','--serial',r.USB_SERIAL,'--audited-running-buffer','0x40c00800:0x07000000','--result',str(out/'usb.json')],env=env,check=True)
with r.open_port() as s:
 s.write(b'\x03');s.flush();r.read_to_prompt(s,5)
 r.check_crc(s,r.DOWNLOAD_BASE,len(buf),'%08x'%(zlib.crc32(buf)&0xffffffff))
 for off,target,data in segments:
  r.copy_chunks(s,r.DOWNLOAD_BASE+off,target,len(data));r.check_crc(s,target,len(data),'%08x'%(zlib.crc32(data)&0xffffffff))
 assert b'edfe0dd0' in r.command(s,'md.l 48300000 1').lower()
 def nsh(cmd,timeout):
  for c in cmd.encode()+b'\r':s.write(bytes([c]));s.flush();time.sleep(.004)
  b=bytearray();end=time.monotonic()+timeout
  while time.monotonic()<end:
   b.extend(s.read(8192))
   if b'nsh>' in b: break
  else:
   s.write(b'\r');s.flush();time.sleep(1);b.extend(s.read(8192))
   if b'nsh>' not in b:
    (out/'startup-timeout.log').write_bytes(b)
    raise RuntimeError('NSH timeout: '+cmd)
  (out/(cmd.split()[0]+'-'+str(time.time_ns())+'.log')).write_bytes(b)
  print(b.decode(errors='replace'),flush=True);time.sleep(.8);return b
 nsh('booti 40400000 - 48300000',40)
 for cmd,timeout in [('k7radio sdio-boot',45),('k7radio bt-host',40),('k7radio wifi-service-start',40),('k7radio provision-status',10)]:
  result=nsh(cmd,timeout)
  if b'command not found' in result or b'Usage:' in result: raise RuntimeError('Rejected '+cmd)
(out/'result.json').write_text(json.dumps({'ram_boot':True,'firmware_sha256':hashlib.sha256(fw).hexdigest(),'emmc_written':False,'app_provisioning_tested':False}))
'''

if __name__ == '__main__':
    out=ROOT/'evidence/board-speech-bridge-20260914'
    out.mkdir(exist_ok=True)
    result=remote(CODE)
    (out/'startup.log').write_bytes(result)
    print(result.decode(errors='replace'))
