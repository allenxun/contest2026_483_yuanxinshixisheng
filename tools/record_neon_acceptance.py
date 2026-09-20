"""Record the recovered image's finite runtime and wireless evidence."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/neon-file64-20260910'
runtime=json.loads((E/'runtime.json').read_text());neon=json.loads((E/'neon.json').read_text())
assert runtime['passed'] and runtime['off_t_bits']==64 and neon['passed']
progress=(E/'ramload-resume-progress.txt').read_text(encoding='utf-8-sig')
assert 'PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED' in progress and 'PASS: REAL K7 NSH' in progress
ble=[json.loads(x) for x in (E/'ble-wireless.jsonl').read_text().splitlines()]
assert any(x['event']=='hold_pass' and x['seconds']==30 for x in ble)
assert ble[-1]['event']=='test_client_disconnected'
gateway=json.loads((E/'gateway.json').read_text())
lines=[line for row in gateway['records'] for line in row['lines']]
assert any('5 packets transmitted, 5 received, 0% packet loss' in line for line in lines)
assert any('AMSDU complete=1 subframes=2 rejected=1' in line for line in lines)
state=dict(running_revision=E.name,boot='RAM',smp_cpus=8,
 firmware_sha256='7fa95ddfeeee2de9d832cbf7cf10a440c5fef158b0a11811deeee6b885cc2b75',
 cxx_runtime_probe_passed=True,off_t_bits=64,pointer_bits=64,neon_probe_passed=True,
 neon_scope=neon['scope'],concurrent_exception_tested=False,model_loaded=False,agent_deployed=False,
 wifi_connected=True,ip='10.3.0.214',gateway_ping='5/5',ble_service_running=True,
 ble_connected=False,ble_disconnect='test client intentionally disconnected',wireless_hold_seconds=30,
 amsdu_rejected=1,strict_zero_receive_anomalies=False,emmc_written=False,serial_port_present=True,
 evidence_directory=E.relative_to(R).as_posix(),
 limits=['off_t width verified; actual ordinary model file IO untested',
         'Only CPU4/5 D8-D15 low64, not full SIMD or concurrent C++ unwind',
         'A-MSDU rejected=1 before gateway test, unchanged after; cause unknown',
         'No long-term, internet, model inference or locale-runtime board acceptance'])
proof=dict(state=state,recorded_utc=datetime.now(timezone.utc).isoformat(),
 hashes={name:hashlib.sha256((E/name).read_bytes()).hexdigest() for name in
         ['ramload-resume-progress.txt','runtime.json','neon.json','ble-wireless.jsonl','gateway.json']})
with (E/'acceptance.json').open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
m['current_device']=state;m['last_verified_device']=state.copy();m['updated_at']=proof['recorded_utc']
m['pending_firmware']=dict(revision='cxx-locale-20260910',compiled=True,hardware_tested=False,
 native_llama_compile='39/39 objects',native_llama_link=True,
 next='Review ELF reservation above current 6MiB loader limit; integrate bounded zero-weight graph probe')
m['agent_plan']['next']='Native llama link/layout and checked pool gate; then bounded model storage/integrity'
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text(encoding='utf-8');a=s.index('**当前板端运行');b=s.index('\n\n',a)
s=s[:a]+('**当前板端运行 `neon-file64-20260910`（RAM），串口中断后已恢复并校验启动。** '
 '八核服务亲和性、基础C++、off_t64与CPU4/5短时NEON诊断通过；真实Wi-Fi配网IP10.3.0.214、BLE30秒和网关5/5通过，测试客户端主动断开。'
 'A-MSDU累计拒收1，不能宣称严格零异常或长稳。证据 `evidence/neon-file64-20260910/acceptance.json`。'
 '另已完成llama的39个ARM64/NuttX对象编译和独立链接；尚未集成启动，模型/Agent未部署。')+s[b:]
p.write_text(s,encoding='utf-8')
print('Recorded recovered runtime, explicit receive anomaly, and separate native link gate')
