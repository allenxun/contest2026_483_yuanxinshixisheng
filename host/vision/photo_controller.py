"""User-started stability test continuing from the last requested position.

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
from photo_protocol import Protocol

p = argparse.ArgumentParser()
p.add_argument('--profile', type=Path, required=True)
p.add_argument('--control', type=Path, required=True)
p.add_argument('--preview', type=Path, required=True)
p.add_argument('--initial-x', type=int, required=True)
p.add_argument('--initial-y', type=int, required=True)
p.add_argument('--duration', type=int, choices=range(1,301), default=300)
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
if (x,y)!=(0,0):raise ValueError('Guided photo start requires confirmed MCU reset at 0/0')
if not marks['xmin'] <= x <= marks['xmax'] or not marks['ymin'] <= y <= marks['ymax']:
    raise ValueError('Initial state outside calibrated range')
a.control.mkdir(parents=True, exist_ok=False)
telemetry = Telemetry(a.control)
photos = Protocol(a.control)


def status(phase, label):
    tmp = a.control/'status.tmp'
    tmp.write_text(json.dumps(dict(phase=phase,label=label)))
    tmp.replace(a.control/'status.json')


def stopped():
    return (a.control/'stop.request').exists()


def check_stop():
    if stopped():
        raise RuntimeError('STOP REQUESTED - HOLD POSITION')


status('waiting', 'SPACE: START {}s GUIDED PHOTOS'.format(a.duration))
while not ((a.control/'start.request').exists() and (a.preview/'ready.json').exists()):
    if stopped():
        status('done','CANCELLED - NO MOTION SENT')
        sys.exit(0)
    time.sleep(.05)
for count in range(5,0,-1):
    status('countdown','START IN {} - FRONT PHOTO FIRST'.format(count))
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
                log.write(block);log.flush();telemetry.feed(block);photos.feed(block)
            return block.decode('ascii',errors='replace')

        def command(line,expected):
            # Info and adopt retries send no motor targets.
            if expected=='MCU PROFILE v1.3-xcenter X_MID=1492':
                expected='v1.3-xcenter X_MID=1492'
            for attempt in range(3):
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
            command('k7host photoreset', 'PHOTO reset requested;')
            command('gimbal adopt {} {}'.format(x,y),'ADOPT OK x={} y={} NO UART TX'.format(x,y))
            cx,cy=marks['center']
            # K7 pipeline starts from gimbal_link_open's adopted last target.
            # Do not physically recenter between the accepted and stability runs.
            (a.control/'initial.json').write_text(json.dumps(dict(requested=[x,y],measured=False)))
            check_stop()
            line='k7host photos {} &\r'.format(a.duration)
            port.write(line.encode('ascii'));port.flush();tracking=True
            # Read-only live round trip proves NSH remains available while the
            # camera worker runs; do not rely on the GUI's process state.
            # Firmware SHA/MCU profile were verified at deployment. The short
            # photo response avoids the existing UART truncation of info dumps.
            command('k7host photoreset', 'PHOTO reset requested;')
            begin=time.monotonic();previous=-1;first_frame=False
            last_ack=None;ack_at=0;ack_count=0
            while time.monotonic()-begin<a.duration:
                check_stop()
                age=time.monotonic()-begin
                remaining=max(0,a.duration-int(age))
                if remaining!=previous:
                    status('active','GUIDED PHOTOS - {}s LEFT'.format(remaining))
                    previous=remaining
                response=read()
                reset_file=a.control/'reset.request'
                if reset_file.exists():
                    reset_file.unlink();port.write(b'k7host photoreset\r');port.flush()
                try:
                    ack=json.loads((a.control/'ack.request').read_text())
                    candidate=(ack['q'],ack['epoch'],ack['side'],ack['ok'])
                    valid=all(type(v) is int and 0<=v<=0xffffffff for v in candidate)
                    valid=valid and candidate[2] in (1,2,4) and candidate[3] in (0,1)
                except (OSError,ValueError,KeyError,TypeError):valid=False
                if valid:
                    if candidate!=last_ack:last_ack=candidate;ack_count=0;ack_at=0
                    if ack_count<5 and time.monotonic()-ack_at>.6:
                        port.write(('k7host photoack {} {} {} {}\r'.format(*candidate)).encode('ascii'))
                        port.flush();ack_at=time.monotonic();ack_count+=1
                if 'result=-' in response or 'Usage:' in response or 'too many arguments' in response:
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
                status('stopping','STOP REQUESTED - WAITING FOR BOARD ACK')
                port.write(b'k7host halt\r');port.flush()
                acknowledged=False
                until=time.monotonic()+5
                response=''
                while time.monotonic()<until:
                    response+=read();response=response[-16384:]
                    if 'TRACK halt requested:' in response:acknowledged=True
                if not acknowledged:raise RuntimeError('STOP UNCONFIRMED - POWER OFF K7')
except Exception as exc:
    end_label=str(exc)
finally:
    status('done',end_label)
