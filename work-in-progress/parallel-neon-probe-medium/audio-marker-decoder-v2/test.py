import pathlib,importlib.util,json,hashlib
from decode import parse,decode
p=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_v1',str(p/'input/decode.py'))
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
raw=(p/'input/k7sound-loopback-rxall-20260910-213805.bin').read_bytes()
base=raw.replace(b'\r\r\n',b'\n').replace(b'\r\n',b'\n')
expected=[0]*8+[0x0707ef00,0x08081100,0,0,0,0,0,0]*31
old_actual=old.parse(raw)[1];assert old_actual==expected
try:old.parse(base.replace(b'\n',b'\r\r\n'));old_double=True
except ValueError:old_double=False
assert not old_double
tested=[]
for name,sep in [('LF',b'\n'),('CRLF',b'\r\n'),('CRCRLF',b'\r\r\n')]:
 data=base.replace(b'\n',sep)
 assert parse(data)[1]==expected
 tested.append(name)
 # Test genuine missing/truncated PCM data, not just missing final newline.
 start=data.index(b'LOOP_PCM 00f8')
 for bad in [data[:start],data[:start]+b'LOOP_PCM 00f8 0707ef00',
             data.replace(b'LOOP_PCM 0008',b'LOOP_PCM 0000',1),
             data.replace(b'LOOP_PCM 0008',b'LOOP_PCM 0010',1),
             data.replace(b'LOOP_PCM 0008 0707ef00',b'LOOP_PCM 0008 0707ef0',1)]:
  try:parse(bad);raise AssertionError('invalid dump accepted')
  except ValueError:pass
assert parse(raw)[1].count(0)==194
result=dict(raw_sha256=hashlib.sha256(raw).hexdigest(),raw_crcrlf=raw.count(b'\r\r\n'),
 raw_crlf=raw.count(b'\r\n'),v1_real_raw_accepted=True,v1_synthetic_double_cr_accepted=old_double,
 v2_complete_formats=tested,words=256,zero_words=194,
 malformed_tests_per_format=5,word_values_unchanged=True,
 note='Original fixed marker values intentionally are not numbered-v1 encodings; only parse checked.')
(p/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
print('PASS complete LF/CRLF/CRCRLF; truncated/duplicate/gap/partial-word rejection; original raw retained')
