"""Record finite board graph/wireless evidence without promoting model claims."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/graph-core-20260910'
def read(name):return json.loads((E/name).read_text())
assert read('runtime.json')['passed'] and read('affinity-boot.json')['passed']
progress=(E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert 'PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED' in progress and 'PASS: REAL K7 NSH' in progress
ble=[json.loads(x) for x in (E/'ble-wireless.jsonl').read_text().splitlines()]
assert any(x['event']=='hold_pass' and x['seconds']==30 for x in ble)
assert ble[-1]['event']=='test_client_disconnected'
lines=[s for r in read('gateway.json')['records'] for s in r['lines']]
assert any('5 packets transmitted, 5 received, 0% packet loss' in s for s in lines)
state=dict(running_revision=E.name,boot='RAM',smp_cpus=8,
 firmware_sha256='6b68dbff8afcd866f8d6e806885f209bd71dcf6e8cd8379b3bd40d768d8ea27b',
 ggml_graph_passed=True,graph_configured_threads=[2,4],graph_checked_per_run=4096,
 graph_mismatches=0,graph_physical_cpus_observed=False,model_loaded=False,agent_deployed=False,
 concurrent_cxx_cold_passed=False,wifi_connected=True,ip='10.3.0.214',gateway_ping='5/5',
 ble_service_running=True,ble_connected=False,ble_disconnect='Test client intentionally disconnected',
 wireless_hold_seconds=30,receive_rejects_before=1,receive_rejects_after=1,
 emmc_written=False,serial_port_present=True,evidence_directory=E.relative_to(R).as_posix(),
 limits=['No weights or natural language inference', 'Configured graph workers do not prove physical CPU placement',
 'C++ first concurrent throw failed in separate cxx-eh image; unresolved',
 'Historical AMSDU rejected label covers all RX rejects; cause not established',
 'Finite wireless regression only; no long-term or internet acceptance'])
proof=dict(state=state,recorded_utc=datetime.now(timezone.utc).isoformat(),
 hashes={n:hashlib.sha256((E/n).read_bytes()).hexdigest() for n in ['ramload-progress.txt','runtime.json','affinity-boot.json','ble-wireless.jsonl','gateway.json']})
with (E/'acceptance.json').open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
m['current_device']=state;m['last_verified_device']=state.copy();m['updated_at']=proof['recorded_utc']
m['pending_firmware']=dict(revision='eh-control-20260910',compiled=True,hardware_tested=False,next='Separate fresh boots: single CPU5 cold then fully preheated CPU4/5 warm1')
m['agent_plan']['next']='Resolve concurrent exception first initialization; scoped model arena buft and immutable file path'
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text(encoding='utf-8');a=s.index('**当前板端运行');b=s.index('\n\n',a)
s=s[:a]+('**当前已验收 `graph-core-20260910`（RAM）的真实 ggml 图计算。** 2/4线程两组各4096项全部正确，资源正常回收；未加载权重，不代表模型推理或物理四核利用。BLE真实配网/IP、30秒保持和网关5/5通过；测试客户端主动断开。接收拒绝计数1→1，历史异常保留。另一个cxx-eh镜像首次双线程异常探针失败，正在用独立控制固件定位，不能宣称C++并发异常已修复。最新运行/加载状态以project-manifest为准。')+s[b:]
p.write_text(s,encoding='utf-8')
print('Graph and finite wireless acceptance recorded; exception failure retained')
