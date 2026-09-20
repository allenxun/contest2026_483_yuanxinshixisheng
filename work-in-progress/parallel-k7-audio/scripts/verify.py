from pathlib import Path
import json,hashlib,datetime,subprocess,sys,difflib,re
R=Path(__file__).resolve().parents[1]
e=R/'evidence'/('run-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));e.mkdir()
args=[sys.executable,'-X','utf8','-m','unittest','-v','test_candidate']
p=subprocess.run(args,cwd=R,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
(e/'stdout.raw').write_bytes(p.stdout);(e/'stderr.raw').write_bytes(p.stderr)
(e/'result.json').write_text(json.dumps(dict(command=args,exit=p.returncode,timeout=False,scope='pure host mock and format arithmetic; no hardware'),indent=2),encoding='utf8')
print(p.stderr.decode('utf8'));assert p.returncode==0
project=R.parents[1]
paths=['artifacts/model-arena-20260910/.config','port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.c','port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.h','port/tracked/nuttx/drivers/usbhost/Kconfig','port/new/nuttx/arch/arm64/src/rk3576/Kconfig','docs/VoiceLink接入评估_20260910.md']
rows=[]
for path in paths:
 src=project/path;data=src.read_bytes();out=R/'sources/project'/path
 if out.exists() and out.read_bytes()!=data:out=e/'project-input'/path
 out.parent.mkdir(parents=True,exist_ok=True)
 if not out.exists():out.write_bytes(data)
 rows.append(dict(source=str(src),copy=str(out.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
(e/'project-inputs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
diff=[]
for page in [16,17,20,32,33]:
 old=R/'sources'/f'K7_V1.1_20241211_SCH-p{page:02}.txt';new=R/'sources'/f'K7_V2.0_20250716_SCH-p{page:02}.txt'
 diff.extend(difflib.unified_diff(old.read_text(encoding='utf8').splitlines(True),new.read_text(encoding='utf8').splitlines(True),fromfile=old.name,tofile=new.name))
(e/'schematic-text.diff').write_text(''.join(diff),encoding='utf8')
# Preserve reference writes verbatim for review; NOT an executable init recipe.
codec=R/'sources/kernel-6.1/sound/soc/codecs/es8323.c'
lines=codec.read_text(encoding='utf8').splitlines()
reference=[]
for i,line in enumerate(lines,1):
 if (98<=i<=102 or 760<=i<=835) and ('snd_soc_component_write' in line or 'usleep_range' in line):
  reference.append(dict(line=i,source=line.strip()))
(e/'codec-reference-only.json').write_text(json.dumps(dict(source=str(codec.relative_to(R)),executable=False,note='probe writes often ignore I/O errors; mute callback is a no-op; capture route not yet validated',statements=reference),indent=2),encoding='utf8')
print('EVIDENCE='+str(e))
