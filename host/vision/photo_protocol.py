"""Board pose telemetry and exact-frame save transactions; no host inference."""
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

NAMES={1:'front',2:'left45',4:'right45'}
NUMBER=r'(-?\d+(?:\.\d+)?)'
POSE=re.compile(r'POSE q=(\d+) e=(\d+) y='+NUMBER+r' p='+NUMBER+r' r='+NUMBER+r' v=(\d+) st=(\d+) next=(\d+) done=(\d+)')
QUALITY=re.compile(r'POSEQ q=(\d+) sy='+NUMBER+r' sharp='+NUMBER+r' settle=(\d+) lost=(\d+) age=(\d+)')
PHOTO=re.compile(r'PHOTO q=(\d+) e=(\d+) s=(\d+) y='+NUMBER+r' p='+NUMBER+r' r='+NUMBER)
PHOTOQ=re.compile(r'PHOTOQ q=(\d+) sy='+NUMBER+r' sp='+NUMBER+r' sr='+NUMBER+r' sharp='+NUMBER+r' size='+NUMBER)

def atomic_json(path,record):
    path=Path(path)
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf8') as f:
        json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

class Protocol:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.buffer='';self.pending={};self.pose={}
    def feed(self,block):
        self.buffer+=block.decode('ascii',errors='replace')
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1)
            m=POSE.search(line)
            if m:
                q,e,y,p,r,v,st,n,d=m.groups()
                self.pose=dict(q=int(q),epoch=int(e),yaw=float(y),pitch=float(p),roll=float(r),
                    valid=bool(int(v)),reason=int(st),next=int(n),done=int(d),at=time.monotonic())
                atomic_json(self.directory/'pose.json',self.pose)
            m=QUALITY.search(line)
            if m and int(m[1])==self.pose.get('q'):
                self.pose.update(smoothed_yaw=float(m[2]),sharpness=float(m[3]),
                    settled=bool(int(m[4])),lost=bool(int(m[5])),age_ms=int(m[6]))
                atomic_json(self.directory/'pose.json',self.pose)
            m=PHOTO.search(line)
            if m:
                q,e,s,y,p,r=m.groups()
                if int(s) in NAMES:
                    self.pending[int(q)]=dict(q=int(q),epoch=int(e),side=int(s),
                        raw_pose=dict(yaw=float(y),pitch=float(p),roll=float(r)))
            m=PHOTOQ.search(line)
            if m and int(m[1]) in self.pending:
                request=self.pending.pop(int(m[1]))
                request.update(filtered_pose=dict(yaw=float(m[2]),pitch=float(m[3]),roll=float(m[4])),
                    sharpness=float(m[5]),face_size=float(m[6]))
                atomic_json(self.directory/'capture.request',request)
            if len(self.pending)>4:
                self.pending.pop(next(iter(self.pending)))
        self.buffer=self.buffer[-16384:]

class FrameCache:
    def __init__(self,limit=120,max_bytes=16*1024*1024):
        self.frames=collections.OrderedDict();self.limit=limit;self.max_bytes=max_bytes
        self.bytes=0;self.lock=threading.Lock()
    def add(self,frame):
        with self.lock:
            old=self.frames.pop(frame['sequence'],None)
            if old:self.bytes-=len(old['jpeg'])
            self.frames[frame['sequence']]=frame;self.bytes+=len(frame['jpeg'])
            while len(self.frames)>self.limit or self.bytes>self.max_bytes:
                _,old=self.frames.popitem(last=False);self.bytes-=len(old['jpeg'])
    def get(self,q):
        with self.lock:return self.frames.get(q)

def validate_request(request):
    for key in ('q','epoch','side'):
        if type(request[key]) is not int or not 0<=request[key]<=0xffffffff:
            raise ValueError('Invalid request identifier')
    if request['epoch']==0 or request['side'] not in NAMES:raise ValueError('Invalid photo stage')
    wanted={1:0,2:45,4:-45}[request['side']]
    for field in ('raw_pose','filtered_pose'):
        pose=request[field]
        if not all(math.isfinite(pose[x]) for x in ('yaw','pitch','roll')):raise ValueError('Nonfinite pose')
        if abs(pose['yaw']-wanted)>7.002 or abs(pose['pitch'])>12.002 or abs(pose['roll'])>12.002:
            raise ValueError('Angle does not qualify')
    if not math.isfinite(request['sharpness']) or request['sharpness']<59.9:
        raise ValueError('Photo not sharp enough')
    if not math.isfinite(request['face_size']) or request['face_size']<79.9:
        raise ValueError('Face too small')

def save_exact(root,request,frame):
    validate_request(request)
    if frame is None or frame['sequence']!=request['q']:raise ValueError('Exact JPEG frame unavailable')
    if (frame['width'],frame['height'])!=(640,480):raise ValueError('Unexpected image size')
    payload=frame['jpeg']
    if not payload.startswith(b'\xff\xd8') or not payload.endswith(b'\xff\xd9'):raise ValueError('Invalid JPEG')
    folder=Path(root)/('set-%04d'%request['epoch']);folder.mkdir(parents=True,exist_ok=True)
    stem='%s-q%08d'%(NAMES[request['side']],request['q'])
    image=folder/(stem+'.jpg');meta=folder/(stem+'.json')
    digest=hashlib.sha256(payload).hexdigest()
    record=dict(request,image=image.name,jpeg_sha256=digest,
        capture_us=frame['capture_us'],received_at_host_monotonic=frame['received_at'],
        saved_at_unix=time.time(),inference='K7_NATIVE_CPU_FSA_NET',
        storage='Ubuntu local filesystem',mirrored=False,yaw_tolerance_deg=7,
        left_yaw_sign=1,view_label_convention='operator head-turn direction',
        stability='image pose plus command-delta estimate; no servo encoder',
        model_sha256='120fa107a2dd3be78c21c3a73a0db980590643a5372893e8878094898262f213')
    if meta.exists():
        existing=json.loads(meta.read_text())
        if existing['jpeg_sha256']!=digest or not image.exists() or hashlib.sha256(image.read_bytes()).hexdigest()!=digest:
            raise ValueError('Existing photo pair failed integrity check')
        return str(image)
    temporary=image.with_suffix('.jpg.tmp')
    with temporary.open('wb') as f:
        f.write(payload);f.flush();os.fsync(f.fileno())
    os.replace(temporary,image)
    atomic_json(meta,record)
    # Confirm both directory entries before acknowledging to the board.
    if os.name=='posix':
        fd=os.open(str(folder),os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return str(image)

def saver_worker(control,root,cache,stop):
    """No filesystem work runs in the USB receiver or native tracking worker."""
    control=Path(control);handled={}
    while not stop.wait(.02):
        try:request=json.loads((control/'capture.request').read_text())
        except (OSError,ValueError):continue
        try:
            key=(request['q'],request['epoch'],request['side'])
            validate_request(request)
        except (KeyError,TypeError,ValueError):continue
        if key in handled:continue
        frame=cache.get(key[0]);deadline=time.monotonic()+.5
        while frame is None and time.monotonic()<deadline and not stop.wait(.02):frame=cache.get(key[0])
        try:
            image=save_exact(root,request,frame);ok=1;error=''
        except (OSError,ValueError,KeyError,TypeError) as exc:
            image=None;ok=0;error=str(exc)
        ack=dict(q=key[0],epoch=key[1],side=key[2],ok=ok,image=image,error=error)
        atomic_json(control/'save.json',ack)
        atomic_json(control/'ack.request',ack)
        handled[key]=True
        if len(handled)>256:handled.pop(next(iter(handled)))
