"""Test and package the scan-only frontend handoff, without board operations."""
import hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT/'frontend'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    node=shutil.which('node')
    if not node:raise RuntimeError('Node.js is required')
    proc=subprocess.run([node,'--test','test-vela-provision.mjs'],cwd=FRONT,
       capture_output=True,text=True,encoding='utf-8')
    (FRONT/'evidence/frontend-scan-handoff-20260909.txt').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    if proc.returncode:raise SystemExit(proc.returncode)
    required=['vela-provision.mjs','接入示例.mjs','test-vela-provision.mjs']
    assert all((FRONT/n).is_file() for n in required)
    files=[dict(path=p.relative_to(FRONT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
       for p in sorted(FRONT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json']
    (FRONT/'SHA256SUMS.json').write_text(json.dumps(dict(
       scope='Scan-only frontend handoff; Wi-Fi authentication/DHCP not implemented',files=files),
       ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    out=ROOT/'deliveries/前端扫描联调包_20260909.zip';out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(FRONT.rglob('*')):
            if p.is_file():z.write(p,'frontend/'+p.relative_to(FRONT).as_posix())
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert all('frontend/'+n in z.namelist() for n in required)
        for item in files:
            assert hashlib.sha256(z.read('frontend/'+item['path'])).hexdigest()==item['sha256']
    report=dict(archive=str(out.relative_to(ROOT)),sha256=sha(out),required_examples=required,
       node_exit_code=proc.returncode,archive_verified=True,hardware_tested_this_run=False,
       wifi_connect_supported=False)
    (ROOT/'evidence/frontend-handoff-package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(proc.stdout);print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
