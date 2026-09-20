"""Record existing auth hardware evidence, separately from pending IP work."""
from pathlib import Path
import json
from datetime import datetime,timezone
r=Path(__file__).resolve().parents[1]
evidence='evidence/wifi-auth-20260909/lansee-auth-01.jsonl'
assert 'authentication completed=1 ret=0 installed=05 IP_acquired=0' in (r/evidence).read_text()
intro='**当前板端已完成真实 WPA2 密码认证：** `wifi-auth-20260909` 在 RAM 运行，Lansee 四次握手及 PTK/GTK 安装返回成功；测试随后主动断开，尚未获取 IP。手机 X → 真实扫描列表已由用户确认。原生数据通道和 DHCP 正在独立 `wifi-ip-20260909` 中开发，前端仍为 `connect:false`。见 [认证与 IP 接入记录](docs/WiFi认证与IP接入_20260909.md)。\n\n以下为历史阶段记录，以顶部最新状态为准。\n\n'
p=r/'README.md';s=p.read_text(encoding='utf-8')
if intro not in s:s=s.replace('## 当前统一版本\n\n','## 当前统一版本\n\n'+intro)
p.write_text(s,encoding='utf-8')
p=r/'docs/代码日志对应表.md';s=p.read_text(encoding='utf-8')
entry='2026-09-09 最新无线进展：原生 Lansee WPA2 四次握手通过，证据 `evidence/wifi-auth-20260909/lansee-auth-01.jsonl`；运行固件及源码对应 `evidence/build/wifi-auth-20260909/verification.json`。IP/DHCP 为后续独立开发，不计作联网通过。对应当前主会话，日志归属不变。详见 [认证与 IP 接入](WiFi认证与IP接入_20260909.md)。\n\n'
if entry not in s:s=s.replace('# 代码、日志与验证对应表\n\n','# 代码、日志与验证对应表\n\n'+entry)
p.write_text(s,encoding='utf-8')
p=r/'project-manifest.json';v=json.loads(p.read_text(encoding='utf-8'))
v['latest_wireless_checkpoint']=dict(updated_at=datetime.now(timezone.utc).isoformat(),running_revision='wifi-auth-20260909',boot='RAM',wpa2_hardware_passed=True,ip_acquired=False,test_disconnected=True,evidence=evidence,pending_revision='wifi-ip-20260909',frontend_connect=False,emmc_written=False)
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
