import hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parent.parent
base=PROJECT/'work-in-progress/parallel-llama-b0'
inputs=[PROJECT/'README.md',PROJECT/'project-manifest.json',PROJECT/'docs/代码日志对应表.md',PROJECT.parent/'AGENTS.md',base/'DEPENDENCIES.md',base/'VERSION.json']
v=base/'vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
inputs += [v/'src/llama-mmap.cpp',v/'src/llama-mmap.h']
def row(p):
    b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(ROOT/'evidence/input-hashes.json').write_text(json.dumps([row(p) for p in inputs],ensure_ascii=False,indent=2),encoding='utf-8')
files=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery.json']
(ROOT/'delivery.json').write_text(json.dumps({'status':'host-tested candidate; not integrated; not NuttX tested','model_commit':'74d4f5b041ad837153b0e90fc864b8290e01d8d5','hardware_tested':False,'weights_downloaded':False,'files':[dict(row(p),path=str(p.relative_to(ROOT))) for p in sorted(files)]},ensure_ascii=False,indent=2),encoding='utf-8')
