"""Read selected exact official SDK Git blobs; no checkout or SDK execution."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[1]
S = R.parent/'无线适配_2026-09-08/official-linux-20260320'
E = R/'evidence/audio-sdk-extra-20260910'
E.mkdir(exist_ok=True)
wanted = {'kernel-6.1/'+p for p in (
    'drivers/i2c/busses/i2c-rk3x.c', 'drivers/pinctrl/pinctrl-rockchip.h',
    'drivers/pinctrl/pinctrl-rockchip.c', 'drivers/clk/rockchip/clk-rk3576.c',
    'include/dt-bindings/clock/rockchip,rk3576-cru.h',
    'include/dt-bindings/power/rk3576-power.h')}
items = [x for x in json.loads((S/'tree.json').read_text()) if x['path'] in wanted]
assert len(items) == len(wanted)
env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='NUL')
for item in items:
    assert item['type'] == 'blob' and item['mode'] == '100644' and item['size'] < 1024*1024
    data = subprocess.check_output(['git', '--no-replace-objects', '--git-dir='+str(S/'object-store'),
                                    'cat-file', 'blob', item['oid']], env=env, timeout=30)
    assert len(data) == item['size']
    assert hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest() == item['oid']
    target = E/item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f: f.write(data)
    item['sha256'] = hashlib.sha256(data).hexdigest()
with (E/'inputs.json').open('x') as f:
    json.dump(dict(source=str(S/'object-store'), tree_sha256=hashlib.sha256((S/'tree.json').read_bytes()).hexdigest(),
                   files=items), f, indent=2)
print('Exact SDK audio/I2C/clock reference blobs captured:', len(items))
