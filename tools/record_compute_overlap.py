"""Merge real overlap timestamps and report remaining RX anomalies explicitly."""
import hashlib, json, re
from pathlib import Path
from datetime import datetime, timezone
R=Path(__file__).resolve().parents[1];E=R/'evidence/smp-load-20260910'
compute=json.loads((E/'compute-radio-attempt02.json').read_text())
assert compute['passed']
ble=[json.loads(x) for x in (E/'ble-overlap-attempt02.jsonl').read_text().splitlines()]
assert any(x['event']=='hold_pass' for x in ble)
rows=compute['records']
start=next(x['wall_time'] for x in rows if x['line'].startswith('LOAD start '))
end=next(x['wall_time'] for x in rows if x['line'].startswith('LOAD result=PASS '))
overlap=[x for x in ble if x['event']=='periodic_status_pass' and start<=x['wall_time']<=end]
assert len(overlap)>=10
ping=[x for x in rows if x['line'].startswith('56 bytes from ') and start<=x['wall_time']<=end]
assert len(ping)>=40
def rejected(name):
    d=json.loads((E/name).read_text())
    lines=[x for r in d['records'] for x in r['lines']]
    return int(re.findall(r'rejected=(\d+)', '\n'.join(lines))[-1])
before=rejected('after-coordinator-failure.json');after=rejected('after-compute-status.json')
state=dict(running_revision=E.name,boot='RAM',smp_cpus=8,
    firmware_sha256=hashlib.sha256((R/'artifacts'/E.name/'nuttx.bin').read_bytes()).hexdigest(),
    wifi_connected=True,ip='10.3.0.214',ble_service_running=True,ble_connected=False,
    ble_disconnect='Test client intentionally disconnected after monitored hold',
    default_service_affinity='0x1',compute_cpus=[4,5,6,7],compute_seconds_per_cpu=60,
    compute_batches=1412766,compute_errors=0,gateway_ping='45/45',
    gateway_replies_in_compute_interval=len(ping),ble_responses_in_compute_interval=len(overlap),
    ble_response_ms_in_compute=dict(min=min(x['response_ms'] for x in overlap),max=max(x['response_ms'] for x in overlap)),
    compute_and_ble_ping_subtests_passed=True,strict_zero_rx_anomaly_passed=False,
    amsdu_rejected_before=before,amsdu_rejected_after=after,amsdu_rejected_delta_between_snapshots=after-before,
    rx_anomaly_cause='Unknown; snapshots also cover time outside compute, no causal attribution to A72 load',
    emmc_written=False,emmc_reregistered_this_boot=False,
    evidence_directory=E.relative_to(R).as_posix(),
    limits=['Synthetic burst workload, not full CPU saturation or real LLM/ASR',
            'No long-term, internet, Android/iOS, audio or whole-system acceptance',
            'First coordinator attempt did not launch compute; background-prompt anchor failed and evidence retained'])
p=E/'acceptance.json';assert not p.exists();p.write_text(json.dumps(state,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text());m['updated_at']=datetime.now(timezone.utc).isoformat()
m['current_device']=state;m['last_verified_device']=state.copy();m['pending_firmware']=None
m['smp_diagnostics']['compute_radio_overlap']='evidence/smp-load-20260910/acceptance.json'
m['agent_plan']=dict(preferred='native openvela CPU llama.cpp with rules and validated tools',deployed=False,
    document='docs/离线Agent选型与B0落地方案_20260910.md',next='C++/file/allocator B0 gates')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text();a=s.index('**当前板端');b=s.index('\n\n',a)
s=s[:a]+'**当前板端运行 `smp-load-20260910` 八核无线候选（RAM）。** 四颗A72各60秒计算、1412766批校验零错误；计算时间内有'+str(len(overlap))+'次BLE状态回包及'+str(len(ping))+'次网关回复，整轮ping45/45。Wi-Fi在线，BLE测试客户端主动断开。两次快照之间A-MSDU拒收从'+str(before)+'增至'+str(after)+'，原因待查，因此严格零接收异常尚未通过，不宣称正式长稳。见 `evidence/smp-load-20260910/acceptance.json`。'+s[b:]
s=s.replace('- **Agent：**尚未部署，模型方案和正式设备工具接口待定。','- **Agent：**主线选择原生openvela CPU llama.cpp＋规则兜底与工具校验，Qwen2.5-0.5B-Instruct Q4_K_M为候选；C++运行库、模型文件与allocator尚待接入，未部署。见 `docs/离线Agent选型与B0落地方案_20260910.md`。')
p.write_text(s,encoding='utf-8')
for name in ['A72计算与无线并发验收_20260910.md','代码日志对应表.md']:
    with (R/'docs'/name).open('a',encoding='utf-8') as f:
        f.write('\n\n实际增量：smp-load-20260910 RAM运行，四A72各60秒、1412766批零计算错误，ping45/45；时间重叠核对BLE回包'+str(len(overlap))+'次、网关回复'+str(len(ping))+'次。A-MSDU快照'+str(before)+'→'+str(after)+'，不满足严格零接收异常，不能归因为计算负载或宣布长稳。首轮后台提示符采集失败未启动计算；第二轮修正主机采集后一次完成，全部记录保留。详见 evidence/smp-load-20260910/acceptance.json。\n')
print(json.dumps(state))
