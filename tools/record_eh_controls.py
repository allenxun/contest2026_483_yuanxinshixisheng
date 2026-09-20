"""Record exact control outcomes and separate restored graph wireless baseline."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/eh-control-20260910';Q=E/'recovery'
rows={m:json.loads((E/m/'runtime.json').read_text()) for m in ['single','warm1']}
assert all(r['passed'] for r in rows.values())
ble=[json.loads(x) for x in (Q/'ble-wireless.jsonl').read_text().splitlines()]
assert ble[-1]['event']=='test_client_disconnected' and any(x['event']=='hold_pass' for x in ble)
assert 'PASS: REAL K7 NSH' in (Q/'ramload-progress.txt').read_text(encoding='utf-8-sig')
lines=[s for r in json.loads((Q/'gateway.json').read_text())['records'] for s in r['lines']]
assert any('5 packets transmitted, 5 received' in s for s in lines)
proof=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),control_firmware_sha256='bc1ec4b367e5eb46f3f629ef69658aae316cbb938f0eb4627b22d39f9cecdf29',
 modes=rows,cold_two_worker_prior_passed=False,general_thread_safety_proven=False,
 interpretation='Single first throw and fully preheated dual workers pass; narrows focus to first shared initialization, not exact branch proof',
 hashes={str(p.relative_to(E)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [E/'single/runtime.bin',E/'warm1/runtime.bin',E/'ramload-progress.txt',E/'warm1-ramload-progress.txt',Q/'ramload-progress.txt',Q/'ble-wireless.jsonl',Q/'gateway.json']})
with (E/'acceptance.json').open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
state=json.loads((R/'evidence/graph-core-20260910/acceptance.json').read_text())['state']
state.update(evidence_directory='evidence/eh-control-20260910/recovery',receive_rejects_before=0,receive_rejects_after=0,
 recovery_after='single/warm1 EH controls; graph workload not redundantly rerun')
m['current_device']=state;m['last_verified_device']=state.copy();m['updated_at']=proof['recorded_utc']
m['pending_firmware']=dict(revision='arena-provider-20260910',compiled=False,hardware_tested=False,next='Remove unnecessary unchecked multi-buffer realloc path before target compile')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'docs/C++异常对照与CPU图进展_20260910.md'
text='''# C++异常对照与CPU图进展

真实ggml CPU零权重图已过；完整模型未加载。graph-core镜像SHA256 6b68dbff8afcd866f8d6e806885f209bd71dcf6e8cd8379b3bd40d768d8ea27b，2/4配置线程各4096项正确，正常回收；不把软件线程数等同于实际四核分布。

异常控制镜像SHA256 bc1ec4b367e5eb46f3f629ef69658aae316cbb938f0eb4627b22d39f9cecdf29，两模式分别完整CRC校验后新启动，先前未运行其他异常探针。

| 对照 | 实测结果 | 结论边界 |
|---|---|---|
| 旧cold双worker | 无worker结果/正常joined，uw_init_context_1附近abort | 保留失败，不能从任务消失认定正常清理 |
| single CPU5首次一次 | caught=1, cleaned=3, joined=1，真实CPU5 | 该三层链在单worker可用 |
| warm1主线程完整预热后CPU4/5 | PREHEAT_PASS先于worker；各caught=1, cleaned=3，joined=2 | 受控预热样本通过，非通用线程安全 |

warm1的两个one_throw测量区间重叠；这不是逐指令展开阶段同时执行的证明。精确libgcc机器码中FDE列表搬移和寄存器尺寸表先写哨兵都有无同步窗口；现场缺分支/状态，尚未锁定触发路径。仅FindFDE预热不覆盖全部窗口，完整预热也没有证明所有后续共享写入安全。

额外取得官方GCC13.4六份源码作参考，URL和SHA在evidence/gcc-unwind-reference-20260910/sources.json；上游版本源码不是当前SDK精确构建来源证明。后续应补正确的once/mutex运行库支持或明确受控执行边界，不改写失败结论。

控制结束后，已从保留快照恢复graph-core固件。八核服务亲和性、真实BLE配网/IP10.3.0.214、30秒保持、网关5/5通过。此次接收拒绝0→0，历史1次及冷异常仍保留。测试客户端主动断开，Wi-Fi在线，蓝牙服务保留；后续切换见project-manifest。未写eMMC/STM32、未启动云台。

下一项是独立最多1MiB的模型池tensor读写，不重复384MiB稀疏旧测试。审查发现原候选即便单buffer也会进入上游未判空realloc；改成固定单buffer显式分配后再构建，避免把已知失败路径带入目标诊断。模型权重、KV/scratch/output及普通文件仍需逐项接入。

证据：evidence/eh-control-20260910/acceptance.json；原始串口及恢复结果位于同目录。独立输出审核器的target-results.json位于work-in-progress/parallel-cxx-unwind-medium/eh-control-output-v1，主机解析不能代替原始目标执行。
'''
with p.open('x',encoding='utf-8') as f:f.write(text)
print('Both controls and graph wireless recovery recorded')
