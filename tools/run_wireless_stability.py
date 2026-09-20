"""Bounded 30-minute native Wi-Fi traffic / phone BLE connection-hold test.

No reboot, re-pairing, key submission, firmware changes or motor commands.
Failure is retained rather than hidden by automatic reconnection.
"""
import argparse,hashlib,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
P=argparse.ArgumentParser();P.add_argument('--out',type=Path,required=True);P.add_argument('--wifi-only',action='store_true');A=P.parse_args()
OUT=A.out.resolve();OUT.mkdir(parents=True,exist_ok=False)
REV='wifi-amsdu-index-20260909';DIGEST='85fb84d34a7dbc74469b91c501b3e289791a1b99636829690d3cc6210e688dfe'
assert hashlib.sha256((ROOT/'artifacts'/REV/'nuttx.bin').read_bytes()).hexdigest()==DIGEST
def now():return datetime.now(timezone.utc).isoformat()
def dump(name,obj):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');t.replace(p)
def parse_status(raw):
 b=re.search(r'RADIO BLE name=.* connected=(\d+) handle=(\d+) ACL_RX=(\d+) ACL_TX_queued=(\d+)',raw)
 h=re.search(r'RADIO BLE history connections=(\d+) disconnections=(\d+) last_reason=(\d+) encrypt_status=(\d+) encrypted=(\d+)',raw)
 w=re.search(r'WIFI status active=(\d+) wifi_connected=(\d+) ip=(\S+) gateway=(\S+) result=(-?\d+)',raw)
 m=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) Umem',raw,re.M)
 n=re.search(r'WIFI netdev rx=(\d+) tx=(\d+) dropped=(\d+)',raw)
 a=re.search(r'WIFI AMSDU complete=(\d+) subframes=(\d+) rejected=(\d+)',raw)
 if not all((b,h,w,m,n,a)):raise RuntimeError('Incomplete status snapshot')
 return dict(ble=dict(connected=int(b[1]),handle=int(b[2]),acl_rx=int(b[3]),acl_tx=int(b[4]),connections=int(h[1]),disconnections=int(h[2]),last_reason=int(h[3]),encrypt_status=int(h[4]),encrypted=int(h[5])),wifi=dict(active=int(w[1]),connected=int(w[2]),ip=w[3],gateway=w[4],result=int(w[5]),rx=int(n[1]),tx=int(n[2]),dropped=int(n[3]),amsdu_complete=int(a[1]),amsdu_subframes=int(a[2]),rx_rejected=int(a[3])),memory=dict(zip(('total','used','free','maxused','maxfree','nused','nfree'),map(int,m.groups()))))
safe=re.compile(r'^(?:WIFI (?:status |netdev |AMSDU |data rejected |link lost |link cleanup |IP worker stopped |WPA state=|WPA key type=|WPA EAPOL |DHCP acquired )|RADIO BLE (?:name=|history |disconnected |connection status=)|PROV (?:connected |disconnected;|command=)|\d+ bytes from 10\.3\.0\.1:|\d+ packets transmitted,|rtt min/avg/max/mdev|ERROR:|\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+ Umem)')
events=(OUT/'events.jsonl').open('x',encoding='utf-8')
def record(kind,**values):
 row=dict(time=now(),elapsed_s=round(time.monotonic()-started,3),kind=kind);row.update(values)
 events.write(json.dumps(row,ensure_ascii=False)+'\n');events.flush()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2,rtscts=False,dsrdtr=False,xonxoff=False)
s.dtr=False;s.rts=False;s.port='COM8';started=time.monotonic();phase='initial';rounds=[];failures=[];initial=None
seen_disconnect=False
def inspect(raw):
 global seen_disconnect
 for line in raw.decode('ascii',errors='replace').splitlines():
  line=line.strip()
  if safe.match(line):record('serial',phase=phase,line=line)
  if line.startswith('RADIO BLE disconnected'):seen_disconnect=True
def command(cmd,timeout=4):
 s.write(cmd.encode('ascii')+b'\r');s.flush();buf=bytearray();end=time.monotonic()+timeout
 while time.monotonic()<end:
  buf.extend(s.read(8192))
  if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):
   inspect(buf);return buf.decode('ascii',errors='replace')
 inspect(buf);raise RuntimeError('Console command timed out: '+cmd)
def status():
 return parse_status(command('k7radio ble-status')+'\n'+command('k7radio wifi-status')+'\n'+command('free'))
def healthy(v):
 wifi=v['wifi']['active']==1 and v['wifi']['connected']==1 and v['wifi']['result']==0 and v['wifi']['ip']=='10.3.0.214'
 ble=v['ble']['connected']==1 and v['ble']['encrypted']==1 and v['ble']['encrypt_status']==0
 return wifi and (A.wifi_only or ble)
def progress(state):
 dump('progress.json',dict(state=state,started_at=started_at,updated_at=now(),elapsed_s=round(time.monotonic()-started,2),target_s=1800,completed_rounds=len(rounds),sent=sum(r['sent'] for r in rounds),received=sum(r['received'] for r in rounds),failures=failures,last_snapshot=rounds[-1]['snapshot'] if rounds else initial))
started_at=now()
try:
 with s:
  phase='waiting_for_connection';ready_deadline=time.monotonic()+300;last_ready_state=None
  while True:
   initial=status();state=(initial['ble']['connected'],initial['ble']['encrypted'],initial['wifi']['connected'])
   if healthy(initial):break
   progress('waiting_for_connection')
   if state!=last_ready_state:print('WAIT_CONNECTION '+json.dumps(initial),flush=True);last_ready_state=state
   if time.monotonic()>=ready_deadline:raise RuntimeError('Baseline not ready within 5 minutes; soak did not start')
   time.sleep(5)
  seen_disconnect=False
  started=time.monotonic();started_at=now();record('baseline',snapshot=initial);progress('running')
  print('START '+started_at+' target=1800s rounds=30 ping_per_round=50',flush=True)
  for index in range(30):
   phase=f'round-{index+1}';raw=command('ping -c 50 -I wlan0 10.3.0.1',timeout=58)
   p=re.search(r'(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss',raw)
   if not p:raise RuntimeError('Ping result missing')
   snapshot=status();row=dict(round=index+1,sent=int(p[1]),received=int(p[2]),loss_percent=float(p[3]),snapshot=snapshot)
   rounds.append(row);record('round',**row)
   if row['sent']!=50 or row['received']!=50:failures.append(dict(round=index+1,reason='ping_loss',sent=row['sent'],received=row['received']))
   if not healthy(snapshot) or (not A.wifi_only and (snapshot['ble']['connections']!=initial['ble']['connections'] or snapshot['ble']['disconnections']!=initial['ble']['disconnections'] or seen_disconnect)):
    failures.append(dict(round=index+1,reason='connection_or_encryption_changed'));progress('failed');break
   progress('running')
   print(json.dumps(dict(round=index+1,ping=f"{row['received']}/{row['sent']}",ble_connected=snapshot['ble']['connected'],encrypted=snapshot['ble']['encrypted'],ble_disconnect_delta=snapshot['ble']['disconnections']-initial['ble']['disconnections'],free=snapshot['memory']['free']),ensure_ascii=False),flush=True)
   # Listen until this minute ends; never sleep through a disconnect event.
   end=started+(index+1)*60;pending=bytearray()
   while time.monotonic()<end:
    pending.extend(s.read(8192))
    if b'\n' in pending:
     split=pending.rfind(b'\n')+1;inspect(pending[:split]);del pending[:split]
   if pending:inspect(pending)
  phase='final';final=status();record('final_snapshot',snapshot=final)
  if not healthy(final) or (not A.wifi_only and (final['ble']['disconnections']!=initial['ble']['disconnections'] or seen_disconnect)):
   failures.append(dict(reason='final_connection_changed'))
except Exception as e:
 failures.append(dict(reason=type(e).__name__,detail=str(e)));record('failure',detail=str(e));final=None
elapsed=time.monotonic()-started
passed=len(rounds)==30 and elapsed>=1800 and not failures
scope='30 minute native Wi-Fi gateway ping; BLE observed only, not required for pass' if A.wifi_only else '30 minute phone encrypted BLE connection hold with native Wi-Fi gateway ping'
result=dict(started_at=started_at,finished_at=now(),elapsed_s=round(elapsed,3),target_s=1800,passed=passed,mode='wifi-only' if A.wifi_only else 'wifi-ble',revision=REV,firmware_sha256=DIGEST,rounds_completed=len(rounds),sent=sum(r['sent'] for r in rounds),received=sum(r['received'] for r in rounds),failures=failures,initial=initial,final=final,scope=scope+'; no BLE application throughput, reconnect, internet or guaranteed rekey coverage')
dump('result.json',result);progress('passed' if passed else 'failed');record('result',**result);events.close()
print('RESULT '+json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(0 if passed else 1)
