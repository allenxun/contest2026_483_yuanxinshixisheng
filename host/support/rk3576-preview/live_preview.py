#!/home/swl/openvela/work/rk3576-vision/venv/bin/python
"""Display K7's sampled tracking JPEGs and telemetry from the debug UART."""
import argparse,base64,binascii,re,sys,time,zlib
sys.path.append('/usr/lib/python3/dist-packages')
import cv2,numpy as np,serial

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',default='/dev/ttyUSB0')
p.add_argument('--seconds',type=int,default=20,choices=range(5,31))
p.add_argument('--limit',type=int,default=30,choices=range(1,51))
p.add_argument('--sign-x',type=int,default=1,choices=[-1,1])
p.add_argument('--sign-y',type=int,default=1,choices=[-1,1])
p.add_argument('--axes',choices=['xy','x','y'],default='xy')
p.add_argument('--run',action='store_true',help='Send gimbal targets; default is visual dry mode')
p.add_argument('--log',default='/home/swl/openvela/work/rk3576-preview/live-preview.log')
a=p.parse_args()
mode='run' if a.run else 'dry'
command=f'k7host preview {mode} {a.seconds} {a.limit} {a.sign_x} {a.sign_y} {a.axes} &'
ansi=re.compile(rb'\x1b\[[0-9;?]*[ -/]*[@-~]')
begin=re.compile(r'VIEW BEGIN q=(\d+) n=(\d+) crc=([0-9a-fA-F]{8})')
box_re=re.compile(r'TRACK BOX q=(\d+) x=([-0-9.]+) y=([-0-9.]+) w=([0-9.]+) h=([0-9.]+) edge=(\d+)')
track_re=re.compile(r'TRACK q=(\d+) s=(\d+) dx=([-0-9.]+) dy=([-0-9.]+) x=(-?\d+) y=(-?\d+) tx=(\d+) age=(\d+)')
states=['lost','confirm','active','stale','halted','clipped']
boxes={};tracks={};frame_q=None;expected=0;expected_crc=0;chunks=[]
shown=bad=0;last_frame=np.zeros((480,640,3),np.uint8)
cv2.putText(last_frame,'Waiting for K7 preview...', (80,240),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
cv2.namedWindow('VelaVision - K7 openvela',cv2.WINDOW_NORMAL)
cv2.resizeWindow('VelaVision - K7 openvela',960,720)
cv2.imshow('VelaVision - K7 openvela',last_frame);cv2.waitKey(1)
s=serial.Serial(port=None,baudrate=1500000,timeout=.03,write_timeout=2,
                exclusive=True,rtscts=False,dsrdtr=False,xonxoff=False)
s.dtr=False;s.rts=False;s.port=a.port;s.open()
started=time.monotonic();stop_sent=False
with s,open(a.log,'ab',buffering=0) as log:
    log.write((f'\n[{time.strftime("%F %T")}] {command}\n').encode())
    s.write(command.encode()+b'\r');s.flush()
    deadline=started+a.seconds+12
    while time.monotonic()<deadline:
        raw=s.readline(4096)
        if raw:
            log.write(raw)
            line=ansi.sub(b'',raw).decode(errors='replace').strip()
            m=box_re.search(line)
            if m: boxes[int(m[1])]=tuple(float(m[i]) for i in range(2,6))+(int(m[6]),)
            m=track_re.search(line)
            if m: tracks[int(m[1])]=(int(m[2]),float(m[3]),float(m[4]),int(m[5]),int(m[6]),int(m[7]),int(m[8]))
            m=begin.search(line)
            if m: frame_q,expected,expected_crc=int(m[1]),int(m[2]),int(m[3],16);chunks=[]
            elif line.startswith('V ') and frame_q is not None: chunks.append(line[2:])
            elif line.startswith('VIEW END q=') and frame_q is not None:
                try:
                    jpeg=base64.b64decode(''.join(chunks),validate=True)
                    if len(jpeg)!=expected or zlib.crc32(jpeg)!=expected_crc: raise ValueError('size/crc')
                    image=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
                    if image is None: raise ValueError('jpeg')
                    if frame_q in boxes:
                        x,y,w,h,edge=boxes[frame_q];scale=image.shape[1]/160
                        color=(0,0,255) if edge else (0,255,0)
                        cv2.rectangle(image,(round(x*scale),round(y*scale)),
                                      (round((x+w)*scale),round((y+h)*scale)),color,2)
                    tr=tracks.get(frame_q)
                    label=f'{mode.upper()} q={frame_q} frames={shown+1} bad={bad}'
                    if tr:
                        state=states[tr[0]] if 0<=tr[0]<len(states) else str(tr[0])
                        label+=f' state={state} target=({tr[3]},{tr[4]}) age={tr[6]}us'
                    cv2.rectangle(image,(0,0),(image.shape[1],34),(0,0,0),-1)
                    cv2.putText(image,label,(8,23),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
                    last_frame=image;shown+=1
                except (ValueError,binascii.Error): bad+=1
                frame_q=None;chunks=[]
        cv2.imshow('VelaVision - K7 openvela',last_frame)
        key=cv2.waitKey(1)&0xff
        closed=cv2.getWindowProperty('VelaVision - K7 openvela',cv2.WND_PROP_VISIBLE)<1
        if (key in (ord('q'),27) or closed) and not stop_sent:
            s.write(b'k7host halt\r');s.flush();stop_sent=True;deadline=min(deadline,time.monotonic()+8)
        if raw and b'TRACK END ' in raw: break
cv2.destroyAllWindows()
print(f'PREVIEW END mode={mode} displayed={shown} corrupt={bad} log={a.log}')
if shown==0: raise SystemExit('No preview frames received')
