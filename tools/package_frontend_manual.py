"""Create a minimal, self-contained frontend operating handoff."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FRONT=ROOT/'frontend'
files={name:FRONT/name for name in ('前端蓝牙联调操作手册.md','手机调试器操作卡.md','手机调试HEX分包.txt','vela-provision.mjs','接入示例.mjs','test-vela-provision.mjs')}
files['credentials-real-board-20260909.jsonl']=FRONT/'evidence/credentials-real-board-20260909.jsonl'
checks={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
out=ROOT/'deliveries/前端蓝牙操作资料_20260909.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name,path in files.items():z.write(path,name)
    z.writestr('SHA256SUMS.json',json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    for name,digest in checks.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
print(json.dumps(dict(archive=str(out),files=list(files),verified=True),ensure_ascii=False))
