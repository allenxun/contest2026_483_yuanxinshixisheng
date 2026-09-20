"""Record only completed C++ and wireless observations for this RAM image."""
import json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]; E=R/'evidence/cxx-unwind-20260910'
runtime=json.loads((E/'runtime.json').read_text())
assert runtime['passed']
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
ble=[json.loads(x) for x in (E/'ble-wireless.jsonl').read_text().splitlines()]
assert any(x['event']=='hold_pass' and x['seconds']==30 for x in ble)
gateway=json.loads((E/'gateway.json').read_text())
assert any('5 packets transmitted, 5 received, 0% packet loss' in l for row in gateway['records'] for l in row['lines'])
state=dict(running_revision=E.name,boot='RAM',smp_cpus=8,
 firmware_sha256='369a710d03ce2407a0cffe56f3042cd3884e195c11bf0cd33075ad84ec03c7d2',
 cxx_runtime_probe_passed=True,off_t_bits=32,pointer_bits=64,
 concurrent_exception_tested=False,model_loaded=False,agent_deployed=False,
 wifi_connected=True,ip='10.3.0.214',gateway_ping='5/5',
 ble_service_running=True,ble_connected=False,ble_disconnect='test client intentionally disconnected',
 wireless_hold_seconds=30,amsdu_rejected=0,emmc_written=False,emmc_reregistered_this_boot=False,
 evidence_directory=E.relative_to(R).as_posix(),
 limits=['Single main-thread exception before worker creation; no concurrent exception acceptance',
         'No large-file, NEON workload, model or long-term wireless test on this revision'])
p=E/'acceptance.json'; assert not p.exists(); p.write_text(json.dumps(state,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text())
m['updated_at']=datetime.now(timezone.utc).isoformat()
m['current_device']=state;m['last_verified_device']=state.copy()
m['pending_firmware']=dict(revision='neon-file64-20260910',state='independent build; not loaded')
m['agent_plan']['next']='64-bit file offsets, SIMD gate, native llama CPU core and bounded model storage'
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text();a=s.index('**当前板端运行');b=s.index('\n\n',a)
s=s[:a]+'**当前板端运行 `cxx-unwind-20260910` 八核无线/C++候选（RAM）。** 静态构造、主线程异常捕获与RAII、对齐分配、std::thread/条件变量探针真机通过；Wi-Fi真实配网IP10.3.0.214、BLE30秒保持及网关5/5通过，客户端主动断开。当前off_t仍32位，模型未加载；并发异常未验收。下一份neon-file64独立候选尚未上板。证据 `evidence/cxx-unwind-20260910/acceptance.json`。此前smp-load的四A72整数负载与A-MSDU异常仍属原版本历史，不能迁用为当前长稳结论。'+s[b:]
p.write_text(s,encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n\n2026-09-10 原生Agent基础增量：app/k7cxx、K7异常表及首构造注册修复，经cxx-unwind独立构建/ELF检查与真机探针通过；无线真配网/BLE30秒/网关5/5。第一轮TLS_TASK缺失编译失败、第二轮异常表缺失取消加载及无线恢复失败均保留。app/k7agent/model_reader与app/k7neon为已迁入待验收候选，模型与Agent未部署。证据evidence/cxx-unwind-20260910/acceptance.json；日志归属当前主会话，子代理独立记录未宣称完整单独入库。\n')
print('Recorded exact C++ RAM acceptance and preserved prior failures')
