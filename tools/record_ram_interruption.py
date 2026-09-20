"""Preserve completed acceptance separately from an interrupted RAM load."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
now = datetime.now(timezone.utc).isoformat()
out = R / 'evidence/neon-file64-20260910/interruption.json'
assert not out.exists()
record = dict(utc=now, state='RAM load interrupted; current runtime unconfirmed',
              last_verified_revision='cxx-unwind-20260910',
              attempted_revision='neon-file64-20260910',
              booted_attempted_image=False, serial_ports=[], removable_volumes=[],
              enumeration='Elevated Win32_SerialPort empty; Get-Volume only fixed C/D/E and recovery volume',
              failure='SerialTimeoutException during RAM load; no full CRC or NSH acceptance',
              wifi_connected=None, ble_service_running=None, emmc_written=False,
              evidence={n: hashlib.sha256((out.parent/n).read_bytes()).hexdigest()
                        for n in ['ramload.bin', 'ramload-progress.txt']})
out.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
p = R / 'project-manifest.json'
m = json.loads(p.read_text(encoding='utf-8'))
if m['current_device'].get('running_revision') == 'cxx-unwind-20260910':
    m['last_verified_device'] = m['current_device']
m['current_device'] = dict(running_revision=None, state=record['state'],
                           wifi_connected=None, ble_service_running=None,
                           serial_port_present=False, model_loaded=False,
                           agent_deployed=False, evidence=str(out.relative_to(R)).replace('\\','/'))
m['pending_firmware'] = dict(revision='neon-file64-20260910', compiled=True,
                            ram_load='interrupted', hardware_tested=False,
                            next='Reconnect serial, preserve snapshot, CRC all regions before boot')
m['updated_at'] = now
p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
p = R / 'README.md'
s = p.read_text(encoding='utf-8')
a = s.index('**当前板端运行')
b = s.index('\n\n', a)
s = s[:a] + ('**当前板端运行状态未确认：neon-file64 RAM 加载中断，Windows 未识别到调试串口。** '
    '新镜像没有完成全量CRC或启动验收，不能宣称无线在线。最后完整通过的是 '
    '`cxx-unwind-20260910`：八核、基础C++探针、真实Wi-Fi配网、BLE30秒及网关5/5；'
    '这些保留为历史验收。NEON与64位文件偏移待恢复串口后上板。'
    '见 `evidence/neon-file64-20260910/interruption.json`。') + s[b:]
p.write_text(s, encoding='utf-8')
print(json.dumps(record))
