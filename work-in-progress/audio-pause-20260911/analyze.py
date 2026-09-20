from pathlib import Path
import re,json,hashlib
r=Path('E:/openvela/VelaVision/work-in-progress/audio-pause-20260911');p=r/'pause-20260911-191526.log';data=p.read_bytes();s=data.decode(errors='replace')
m=re.search(r'pause250 start=(\d+) end=(\d+) before=([0-9a-f]+) after=([0-9a-f]+)',s);assert m
assert 'SOUND pio=0 frames=128' in s and 'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in s
raw=int(m[4],16);fields=[(raw>>(6*i))&63 for i in range(4)];assert fields==[2,2,2,2]
report={'firmware_sha256':'d802b88da7c984ea4e69b05d2f9a37c6bb22cd9441100aaa100ee586e7a81582','raw_log':p.name,'log_sha256':hashlib.sha256(data).hexdigest(),'pause_us':int(m[2])-int(m[1]),'fifo_before':m[3],'fifo_after':m[4],'fifo_counts_after':fields,'capture_and_cleanup_passed':True,'interpretation':'Multiple FIFO banks accumulated data without RXDR reads; excludes simple read-only advancement hypothesis','audio_fixed':False,'voice_wifi_passed':False,'serial_log_missing_some_later_lines':True}
(r/'board-result.json').write_text(json.dumps(report,indent=2));print(report)
