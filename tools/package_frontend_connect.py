"""Produce a small, unambiguous frontend handoff; no credentials or old demos."""
import hashlib,json,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];F=R/'frontend'
names=['vela-provision.mjs','完整配网接入示例.mjs','真实联网联调说明_20260909.md']
manifest={n:hashlib.sha256((F/n).read_bytes()).hexdigest() for n in names}
out=R/'deliveries/前端真实联网联调_20260909.zip';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for n in names:z.write(F/n,n)
 z.writestr('SHA256SUMS.json',json.dumps(manifest,ensure_ascii=False,indent=2))
 z.writestr('先读我.txt','新版真实联网：调用 connectWifi({ssid_b64,password})，不要用 submitCredentials() 或旧接入示例。\n先订阅 Notify，读取 connect:true/encrypted:true，按 LF 组包，匹配 id/session；只在 wifi_connected 和真实 IP 到达后显示已连接。\n详情见真实联网联调说明_20260909.md。\n')
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for n,d in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==d
print(out)
