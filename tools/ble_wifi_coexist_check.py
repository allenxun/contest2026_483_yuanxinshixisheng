"""Bounded owned-device BLE GATT test while native Wi-Fi is exercised separately."""
import argparse,asyncio,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'无线适配_2026-09-08/tools/ble-python-deps'))
from bleak import BleakClient,BleakScanner
ADDRESS='60:48:9C:B5:17:1D'
STATUS='6b7a0004-78c3-4f2e-9c2f-3ecbc2d74680'
WRITE='6b7a0002-78c3-4f2e-9c2f-3ecbc2d74680'
NOTIFY='6b7a0003-78c3-4f2e-9c2f-3ecbc2d74680'
async def run(log,seconds,reset_bond):
    start=time.monotonic();buffer=bytearray();queue=asyncio.Queue()
    def record(event,**fields):
        row=dict(elapsed=round(time.monotonic()-start,3),event=event,**fields)
        line=json.dumps(row);print(line,flush=True);log.write(line+'\n');log.flush()
    def notify(_,data):
        buffer.extend(data)
        if len(buffer)>4096:raise RuntimeError('notification_overflow')
        while b'\n' in buffer:
            line,_,rest=buffer.partition(b'\n');buffer[:]=rest;queue.put_nowait(json.loads(line))
    if reset_bond:
        await asyncio.wait_for(BleakClient(ADDRESS).unpair(),25)
        record('owned_windows_bond_removed');await asyncio.sleep(2)
    device=await BleakScanner.find_device_by_filter(lambda d,a:d.address.upper()==ADDRESS,timeout=15)
    # Windows may retain an existing GAP link, which stops connectable
    # advertising. The fallback is still this exact owned device address.
    client=BleakClient(device or ADDRESS,pair=True,timeout=35,winrt={'use_cached_services':False})
    try:
        await client.connect();await client.start_notify(NOTIFY,notify)
        state=json.loads(bytes(await client.read_gatt_char(STATUS)));assert state['encrypted']
        record('encrypted_connected',session=state['session'])
        end=time.monotonic()+seconds;count=0
        while time.monotonic()<end:
            assert client.is_connected
            state=json.loads(bytes(await client.read_gatt_char(STATUS)));assert state['encrypted']
            ident=12000+count
            data=(json.dumps(dict(v=1,id=ident,cmd='status'))+'\n').encode()
            for pos in range(0,len(data),20):await client.write_gatt_char(WRITE,data[pos:pos+20],response=True)
            row=await asyncio.wait_for(queue.get(),15)
            assert row['id']==ident and row['event']=='status'
            count+=1;record('gatt_roundtrip',count=count)
            await asyncio.sleep(3)
        record('PASS',scope='Encrypted BLE GATT only; correlate separate WLAN ping evidence',seconds=seconds,roundtrips=count)
    finally:
        if client.is_connected:await client.disconnect()
        record('owned_client_disconnected')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);p.add_argument('--seconds',type=int,default=120);p.add_argument('--reset-owned-bond',action='store_true');a=p.parse_args()
    assert 10<=a.seconds<=300
    with a.log.open('x',encoding='utf-8') as log:asyncio.run(run(log,a.seconds,a.reset_owned_bond))
