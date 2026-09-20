"""Owned K7 real BLE-to-WPA2/DHCP test; credentials stay local and unlogged."""
import argparse,asyncio,base64,json,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/ble-python-deps'))
from bleak import BleakClient,BleakScanner
ADDRESS='60:48:9C:B5:17:1D'
PREFIX='6b7a000';SUFFIX='-78c3-4f2e-9c2f-3ecbc2d74680'
WRITE=PREFIX+'2'+SUFFIX;NOTIFY=PREFIX+'3'+SUFFIX;STATUS=PREFIX+'4'+SUFFIX
async def run(log,reset,hold_seconds=0):
 start=time.monotonic();buf=bytearray();queue=asyncio.Queue()
 def record(event,**fields):
  row=dict(wall_time=time.time(),elapsed=round(time.monotonic()-start,3),event=event,**fields)
  s=json.dumps(row);log.write(s+'\n');log.flush();print(s,flush=True)
 def receive(_,data):
  buf.extend(data)
  if len(buf)>4096:buf.clear();queue.put_nowait({'event':'overflow'});return
  while b'\n' in buf:
   line,_,tail=buf.partition(b'\n');buf[:]=tail
   try:queue.put_nowait(json.loads(line))
   except Exception:queue.put_nowait({'event':'decode_error'})
 if reset:
  await asyncio.wait_for(BleakClient(ADDRESS).unpair(),25)
  record('owned_windows_bond_removed');await asyncio.sleep(2)
 dev=await BleakScanner.find_device_by_filter(lambda d,a:d.address.upper()==ADDRESS,timeout=20)
 if not dev:raise RuntimeError('owned_advertisement_absent')
 client=BleakClient(dev,pair=True,timeout=35,winrt={'use_cached_services':False})
 async def request(ident,cmd,**fields):
  raw=bytearray((json.dumps(dict(v=1,id=ident,cmd=cmd,**fields),separators=(',',':'))+'\n').encode())
  try:
   for pos in range(0,len(raw),20):await client.write_gatt_char(WRITE,raw[pos:pos+20],response=True)
  finally:raw[:]=b'\0'*len(raw)
  deadline=time.monotonic()+120
  while True:
   row=await asyncio.wait_for(queue.get(),max(.1,deadline-time.monotonic()))
   assert row.get('id')==ident and row.get('session')==state['session']
   # Only protocol metadata. Never outgoing request, SSID, password or raw ATT.
   record('response',**{k:row[k] for k in ('id','session','event','code','detail','wifi_connected','ip') if k in row and k!='event'},response_event=row['event'])
   if row['event']!='wifi_connecting':return row
 try:
  await client.connect();await client.start_notify(NOTIFY,receive)
  for _ in range(30):
   state=json.loads(bytes(await client.read_gatt_char(STATUS)))
   if state.get('encrypted'):break
   await asyncio.sleep(.5)
  assert state.get('encrypted') and state.get('connect') is True
  record('connect_capability_verified',session=state['session'],encrypted=True)
  invalid=await request(9100,'connect',ssid_b64='TGFuc2Vl',password='short')
  assert invalid['event']=='error' and invalid['code']=='invalid_password'
  record('invalid_password_rejected')
  auth=json.loads((R.parent/'本地私密配置/wireless-auth.json').read_text(encoding='utf-8-sig'))
  assert auth['ssid']=='Lansee'
  try:
   result=await request(9101,'connect',ssid_b64=base64.b64encode(auth['ssid'].encode()).decode(),password=auth['password'])
  finally:auth.clear()
  assert result['event']=='wifi_connected' and result['wifi_connected'] and result['ip'] not in (None,'0.0.0.0')
  status=await request(9102,'status')
  assert status['event']=='status' and status['wifi_connected'] and status['ip']==result['ip']
  record('PASS',scope='Real Windows BLE request -> native WPA2/DHCP -> matching IP status; not Android/iOS or internet acceptance',ip=result['ip'])
  if hold_seconds:
   record('hold_started',seconds=hold_seconds)
   for _ in range(hold_seconds):
    await asyncio.sleep(1)
    assert client.is_connected, 'BLE disconnected during hold'
    if _ % 5 == 4:
     tick=await request(9200+_,'status')
     assert tick['wifi_connected'] and tick['ip']==result['ip']
     record('periodic_status_pass',id=9200+_,ip=tick['ip'])
   held=await request(9103,'status')
   assert held['wifi_connected'] and held['ip']==result['ip']
   record('hold_pass',seconds=hold_seconds,ip=held['ip'])
 finally:
  if client.is_connected:await client.disconnect()
  record('test_client_disconnected')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);p.add_argument('--reset-owned-bond',action='store_true');p.add_argument('--hold-seconds',type=int,default=0,choices=range(0,301));a=p.parse_args()
 with a.log.open('x',encoding='utf-8') as f:
  try:asyncio.run(run(f,a.reset_owned_bond,a.hold_seconds))
  except Exception as e:
   # Library exceptions may contain request bytes; do not print their messages.
   line=json.dumps(dict(event='FAIL',error_type=type(e).__name__))
   f.write(line+'\n');print(line);raise SystemExit(1)
