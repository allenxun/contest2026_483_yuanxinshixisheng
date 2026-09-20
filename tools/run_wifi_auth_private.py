"""Submit the authorized local password only after the board disables echo.
No secret command arguments, environment variables, raw transcript or VM copy.
"""
import argparse,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);p.add_argument('--port',default='COM8');p.add_argument('--wrong-password-test',action='store_true');a=p.parse_args()
credentials=json.loads((root.parent/'本地私密配置/wireless-auth.json').read_text(encoding='utf-8-sig'))
assert credentials['ssid']=='Lansee','Diagnostic currently targets Lansee only'
secret=bytearray(credentials.pop('password').encode('ascii'));assert 8<=len(secret)<=63
if a.wrong_password_test:
    for i in range(len(secret)):secret[i]=0
    secret=bytearray(b'VelaNegativeTest_NotThePassword_2026')
    print('TEST MODE: one deliberate wrong-password attempt on owned Lansee',flush=True)
assert all(32<=c<=126 for c in secret)
credentials.clear()
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,rtscts=False,dsrdtr=False,xonxoff=False)
s.rts=False;s.dtr=False;s.port=a.port
sent=False;finished=False;auth_completed=False;result=None
try:
    with a.log.open('x',encoding='utf-8') as log,s:
        s.write(b'k7radio wifi-auth\r');s.flush()
        deadline=time.monotonic()+70;buffer=bytearray()
        while time.monotonic()<deadline:
            buffer.extend(s.read(4096))
            while b'\n' in buffer:
                line,_,rest=buffer.partition(b'\n');buffer[:]=rest
                text=line.decode('ascii',errors='replace').strip()
                # Whitelist fixed metadata from our adapter/command transport.
                safe=(text.startswith('WIFI ') or re.fullmatch(r'RADIO Wi-Fi (?:cmd=.*|JOIN peer=.*|management response.*|association response_ok=.*|JOIN/AUTH result.*|EAPOL transport.*)',text))
                if safe:
                    text=text.replace(secret.decode('ascii'),'[REDACTED]')
                    row=dict(time=datetime.now(timezone.utc).isoformat(),line=text)
                    log.write(json.dumps(row)+'\n');log.flush();print(text,flush=True)
                if text=='WIFI PASSWORD_INPUT_READY max=63 timeout=15s echo=off' and not sent:
                    s.write(secret);s.write(b'\n');s.flush();sent=True
                if text.startswith('WIFI authentication diagnostic finished'):
                    result=int(re.search(r'ret=(-?\d+)',text)[1])
                    finished=True;break
                if text.startswith('WIFI authentication completed=1'):auth_completed=True
            if finished:break
            if len(buffer)>8192:buffer.clear()
        if not sent:raise RuntimeError('No verified echo-off prompt; password NOT sent')
        if not finished:raise RuntimeError('Board result not received within 70 seconds')
        if a.wrong_password_test:assert result!=0 and not auth_completed,'Wrong password unexpectedly authenticated'
finally:
    for i in range(len(secret)):secret[i]=0
print('Private credential submission completed; see board result above')
