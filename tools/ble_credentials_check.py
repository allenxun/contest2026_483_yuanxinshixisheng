"""Owned K7 BLE reception test: synthetic password only; no Wi-Fi connect."""
import argparse,asyncio,base64,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'无线适配_2026-09-08/tools/ble-python-deps'))
from bleak import BleakClient,BleakScanner
WRITE='6b7a0002-78c3-4f2e-9c2f-3ecbc2d74680'
NOTIFY='6b7a0003-78c3-4f2e-9c2f-3ecbc2d74680'
STATUS='6b7a0004-78c3-4f2e-9c2f-3ecbc2d74680'
ADDRESS='60:48:9C:B5:17:1D'
async def check(log):
    started=time.monotonic()
    def record(event,**data):
        row=dict(elapsed=round(time.monotonic()-started,3),event=event,**data)
        text=json.dumps(row,ensure_ascii=False);print(text,flush=True);log.write(text+'\n');log.flush()
    device=await BleakScanner.find_device_by_filter(lambda d,a:d.address.upper()==ADDRESS,timeout=15)
    assert device,'Owned K7 advertisement absent'
    record('advertisement',address=device.address,name=device.name)
    client=BleakClient(device,pair=True,timeout=35,winrt={'use_cached_services':False})
    buf=bytearray();queue=asyncio.Queue()
    def receive(char,data):
        buf.extend(data)
        if len(buf)>4096:queue.put_nowait({'event':'overflow'});buf.clear();return
        while b'\n' in buf:
            line,_,tail=buf.partition(b'\n');buf[:]=tail
            try:queue.put_nowait(json.loads(line))
            except Exception:queue.put_nowait({'event':'decode_error'})
    async def send(data):
        for pos in range(0,len(data),20):await client.write_gatt_char(WRITE,data[pos:pos+20],response=True)
    async def request(ident,cmd,**fields):
        # Deliberately never log outgoing JSON or password-bearing exceptions.
        data=bytearray((json.dumps(dict(v=1,id=ident,cmd=cmd,**fields),separators=(',',':'))+'\n').encode())
        try:await send(data)
        finally:data[:]=b'\0'*len(data)
        response=await asyncio.wait_for(queue.get(),20);assert response.get('id')==ident
        return response
    try:
        await client.connect();await client.start_notify(NOTIFY,receive)
        for _ in range(20):
            state=json.loads(bytes(await client.read_gatt_char(STATUS)))
            if state.get('encrypted'):break
            await asyncio.sleep(.5)
        assert state.get('encrypted') and state.get('receive_credentials') is True and state.get('connect') is False
        record('capabilities',state=state)
        await send(b'X');start=await asyncio.wait_for(queue.get(),20);assert start['event']=='scan_started'
        count=0;target=None
        while True:
            row=await asyncio.wait_for(queue.get(),60);assert row['id']==start['id']
            if row['event']=='scan_done':assert row['count']==count;break
            assert row['event']=='ap';count+=1
            if base64.b64decode(row['ssid_b64'])==b'Lansee':target=row['ssid_b64']
        assert count and target
        record('real_scan_pass',count=count,lansee_present=True)
        reply=await request(9001,'submit_credentials',ssid_b64=target,password='VelaTest_123!')
        assert reply==dict(v=1,id=9001,session=state['session'],event='credentials_received',validated=True,stored=False,wifi_connected=False,ip=None)
        record('synthetic_credentials_receipt',response=reply)
        reply=await request(9002,'submit_credentials',ssid_b64=target,password='short')
        assert reply['event']=='error' and reply['code']=='invalid_password' and reply['session']==state['session']
        record('invalid_password_rejected',response=reply)
        reply=await request(9003,'status')
        assert reply['event']=='status' and reply['wifi_connected'] is False and reply['ip'] is None
        record('status_no_connection',response=reply)
        record('PASS',scope='Windows BLE: real scan and synthetic credential receipt only',wifi_connection_attempted=False)
    finally:
        if client.is_connected:await client.disconnect()
        record('test_client_disconnected')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);args=p.parse_args()
    with args.log.open('x',encoding='utf-8') as log:asyncio.run(check(log))
