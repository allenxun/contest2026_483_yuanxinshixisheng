"""Tie existing Wi-Fi/BLE status monitoring to one bounded compute launch."""
import asyncio
import json
import sys
import time
from pathlib import Path
from ble_load_monitor import BleakClient, BleakScanner, ADDRESS, WRITE, NOTIFY, STATUS
R = Path(__file__).resolve().parents[1]
E = R / 'evidence/smp-load-20260910'

async def run(log):
    start = time.monotonic()
    buffer = bytearray()
    queue = asyncio.Queue()
    process = None
    capture = None
    def record(event, **fields):
        row = dict(wall_time=time.time(), elapsed=round(time.monotonic()-start, 3), event=event, **fields)
        line = json.dumps(row)
        log.write(line+'\n'); log.flush(); print(line, flush=True)
    def receive(_, data):
        buffer.extend(data)
        if len(buffer) > 4096:
            buffer.clear(); queue.put_nowait({}); return
        while b'\n' in buffer:
            line, _, tail = buffer.partition(b'\n'); buffer[:] = tail
            try: queue.put_nowait(json.loads(line))
            except Exception: queue.put_nowait({})
    dev = await BleakScanner.find_device_by_filter(lambda d, a:d.address.upper()==ADDRESS, timeout=20)
    if not dev: raise RuntimeError('Owned advertisement absent')
    client = BleakClient(dev, pair=True, timeout=35, winrt={'use_cached_services':False})
    async def status(ident):
        raw = (json.dumps(dict(v=1, id=ident, cmd='status'), separators=(',',':'))+'\n').encode()
        sent = time.monotonic()
        for pos in range(0, len(raw), 20):
            await client.write_gatt_char(WRITE, raw[pos:pos+20], response=True)
        row = await asyncio.wait_for(queue.get(), 10)
        assert row.get('id') == ident and row.get('session') == state['session']
        assert row.get('event') == 'status' and row.get('wifi_connected') is True
        assert row.get('ip') == '10.3.0.214'
        record('periodic_status_pass', id=ident, ip=row['ip'], response_ms=round((time.monotonic()-sent)*1000, 2))
    try:
        await client.connect()
        await client.start_notify(NOTIFY, receive)
        for _ in range(30):
            state = json.loads(bytes(await client.read_gatt_char(STATUS)))
            if state.get('encrypted'): break
            await asyncio.sleep(.5)
        assert state.get('encrypted') and state.get('connect') is True
        record('encrypted_connection', session=state['session'])
        await status(10000)
        record('hold_started', seconds=80, wifi_reconnected=False)
        capture = (E / 'compute-monitor.txt').open('xb')
        process = await asyncio.create_subprocess_exec(sys.executable, '-X', 'utf8',
            str(R / 'tools/check_compute_radio_overlap.py'), stdout=capture, stderr=asyncio.subprocess.STDOUT)
        end = time.monotonic() + 80
        ident = 10001
        while time.monotonic() < end:
            await asyncio.sleep(5)
            assert client.is_connected
            await status(ident)
            ident += 1
            if process.returncode is not None and process.returncode != 0:
                raise RuntimeError('Compute collector failed')
        result = await asyncio.wait_for(process.wait(), 5)
        assert result == 0
        record('hold_pass', seconds=80, compute_exit_code=result)
    finally:
        # Do not abandon a running collector when BLE fails: it retains the
        # actual bounded board result, and the target workload exits itself.
        if process is not None and process.returncode is None:
            try: await asyncio.wait_for(process.wait(), 70)
            except asyncio.TimeoutError:
                process.terminate(); await process.wait()
                record('collector_timeout')
        if capture is not None: capture.close()
        if client.is_connected: await client.disconnect()
        record('test_client_disconnected')

if __name__ == '__main__':
    assert not (E / 'compute-radio.json').exists()
    with (E / 'ble-overlap.jsonl').open('x', encoding='utf-8') as log:
        try: asyncio.run(run(log))
        except Exception as error:
            line = json.dumps(dict(wall_time=time.time(), event='FAIL', error_type=type(error).__name__))
            log.write(line+'\n'); print(line, flush=True)
            raise SystemExit(1)
