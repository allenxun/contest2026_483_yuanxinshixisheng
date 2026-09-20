import pathlib,json,hashlib,difflib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
patch=''
for n in ['codec_duplex.c','codec_duplex.h']:
 a=(R/('input-'+n)).read_text();b=(R/n).read_text()
 patch+=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/'+n,tofile='b/'+n))
(R/'adc-modes.patch').write_text(patch)
paths=[R/'input-codec_duplex.c',R/'input-codec_duplex.h',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.c']
(R/'fixed-inputs.json').write_text(json.dumps([dict(path=str(p),sha256=sha(p)) for p in paths],indent=2)+'\n')
files=[dict(path=p.relative_to(R).as_posix(),sha256=sha(p)) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json']
(R/'delivery.json').write_text(json.dumps({'scope':'Explicit independently reset ADC comparison modes; host mock tests, no device','files':files},indent=2)+'\n')
for e in files:assert sha(R/e['path'])==e['sha256']
print('delivery',sha(R/'delivery.json'),'source',sha(R/'codec_duplex.c'))
