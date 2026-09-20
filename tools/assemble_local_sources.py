"""Import existing local deliverables, with source hashes, without changing originals."""
import hashlib, json, shutil, tarfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
copied = []
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def tree(src, dest):
    for p in sorted(src.rglob('*')):
        if not p.is_file() or any(x in ('.git', '__pycache__', 'node_modules') for x in p.relative_to(src).parts): continue
        out = dest / p.relative_to(src)
        if out.exists() and sha(out) != sha(p): raise RuntimeError('Refusing unknown overwrite: '+str(out))
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, out)
        copied.append(dict(source=str(p), path=out.relative_to(ROOT).as_posix(), sha256=sha(out)))
tree(WORK/'无线适配_2026-09-08/frontend', ROOT/'frontend')
tree(WORK/'无线适配_2026-09-08/wifi-link-port', ROOT/'work-in-progress/wifi-link')
tree(WORK/'交付包_RK3576三功能_V0.0.1_2026-09-07', ROOT/'legacy/pc-delivery')
tree(WORK/'参赛交付补充_2026-09-08/skills', ROOT/'skills')
mcu = ROOT/'mcu/stm32-v1.3'
with zipfile.ZipFile(WORK/'评审与接续_2026-09-08/06_STM32F103RCT6_v1.3_Xcenter.zip') as z:
    for info in z.infolist():
        if info.is_dir(): continue
        target = (mcu/info.filename).resolve()
        assert target.is_relative_to(mcu.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(info.filename))
        copied.append(dict(source='STM32-v1.3-archive:'+info.filename, path=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
comparisons=[]
with tarfile.open(WORK/'评审与接续_2026-09-08/05_最新工程与固件快照.tar.gz') as tar:
    for member in tar:
        if not member.isfile() or not member.name.startswith(('apps/examples/k7host/', 'apps/examples/gimbal/', 'apps/examples/k7npu/')): continue
        target=ROOT/'app'/member.name.removeprefix('apps/examples/')
        old=hashlib.sha256(tar.extractfile(member).read()).hexdigest()
        comparisons.append(dict(group='accepted-vision-gimbal-npu', source=member.name,path=target.relative_to(ROOT).as_posix(),
                                baseline_sha256=old,current_sha256=sha(target) if target.exists() else None,identical=target.exists() and sha(target)==old))
radio=json.loads((WORK/'无线适配_2026-09-08/candidate-id36/manifest.json').read_text(encoding='utf-8'))
for name, expected in radio.items():
    target=ROOT/('port/new/nuttx/arch/arm64/src/rk3576' if name=='rk3576_boot.c' else 'app/k7radio')/name
    comparisons.append(dict(group='accepted-radio-id36',source=name,path=target.relative_to(ROOT).as_posix(),
                            baseline_sha256=expected,current_sha256=sha(target),identical=sha(target)==expected))
(ROOT/'evidence/local-imports.json').write_text(json.dumps(copied,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROOT/'evidence/accepted-source-comparison.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(imported_files=len(copied), baseline_checks=len(comparisons),
                     identical=sum(x['identical'] for x in comparisons), different=[x['path'] for x in comparisons if not x['identical']]),ensure_ascii=False))
