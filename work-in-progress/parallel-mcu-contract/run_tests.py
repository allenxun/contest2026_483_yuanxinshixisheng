"""Offline bounded test runner; writes only beside itself. Never accesses devices."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EVIDENCE = HERE / ('evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
EVIDENCE.mkdir()
paths = ['README.md', 'project-manifest.json', 'docs/代码日志对应表.md',
         'app/gimbal/README.md', 'app/gimbal/gimbal_link.c', 'app/gimbal/gimbal_link.h',
         'app/gimbal/gimbal_main.c', 'app/k7host/k7_pipeline.c', 'app/k7host/k7host_main.c',
         'host/vision/photo_controller.py', 'mcu/stm32-v1.3/firmware/BSP/bsp_usart.c',
         'mcu/stm32-v1.3/firmware/BSP/bsp_servo.c', 'mcu/stm32-v1.3/firmware/BSP/bsp.c',
         'mcu/stm32-v1.3/firmware/USER/main.c', 'mcu/stm32-v1.3/firmware/USER/control.c',
         'mcu/stm32-v1.3/firmware/USER/pid.c', 'mcu/stm32-v1.3/firmware/USER/pid.h']
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
inputs = {p: {'absolute_path': str(ROOT/p), 'sha256': digest(ROOT/p)} for p in paths}
(EVIDENCE/'inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding='utf-8')

def extract(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1; end = begin+1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]

# Exact function body from current frozen source, no production file edits.
source = (ROOT/'app/gimbal/gimbal_link.c').read_text()
pack = extract(source, 'int gimbal_link_pack(')
oracle = '#include <stdint.h>\n#include <errno.h>\n#include <stdio.h>\nstatic int fail(int e){return -e;}\n' + pack + '''
int main(void) {
  uint8_t data[14]; int v[4][2]={{10,-10},{-800,-200},{800,1030},{0,0}};
  for(int j=0;j<4;j++){if(gimbal_link_pack(data,v[j][0],v[j][1]))return 1;
    for(int i=0;i<14;i++){printf("%02x",data[i]);} puts("");}
  if(gimbal_link_pack(data,801,0)!=-EINVAL)return 2;
  if(gimbal_link_pack(data,0,1031)!=-EINVAL)return 3;
  return 0;
}
'''
(EVIDENCE/'pack_oracle.c').write_text(oracle)
results=[]
def run(name, command):
    result = subprocess.run(command, cwd=HERE, capture_output=True, timeout=60)
    (EVIDENCE/(name+'.stdout.raw')).write_bytes(result.stdout)
    (EVIDENCE/(name+'.stderr.raw')).write_bytes(result.stderr)
    results.append(dict(name=name, command=[str(c) for c in command], exit_code=result.returncode))
    return result

build=run('build', [r'D:\software\mingw64\mingw64\bin\gcc.exe', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(EVIDENCE/'pack_oracle.c'), '-o', str(EVIDENCE/'pack_oracle.exe')])
if build.returncode == 0:
    oracle_result=run('oracle', [str(EVIDENCE/'pack_oracle.exe')])
    from contract import encode_pair
    expected=''.join(encode_pair(x,y).hex()+'\n' for x,y in [(10,-10),(-800,-200),(800,1030),(0,0)])
    parity = oracle_result.returncode == 0 and oracle_result.stdout.decode().replace('\r\n','\n') == expected
else: parity=False
unit=run('unittest', [sys.executable, '-B', '-m', 'unittest', '-v', 'test_contract'])
changed=[p for p in paths if digest(ROOT/p) != inputs[p]['sha256']]
summary=dict(commands=results, c_source_pack_parity=parity, changed_inputs=changed,
             passed=build.returncode==0 and parity and unit.returncode==0 and not changed,
             scope='offline Windows host only; no hardware, ACK, CAN or actuator validation')
(EVIDENCE/'result.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(dict(evidence=str(EVIDENCE), **summary), indent=2))
sys.exit(0 if summary['passed'] else 1)
