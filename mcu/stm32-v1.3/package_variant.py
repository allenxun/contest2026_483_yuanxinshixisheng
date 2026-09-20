from pathlib import Path
import hashlib
import json
import difflib
import zipfile
import re

root = Path(__file__).resolve().parent
base = root.parent / 'mcu-rct6' / 'firmware'
manifest = json.loads((root/'baseline-v1.2-sha256.json').read_text(encoding='utf-8'))
changes = []
diff = []
for rel, digest in sorted(manifest.items()):
    old = (base/rel).read_bytes()
    new = (root/'firmware'/rel).read_bytes()
    assert hashlib.sha256(old).hexdigest() == digest, 'Baseline changed: '+rel
    if old == new:
        continue
    changes.append(rel)
    diff.extend(difflib.unified_diff(old.decode('latin1').splitlines(True),
                                    new.decode('latin1').splitlines(True),
                                    'v1.2/'+rel, 'v1.3/'+rel))
assert changes == ['BSP/bsp_servo.c', 'USER/main.c']
newservo = (root/'firmware/BSP/bsp_servo.c').read_bytes()
oldservo = (base/'BSP/bsp_servo.c').read_bytes()
pattern = rb'ServTypdef Yserv\s*=\s*\{.*?\};'
assert re.search(pattern,newservo,re.S).group() == re.search(pattern,oldservo,re.S).group()
assert b'.pwm = 1492' in newservo and b'.MIDPWM = 1492' in newservo
assert b'oc.TIM_Pulse = Xserv.MIDPWM;' in newservo
assert b'oc.TIM_Pulse = Yserv.MIDPWM;' in newservo
assert b'rec_step_p[1][2]= {0}' in (root/'firmware/USER/control.c').read_bytes()
assert b'0 Error(s), 56 Warning(s)' in (root/'keil-build.log').read_bytes()
(root/'changes-from-v1.2.patch').write_bytes(''.join(diff).encode('latin1'))
hashes = []
for ext in ('hex','bin'):
    p = root/'firmware/OBJ'/('stree_free_ii.'+ext)
    assert p.stat().st_size > 1000
    assert p.read_bytes() != (base/'OBJ'/p.name).read_bytes()
    hashes.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
(root/'release-sha256.txt').write_text('\n'.join(hashes)+'\n',encoding='ascii')
out = root.parents[1]/'outputs/STM32F103RCT6_VelaVision_v1.3_Xcenter.zip'
with zipfile.ZipFile(str(out),'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if 'Listings' in rel.parts or '__pycache__' in rel.parts:
            continue
        if 'OBJ' in rel.parts and p.suffix not in ('.hex','.bin'):
            continue
        if p.suffix in ('.exe','.pyc') or '.uvguix.' in p.name:
            continue
        z.write(str(p),rel.as_posix())
with zipfile.ZipFile(str(out)) as z:
    assert z.testzip() is None
    for name in ['firmware/OBJ/stree_free_ii.hex','firmware/USER/steer_freeII.uvprojx','README.md']:
        assert name in z.namelist()
print('PASS: v1.2 source hashes unchanged; only X configuration/version changed; Y identical.')
print('\n'.join(hashes))
print(str(out))
