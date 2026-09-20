"""Bounded run with countdown and batch UART reading independent of GUI."""
import sys,time,threading,re,base64,zlib,json
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
import serial,cv2,numpy as np
w=Path('/home/swl/openvela/work/rk3576-preview')
name='visible-mounted-'+time.strftime('%Y%m%d-%H%M%S')
shared={'frame':None,'q':0,'good':0,'bad':0,'last':0.,'end':False,'error':'','track':'','box':None}
quit_reader=threading.Event()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
log=(w/(name+'.log')).open('xb',buffering=0)
def reader():
    pending=b'';chunks=[];head=None;boxes={}
    try:
        while not quit_reader.is_set():
            data=s.read(max(1,min(s.in_waiting,16384)))
            if not data:continue
            log.write(data);pending+=data
            while b'\n' in pending:
                raw,pending=pending.split(b'\n',1)
                line=re.sub(rb'\x1b\[[0-9;?]*[ -/]*[@-~]',b'',raw).decode(errors='replace').strip()
                m=re.search(r'TRACK BOX q=(\d+) x=([-0-9.]+) y=([-0-9.]+) w=([0-9.]+) h=([0-9.]+) edge=(\d+)',line)
                if m:boxes[int(m[1])]=tuple(float(m[i]) for i in range(2,6))+(int(m[6]),)
                if line.startswith('TRACK q='):shared['track']=line
                if 'TRACK END obs=' in line:shared['end']=True
                m=re.search(r'VIEW BEGIN q=(\d+) n=(\d+) crc=([0-9a-fA-F]{8})',line)
                if m:head=(int(m[1]),int(m[2]),int(m[3],16));chunks=[]
                elif line.startswith('V ') and head:chunks.append(line[2:])
                elif line.startswith('VIEW END q=') and head:
                    try:
                        payload=base64.b64decode(''.join(chunks),validate=True)
                        assert int(line.split('=')[-1])==head[0]
                        assert len(payload)==head[1] and zlib.crc32(payload)==head[2]
                        img=cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_COLOR)
                        assert img is not None and img.shape[:2]==(120,160)
                        shared.update(frame=img,q=head[0],box=boxes.get(head[0]),last=time.monotonic(),good=shared['good']+1)
                    except Exception:shared['bad']+=1
                    head=None;chunks=[]
                if len(boxes)>400:boxes={k:v for k,v in boxes.items() if k>shared['q']-20}
    except Exception as exc:shared['error']=str(exc)
thread=threading.Thread(target=reader);thread.start()
title='VelaVision - LIVE TEST - Q stops motion'
cv2.namedWindow(title,cv2.WINDOW_NORMAL|cv2.WINDOW_GUI_NORMAL)
cv2.resizeWindow(title,960,840)
start=time.monotonic();sent=False;halted=False;run_at=None;ended_at=None
try:
    while True:
        now=time.monotonic();elapsed=now-start
        if not sent and elapsed>=10:
            cmd=b'k7host preview run 25 30 1 1 xy &\r'
            log.write(b'\nHOST_SEND '+cmd+b'\n');s.write(cmd);s.flush();sent=True;run_at=now
        if sent and not halted and (now-run_at>=20 or shared['error'] or (now-run_at>5 and now-shared['last']>4)):
            s.write(b'k7host halt\r');s.flush();halted=True
        state=f'READY - START IN {max(0,10-int(elapsed))} s' if not sent else ('STOPPED - HOLD POSITION' if halted or shared['end'] else 'TRACKING - MOVE SLOWLY')
        canvas=np.zeros((840,960,3),np.uint8)
        img=shared['frame']
        if img is not None:
            large=cv2.resize(img,(960,720),interpolation=cv2.INTER_LINEAR)
            box=shared['box']
            if box:
                x,y,bw,bh,edge=box
                cv2.rectangle(large,(round(x*6),round(y*6)),(round((x+bw)*6),round((y+bh)*6)),(0,0,255) if edge else (0,255,0),2)
            canvas[120:]=large
        cv2.putText(canvas,state,(18,34),cv2.FONT_HERSHEY_SIMPLEX,.85,(0,220,255),2)
        age=now-shared['last'] if shared['last'] else 0
        cv2.putText(canvas,f'Frames {shared["good"]} | Dropped {shared["bad"]} | Age {age:.1f}s | Q / Esc: stop',(18,66),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
        cv2.putText(canvas,shared['track'][:110],(18,98),cv2.FONT_HERSHEY_SIMPLEX,.45,(200,200,200),1)
        cv2.imshow(title,canvas)
        key=cv2.waitKey(20)&255
        if key in (27,ord('q')) or cv2.getWindowProperty(title,cv2.WND_PROP_VISIBLE)<1:break
        if shared['end'] and ended_at is None:ended_at=now
        if ended_at and now-ended_at>15:break
        if elapsed>60:break
finally:
    if sent and not halted:
        s.write(b'k7host halt\r');s.flush()
    quit_reader.set();thread.join(timeout=2);s.close();log.close();cv2.destroyAllWindows()
    result={k:v for k,v in shared.items() if k not in ('frame','box')}
    (w/(name+'.json')).write_text(json.dumps(result,indent=2))
    print(name,json.dumps(result),flush=True)
