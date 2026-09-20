"""Generate a stability report only from a completed, cross-checked test."""
import argparse,csv,hashlib,json,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();d=a.directory.resolve()
r=json.loads((d/'result.json').read_text(encoding='utf-8'))
events=[json.loads(x) for x in (d/'events.jsonl').read_text(encoding='utf-8').splitlines()]
rounds=[x for x in events if x['kind']=='round']
assert len(rounds)==r['rounds_completed']
assert sum(x['sent'] for x in rounds)==r['sent'] and sum(x['received'] for x in rounds)==r['received']
assert [x['round'] for x in rounds]==list(range(1,len(rounds)+1))
if r['passed']:
 assert r['elapsed_s']>=1800 and len(rounds)==30 and r['sent']==r['received']==1500 and not r['failures']
samples=[x['snapshot'] for x in events if x['kind'] in ('baseline','round','final_snapshot')]
with (d/'minute-metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['round','time_utc','sent','received','loss_percent','wifi_connected','ip','ble_connected','ble_encrypted','ble_connections','ble_disconnections','heap_free','heap_used','rx','tx','rx_rejected'])
 for x in rounds:
  s=x['snapshot'];w.writerow([x['round'],x['time'],x['sent'],x['received'],x['loss_percent'],s['wifi']['connected'],s['wifi']['ip'],s['ble']['connected'],s['ble']['encrypted'],s['ble']['connections'],s['ble']['disconnections'],s['memory']['free'],s['memory']['used'],s['wifi']['rx'],s['wifi']['tx'],s['wifi']['rx_rejected']])
mem=[s['memory']['free'] for s in samples]
ble_all=bool(samples) and all(s['ble']['connected']==1 and s['ble']['encrypted']==1 for s in samples)
completed_hold=r['elapsed_s']>=1800 and len(rounds)==30 and len(samples)==32 and r.get('final') is not None
ble_hold=bool(r['mode']=='wifi-ble' and completed_hold and ble_all and
 all(s['ble']['encrypt_status']==0 and s['ble']['connections']==samples[0]['ble']['connections'] and
     s['ble']['disconnections']==samples[0]['ble']['disconnections'] for s in samples) and
 not any(x.get('line','').startswith('RADIO BLE disconnected') for x in events))
wifi_hold=bool(completed_hold and all(s['wifi']['active']==1 and s['wifi']['connected']==1 and
 s['wifi']['result']==0 and s['wifi']['ip']==samples[0]['wifi']['ip'] for s in samples) and
 not any(x.get('line','').startswith('WIFI link lost') for x in events))
rtts=[]
for event in events:
 match=re.search(r'^\d+ bytes from 10\.3\.0\.1: icmp_seq=\d+ time=([\d.]+) ms$',event.get('line',''))
 if match:rtts.append(float(match[1]))
assert len(rtts)==r['received'],'Individual echo records do not match aggregate result'
latency=dict(min=min(rtts),mean=round(statistics.mean(rtts),3),max=max(rtts),p95=round(statistics.quantiles(rtts,n=100,method='inclusive')[94],3)) if len(rtts)>1 else None
summary=dict(result=r,heap_free_min=min(mem) if mem else None,heap_free_max=max(mem) if mem else None,heap_free_delta=(mem[-1]-mem[0]) if mem else None,all_sampled_ble_connected_encrypted=ble_all,evidence={name:hashlib.sha256((d/name).read_bytes()).hexdigest() for name in ('result.json','events.jsonl','minute-metrics.csv')},long_term_production_acceptance=False)
summary['latency_ms']=latency
summary['component_acceptance']=dict(ble_hold=ble_hold if r['mode']=='wifi-ble' else None,
 wifi_connection_hold=wifi_hold,zero_ping_loss=bool(completed_hold and r['sent']==r['received']==1500),
 scope='Separate connection-hold observations from strict combined zero-loss result; no application throughput acceptance')
(d/'verified-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
mode='Wi-Fi 独立长测（蓝牙仅观察）' if r['mode']=='wifi-only' else 'Wi-Fi / 手机 BLE 连接保持'
verdict='本轮通过' if r['passed'] else '本轮未通过/未完成，见失败明细'
body=f'''# 无线稳定性实测结果

**{verdict}。** 测试模式：{mode}。

| 项目 | 实际记录 |
|---|---|
| 固件 | `{r['revision']}`，RAM 运行 |
| 开始时间（UTC） | {r['started_at']} |
| 结束时间（UTC） | {r['finished_at']} |
| 实际计时 | {r['elapsed_s']} 秒，目标 1800 秒 |
| 完成周期 | {r['rounds_completed']}/30 |
| 网关探测 | 发送 {r['sent']}，收到 {r['received']} |
| 往返时间（毫秒） | `{json.dumps(latency,ensure_ascii=False)}` |
| 空闲堆内存 | 最小 {summary['heap_free_min']}，最大 {summary['heap_free_max']} 字节 |
| 起止空闲堆变化 | {summary['heap_free_delta']} 字节 |

蓝牙每次抽样均连接且加密：{ble_all}。Wi-Fi 独立模式的通过不代表蓝牙长时间保持通过。内存记录仅描述这一轮现象，不能据此排除所有泄漏。

独立观察结论：BLE 30 分钟保持为 {ble_hold if r['mode']=='wifi-ble' else '未覆盖'}；Wi-Fi 连接保持为 {wifi_hold}。严格综合判定仍以本轮 passed 为准，单个分项通过不覆盖其他失败。

失败明细：`{json.dumps(r['failures'],ensure_ascii=False)}`。

测试未涵盖 BLE 双向业务吞吐、互联网、iOS、强制重连、保证发生的 AP 重密钥或整机视觉/云台协同；30 分钟结果不等于生产级长期稳定性验收。

同目录 `events.jsonl`、`result.json` 为原始时序与结果，`minute-metrics.csv` 可按分钟核对；`verified-summary.json` 保存交叉校验和文件摘要。源码 `tools/run_wireless_stability.py`，协议说明 `docs/无线30分钟稳定性测试_20260909.md`。没有刷写 eMMC/STM32、启动云台或远程提交。
'''
(d/'测试结果.md').write_text(body,encoding='utf-8')
manifest=ROOT/'project-manifest.json';m=json.loads(manifest.read_text(encoding='utf-8'));m['latest_stability_checkpoint']=dict(mode=r['mode'],passed=r['passed'],elapsed_s=r['elapsed_s'],sent=r['sent'],received=r['received'],evidence=d.relative_to(ROOT).as_posix(),ble_hold_acceptance='not covered' if r['mode']=='wifi-only' else r['passed'],production_acceptance=False)
m['latest_stability_checkpoint']['ble_hold_acceptance']=ble_hold if r['mode']=='wifi-ble' else 'not covered'
m['latest_stability_checkpoint']['component_acceptance']=summary['component_acceptance']
m['active_stability_test']['state']='completed';manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(m['latest_stability_checkpoint'],ensure_ascii=False))
