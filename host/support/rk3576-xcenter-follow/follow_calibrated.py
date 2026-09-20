"""User-started calibrated face tracking with bounded return to reference.

Initial position is an explicitly supplied last-command/reset state, not feedback.
Q/Esc cancels further moves; the MCU keeps its last PWM position.
"""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.append('/usr/lib/python3/dist-packages')
import serial
from manual_model import validate, resume_state
from track_overlay import Telemetry

p = argparse.ArgumentParser()
p.add_argument('--profile', type=Path, required=True)
p.add_argument('--control', type=Path, required=True)
p.add_argument('--preview', type=Path, required=True)
p.add_argument('--initial-x', type=int, required=True)
p.add_argument('--initial-y', type=int, required=True)
p.add_argument('--duration', type=int, choices=range(1,301), default=60)
a = p.parse_args()
profile = json.loads(a.profile.read_text())
resume_state(profile)  # Validate saved data types and MCU version.
marks = profile['marks']
valid, message = validate(marks)
if profile.get('complete') is not True or not valid:
    raise ValueError('Incomplete calibration: '+message)
sx, sy = profile['sign_x'], profile['sign_y']
if sx not in (-1,1) or sy not in (-1,1):
    raise ValueError('invalid direction')
x,y = a.initial_x,a.initial_y
if not marks['xmin'] <= x <= marks['xmax'] or not marks['ymin'] <= y <= marks['ymax']:
    raise ValueError('Initial state outside calibrated range')
a.control.mkdir(parents=True, exist_ok=False)
telemetry = Telemetry(a.control)


def status(phase, label):
    tmp = a.control/'status.tmp'
    tmp.write_text(json.dumps(dict(phase=phase,label=label)))
    tmp.replace(a.control/'status.json')


def stopped():
    return (a.control/'stop.request').exists()


def check_stop():
    if stopped():
        raise RuntimeError('STOP REQUESTED - HOLD POSITION')


status('waiting', 'SPACE: START {}s CALIBRATED FOLLOW'.format(a.duration))
while not ((a.control/'start.request').exists() and (a.preview/'ready.json').exists()):
    if stopped():
        status('done','CANCELLED - NO MOTION SENT')
        sys.exit(0)
    time.sleep(.05)
for count in range(5,0,-1):
    status('countdown','START IN {} - FACE FOLLOW'.format(count))
    until=time.monotonic()+1
    while time.monotonic()<until:
        if stopped():
            status('done','CANCELLED - NO MOTION SENT')
            sys.exit(0)
        time.sleep(.02)
port=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=1,exclusive=True)
port.dtr=port.rts=False
port.port='/dev/ttyUSB0'
tracking=False
end_label='TEST FINISHED - HOLD POSITION'
try:
    port.open()
    with port, (a.control/'serial.log').open('ab') as log:
        def read():
            block=port.read(8192)
            if block:
                log.write(block);log.flush();telemetry.feed(block)
            return block.decode('ascii',errors='replace')

        def command(line,expected):
            check_stop();read()
            port.write((line+'\r').encode('ascii'));port.flush()
            response='';until=time.monotonic()+1.2
            while time.monotonic()<until:
                check_stop();response+=read()
                if expected in response:return
                if 'JOG LIMIT' in response or 'command not found' in response:
                    raise RuntimeError('BOARD COMMAND REJECTED - HOLD')
            raise RuntimeError('BOARD RESPONSE TIMEOUT - HOLD')

        try:
            command('gimbal info', 'MCU PROFILE v1.3-xcenter X_MID=1492')
            command('gimbal adopt {} {}'.format(x,y),'ADOPT OK x={} y={} NO UART TX'.format(x,y))
            cx,cy=marks['center']
            for axis,target in ((0,cx),(1,cy)):
                while (x if axis==0 else y)!=target:
                    check_stop()
                    diff=target-(x if axis==0 else y)
                    delta=max(-5,min(5,diff))
                    dx,dy=(delta,0) if axis==0 else (0,delta)
                    nx,ny=x+dx,y+dy
                    status('centering','SLOW CENTER X={} Y={} - Q/ESC STOP'.format(nx,ny))
                    command('gimbal jog {} {}'.format(dx,dy),'JOG OK x={} y={}'.format(nx,ny))
                    x,y=nx,ny
                    until=time.monotonic()+.1
                    while time.monotonic()<until:check_stop();read()
            (a.control/'centered.json').write_text(json.dumps(dict(requested=[x,y],measured=False)))
            check_stop()
            line='k7host trackcal run {} {} {} {} {} {} {} {} {} &\r'.format(
                a.duration,marks['xmin'],marks['xmax'],marks['ymin'],marks['ymax'],cx,cy,sx,sy)
            port.write(line.encode('ascii'));port.flush();tracking=True
            begin=time.monotonic();previous=-1;first_frame=False
            while time.monotonic()-begin<a.duration:
                check_stop()
                age=time.monotonic()-begin
                remaining=max(0,a.duration-int(age))
                if remaining!=previous:
                    phase=min(3,int(age/max(1,a.duration/4)))
                    cue=('LEFT / RIGHT','UP / DOWN','BOTH AXES','HOLD STILL')[phase]
                    status('active','CALIBRATED FOLLOW {}s: {}'.format(remaining,cue))
                    previous=remaining
                response=read()
                if 'result=-' in response or 'Usage:' in response:
                    raise RuntimeError('CAMERA/TRACK ERROR - HOLD')
                # The preview supplies a heartbeat of actual received frames.
                try:
                    view=json.loads((a.control/'view.json').read_text())
                    fresh=0 <= time.monotonic()-view['at']<.7 and view['age']<.6
                except (OSError,ValueError,KeyError,TypeError):fresh=False
                if fresh:first_frame=True
                if (first_frame and not fresh) or (not first_frame and age>8):
                    raise RuntimeError('VIDEO STALE - FOLLOW STOPPED')
        finally:
            if tracking:
                port.write(b'k7host halt\r');port.flush()
                until=time.monotonic()+5
                while time.monotonic()<until:read()
except Exception as exc:
    end_label=str(exc)
finally:
    status('done',end_label)
