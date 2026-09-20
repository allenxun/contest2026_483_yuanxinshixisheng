from pathlib import Path
import shutil
import hashlib
import json
import re

root = Path(__file__).resolve().parent
base = root.parent / 'mcu-rct6'
dst = root / 'firmware'
assert not dst.exists(), 'Variant already exists; refuse overwrite'
shutil.copytree(str(base / 'firmware'), str(dst),
                ignore=shutil.ignore_patterns('OBJ', 'Listings', '*.uvguix.*'))
old = (dst / 'BSP/bsp_servo.c').read_bytes()
block = re.search(rb'ServTypdef Xserv\s*=\s*\{.*?\};', old, re.S).group(0)
newblock = block.replace(b'.pwm = 712', b'.pwm = 1492')
newblock = re.sub(rb'\.MIDPWM = 712[^\r\n]*',
                  b'.MIDPWM = 1492 /* Midpoint of selected X endpoints: (2452 + 532) / 2. */', newblock)
assert newblock != block
(dst / 'BSP/bsp_servo.c').write_bytes(old.replace(block, newblock, 1))
p = dst / 'USER/main.c'
assert b'float version = 1.2;' in p.read_bytes()
p.write_bytes(p.read_bytes().replace(b'float version = 1.2;', b'float version = 1.3;'))
changed = []
manifest = {}
for p in sorted(dst.rglob('*')):
    if not p.is_file():
        continue
    rel = p.relative_to(dst).as_posix()
    b = base / 'firmware' / rel
    manifest[rel] = hashlib.sha256(b.read_bytes()).hexdigest()
    if p.read_bytes() != b.read_bytes():
        changed.append(rel)
assert changed == ['BSP/bsp_servo.c', 'USER/main.c'], changed
(root / 'baseline-v1.2-sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

# Keep the existing actual-function/parser tests and add the recenter regression.
t = (base / 'test_variant.py').read_text(encoding='utf-8')
t = t.replace('{712,2500,500,712}', '{1492,2500,500,1492}').replace('cx=712', 'cx=1492')
t = t.replace('cx==676', 'cx==1456').replace('cx==748', 'cx==1528').replace('cx==712', 'cx==1492')
t = t.replace('    puts("PASS: ring', '''    Servo_ApplyLegacy(-800,0); assert(cx==2452 && cy==700);
    Servo_ApplyLegacy(800,0); assert(cx==532 && cy==700);
    Servo_ApplyLegacy(0,0); assert(cx==1492 && cy==700);
    for(i=-32768;i<=32767;i++) {
        int expected_y = 700 + i*15/10;
        if(expected_y<500) expected_y=500;
        if(expected_y>2300) expected_y=2300;
        Servo_ApplyLegacy(0,(int16_t)i);
        assert(cx==1492 && cy==expected_y);
    }
    puts("PASS: X midpoint and symmetric endpoints; all 65536 Y commands unchanged.");
    puts("PASS: ring''')
(root / 'test_variant.py').write_text(t, encoding='utf-8')
print('Created v1.3: only X initial/MID pulse and version changed; Y source unchanged.')
