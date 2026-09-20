import serial,time,re,json
from pathlib import Path
w=Path('/home/swl/openvela/work/rk3576-preview');out=[]
s=serial.Serial(port=None,baudrate=1500000,timeout=.01,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for trial,gap in enumerate((5000,)*10):
  s.reset_input_buffer();start=time.monotonic();data=b''
  s.write(f'k7host uartbench {gap}\r'.encode());s.flush()
  while time.monotonic()-start<6:
   data+=s.read(max(1,min(s.in_waiting,16384)))
   if b'BENCH DONE' in data:break
  duration=time.monotonic()-start
  (w/f'bench-repeat-{trial}-{gap}.log').write_bytes(data)
  valid=[]
  for m in re.finditer(rb'BENCH (\d{3}) ([A-Z]{48})\r?\n',data):
   row=int(m[1]);expect=bytes(65+(row+j)%26 for j in range(48))
   if m[2]==expect:valid.append(row)
  result={'gap_us':gap,'seconds':duration,'bytes_received':len(data),'valid_rows':len(set(valid)),
          'missing_rows':sorted(set(range(256))-set(valid)),'done':b'BENCH DONE' in data}
  out.append(result);print(json.dumps(result),flush=True);time.sleep(.15)
(w/'bench-repeat-results.json').write_text(json.dumps(out,indent=2))
