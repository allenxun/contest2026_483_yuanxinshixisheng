"""Release the owned test Wi-Fi connection and verify K7 advertising for phone tests."""
import asyncio
import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/audio-preflight-20260910'
sys.path.insert(0, str(ROOT.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial
sys.path.insert(0, str(ROOT.parent / '无线适配_2026-09-08/tools/ble-python-deps'))
from bleak import BleakScanner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-only', action='store_true', help='Inspect an already released network; do not disconnect again')
    args = parser.parse_args()
    assert (OUT / 'runtime-acceptance.json').exists()
    port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
    port.dtr = False
    port.rts = False
    port.port = 'COM8'
    rows = []
    def command(text):
        raw = bytearray()
        port.write(text.encode('ascii') + b'\r')
        port.flush()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            raw.extend(port.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
                rows.append(dict(command=text, output=raw.decode('ascii', errors='replace')))
                return bytes(raw)
        rows.append(dict(command=text, output=raw.decode('ascii', errors='replace'), timed_out=True))
        raise RuntimeError('Console observation timeout')
    result = dict(ready=False, rows=rows)
    try:
        with port:
            if not args.verify_only:
                command('k7radio wifi-disconnect')
            for _ in range(10):
                status = command('k7radio wifi-status')
                if b'WIFI status active=0 wifi_connected=0' in status:
                    break
                time.sleep(.5)
            else:
                raise RuntimeError('Wi-Fi cleanup not confirmed')
            ble = command('k7radio ble-status')
            prov = command('k7radio provision-status')
            assert b'connected=0' in ble and b'PROV registered=1 connected=0' in prov
        async def find_owned():
            dev = await BleakScanner.find_device_by_filter(
                lambda d, a: d.address.upper() == '60:48:9C:B5:17:1D', timeout=15)
            return dev is not None
        result['advertisement_observed'] = asyncio.run(find_owned())
        result['ready'] = result['advertisement_observed']
        result['wifi_connected'] = False
        result['ble_connected'] = False
        result['name'] = 'VelaVision K7'
    finally:
        result['recorded_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_name = 'phone-ready-recovery.json' if args.verify_only else 'phone-ready.json'
        with (OUT / report_name).open('x', encoding='utf-8') as file:
            json.dump(result, file, indent=2)
    path = ROOT / 'project-manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['current_device'].update(wifi_connected=False, ip=None, ble_connected=False,
                                      phone_scan_ready=result['ready'],
                                      state='Test network intentionally disconnected; BLE service retained for phone scan')
    manifest['updated_at'] = result['recorded_utc']
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
    if not result['ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
