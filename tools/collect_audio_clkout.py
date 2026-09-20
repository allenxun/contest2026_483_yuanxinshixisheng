"""Freeze the exact official RK3576 external audio-clock gate provider."""
import hashlib,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
S=R.parent/'无线适配_2026-09-08/official-linux-20260320'
name='kernel-6.1/drivers/clk/rockchip/clk-out.c'
item=next(x for x in json.loads((S/'tree.json').read_text()) if x['path']==name)
assert item['type']=='blob' and item['mode']=='100644' and item['size']<100000
data=subprocess.check_output(['git','--no-replace-objects','--git-dir='+str(S/'object-store'),
 'cat-file','blob',item['oid']],env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='NUL'),timeout=30)
assert len(data)==item['size'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['oid']
E=R/'evidence/audio-clkout-reference-20260910';p=E/name;p.parent.mkdir(parents=True,exist_ok=True)
with p.open('xb') as f:f.write(data)
with (E/'input.json').open('x') as f:json.dump(item|{'sha256':hashlib.sha256(data).hexdigest()},f,indent=2)
print(str(p))
