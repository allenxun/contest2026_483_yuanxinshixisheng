"""Bounded, read-only frontend UART observation; records only safe status lines."""
import argparse,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'无线适配_2026-09-08/tools/pydeps'))
import serial
p=argparse.ArgumentParser();p.add_argument('--port',default='COM8');p.add_argument('--seconds',type=int,default=1800)
p.add_argument('--log',type=Path,required=True);a=p.parse_args()
if not 1<=a.seconds<=1800:p.error('duration must be 1..1800 seconds')
patterns=[r'PROV connected security_request=-?\d+',r'PROV disconnected; input wiped; subscribe again after reconnect',
          r'PROV command=\d+ id=\d+ ret=-?\d+ notify_ret=-?\d+',
          r'RADIO BLE connection status=\d+ handle=\d+ role=\d+',
          r'RADIO BLE disconnected status=\d+ handle=\d+ reason=\d+',
          # Metadata only: never capture SMP keys, ATT values or credentials.
          r'RADIO BLE encryption status=\d+ handle=\d+ enabled=\d+',
          r'RADIO SMP (?:RX|TX) opcode=[0-9a-fA-F]+ bytes=\d+',
          r'RADIO SMP failure reason=\d+',
          r'RADIO SMP TX failure reason=\d+',
          r'RADIO BLE ATT RX count=\d+ opcode=[0-9a-fA-F]+ bytes=\d+',
          r'RADIO HCI LE subevent=[0-9a-fA-F]+ bytes=\d+',
          r'RADIO HCI complete op=[0-9a-fA-F]+ status=\d+',
          r'RADIO HCI command status op=[0-9a-fA-F]+ status=\d+',
          r'WIFI authentication completed=\d+ ret=-?\d+ installed=[0-9a-fA-F]+ IP_acquired=\d+',
          r'WIFI DHCP acquired ip=[0-9.]+ gateway=[0-9.]+ wifi_connected=\d+',
          r'WIFI IP worker stopped ret=-?\d+',
          r'WIFI link lost reason=\d+']
def allowed(line):return any(re.fullmatch(pattern,line) for pattern in patterns)
with a.log.open('x',encoding='utf-8') as log:
    def record(event,**values):
        row=dict(time=datetime.now(timezone.utc).isoformat(),event=event,**values)
        line=json.dumps(row,ensure_ascii=False);log.write(line+'\n');log.flush();print(line,flush=True)
    s=serial.Serial(port=None,baudrate=1500000,timeout=.1,write_timeout=2,rtscts=False,dsrdtr=False,xonxoff=False)
    s.rts=False;s.dtr=False;s.port=a.port;s.open()
    with s:
        record('capture_started',port=a.port,duration_seconds=a.seconds,read_only=True)
        end=time.monotonic()+a.seconds;buf=bytearray()
        while time.monotonic()<end:
            data=s.read(4096)
            if not data:continue
            buf.extend(data)
            while b'\n' in buf:
                row,_,rest=buf.partition(b'\n');buf[:]=rest
                line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',row.decode('ascii',errors='replace')).strip()
                if line.startswith('nsh>'):line=line[4:].strip()
                if allowed(line):record('device_status',line=line)
            if len(buf)>8192:buf.clear()
        record('capture_finished')
