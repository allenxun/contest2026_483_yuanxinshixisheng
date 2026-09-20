"""Record actual MMU and Wi-Fi evidence for this exact RAM revision."""
from pathlib import Path
import json, hashlib, datetime
R=Path(__file__).resolve().parents[1];E=R/'evidence/audio-mmu-20260910'
raw=E/'mmu-20260911-093323.bin'
assert hashlib.sha256(raw.read_bytes()).hexdigest()=='aef96c42d986a61a03adabb787b25d5634e315920ef42e39a4dde5dc20de49f7'
assert b'ngnrne=1 identity=1 AF=1' in raw.read_bytes()
w=json.loads((E/'wifi-gateway.json').read_text())
assert any('5 packets transmitted, 5 received' in line for r in w['records'] for line in r['lines'])
report=dict(revision='audio-mmu-20260910',sha256='886137227992f07ff1a32ff3662d4de2c799d1baa6fa15238bbba75cfbed2638',
 mmu=dict(cpu=0,reads=3,output_pa='0x2a610000',device_ngnrne=True,identity=True,access_flag=True,
 raw=raw.name,limits='Current EL1 page tables and stable registers; not independent TLB/stage2 attestation'),
 wifi=dict(auth_route='private serial diagnostic',wpa2=True,dhcp_ip='10.3.0.214',gateway_sent=5,gateway_received=5),
 ble=dict(service_registered=True,client_connected=False,gatt_tested=False),audio_noise_fixed=False)
(E/'runtime-results.json').write_text(json.dumps(report,indent=2)+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
m['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
m['pending_firmware']=None
m['current_device']=dict(revision=report['revision'],sha256=report['sha256'],wifi_online=True,ip='10.3.0.214',ble_connected=False,ble_service_registered=True,evidence='evidence/audio-mmu-20260910/runtime-results.json')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n2026-09-11 09:33 MMU真机：audio-mmu-20260910 RAM加载成功，CPU0三次页表读取，SAI 0x2a610000为Device-nGnRnE、identity和AF有效；不代替TLB/Stage2全验证。09:34通过私密串口认证恢复Lansee WPA2/DHCP 10.3.0.214，空ARP起步网关5/5，A-MSDU 1组2子帧/0拒收。BLE服务注册、客户端未连接，未声称GATT通过。见 evidence/audio-mmu-20260910/runtime-results.json；杂声未修复。\n')
print('Actual MMU and WLAN results recorded')
