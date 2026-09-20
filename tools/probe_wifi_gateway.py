"""Bounded gateway/ARP checks; metadata only, no credentials or radio reset."""
import argparse,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
p=argparse.ArgumentParser()
p.add_argument('--out',type=Path,required=True)
p.add_argument('--status-only',action='store_true')
a=p.parse_args()
records=[]
safe=re.compile(r'^(?:WIFI (?:status |netdev |AMSDU |ARP |data rejected |link lost |IP worker stopped )|RADIO BLE (?:name=|history |disconnected |connection status=)|PROV (?:registered=|command=|last )|ARP|arp:|nsh: arp:|10\.3\.0\.1\b|[0-9]+ bytes from 10\.3\.0\.1:|[0-9]+ packets transmitted,|rtt min/avg/max/mdev|ERROR:|\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+ Umem)')
s=serial.Serial(port=None,baudrate=1500000,timeout=.03,write_timeout=2,rtscts=False,dsrdtr=False,xonxoff=False)
s.rts=False;s.dtr=False;s.port='COM8'
def command(cmd,timeout=12):
    s.write(cmd.encode('ascii')+b'\r');s.flush();buf=bytearray();end=time.monotonic()+timeout
    while time.monotonic()<end:
        buf.extend(s.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):break
    else:raise RuntimeError('Console timeout: '+cmd)
    lines=[]
    for line in buf.decode('ascii',errors='replace').splitlines():
        line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
        if line.startswith('nsh>'):line=line[4:].strip()
        if safe.match(line):lines.append(line)
        elif '10.3.0.1' in line:
            mac=re.search(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}',line)
            if mac:lines.append('ARP gateway=10.3.0.1 mac='+mac[0])
    row=dict(time=datetime.now(timezone.utc).isoformat(),command=cmd,lines=lines)
    records.append(row);print(json.dumps(row),flush=True)
try:
    with s:
        command('k7radio wifi-status');command('arp -i wlan0 -a 10.3.0.1')
        if not a.status_only:
            command('ping -c 5 -I wlan0 10.3.0.1',20)
            command('arp -i wlan0 -a 10.3.0.1')
        command('k7radio wifi-status');command('k7radio ble-status');command('k7radio provision-status');command('free')
finally:
    with a.out.open('x',encoding='utf-8') as f:
        json.dump(dict(temporary_arp=False,status_only=a.status_only,records=records),f,indent=2);f.write('\n')
