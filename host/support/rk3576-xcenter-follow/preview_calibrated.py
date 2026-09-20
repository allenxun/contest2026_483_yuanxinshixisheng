"""USB JPEG preview only. This program never opens the MCU/debug serial port."""
import argparse
import json
from pathlib import Path
import threading
import time
import cv2
import numpy as np
import usb.core
import usb.util
from k7_video_receiver import Receiver
from track_overlay import display_box

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=float, default=45)
parser.add_argument('--control', type=Path)
parser.add_argument('--title')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
if args.control:
    args.control.mkdir(parents=True, exist_ok=True)
ready = args.output/'ready.json'
if ready.exists():
    ready.unlink()
cv2.setNumThreads(2)
stop = threading.Event()
lock = threading.Lock()
state = {'message': 'WAITING FOR K7 USB - MOTORS OFF', 'image': None,
         'frame': None, 'decoded': 0, 'decode_errors': 0, 'bytes': 0,
         'first': None, 'last': None, 'intervals': [], 'first_frame': None,
         'error': None}
receiver = Receiver()


def read_worker():
    dev = None
    claimed = False
    try:
        while not stop.is_set():
            dev = usb.core.find(idVendor=0x1209, idProduct=0x0001)
            if dev is not None:
                break
            stop.wait(0.25)
        if stop.is_set():
            return
        if usb.util.get_string(dev, dev.iProduct) != 'openvela link probe':
            raise RuntimeError('Private VID/PID belongs to another test device')
        cfg = dev.get_active_configuration()
        ep = usb.util.find_descriptor(cfg[(0, 0)], bEndpointAddress=0x81)
        if cfg.bConfigurationValue != 1 or ep is None or ep.wMaxPacketSize != 512:
            raise RuntimeError('Expected high-speed video endpoint not configured')
        usb.util.claim_interface(dev, 0)
        claimed = True
        ready.write_text(json.dumps({'configured': True, 'endpoint': 129}))
        with lock:
            state['message'] = 'USB READY - WAITING FOR CAMERA - MOTORS OFF'
        while not stop.is_set():
            try:
                raw = bytes(dev.read(0x81, 16384, timeout=200))
            except usb.core.USBTimeoutError:
                receiver.expire()
                continue
            frame = receiver.feed(raw)
            with lock:
                state['bytes'] += len(raw)
            if frame is None:
                continue
            decoded = cv2.imdecode(np.frombuffer(frame['jpeg'], np.uint8), cv2.IMREAD_COLOR)
            if decoded is None or decoded.shape[:2] != (frame['height'], frame['width']):
                with lock:
                    state['decode_errors'] += 1
                continue
            stamp = frame['received_at']
            with lock:
                if state['first'] is None:
                    state['first'] = stamp
                    state['first_frame'] = dict(sequence=frame['sequence'], capture_us=frame['capture_us'])
                if state['last'] is not None:
                    state['intervals'].append((stamp-state['last'])*1000)
                state['last'] = stamp
                state['decoded'] += 1
                state['image'] = decoded
                state['frame'] = frame
                state['message'] = 'LIVE USB VIDEO' if args.control else 'LIVE USB VIDEO - MOTORS OFF'
    except Exception as exc:
        if args.control:
            (args.control/'stop.request').write_text('USB error: hold')
        with lock:
            state['error'] = str(exc)
            state['message'] = 'USB ERROR - MOTORS OFF'
    finally:
        receiver.reset()
        if dev is not None:
            if claimed:
                try:
                    usb.util.release_interface(dev, 0)
                except usb.core.USBError:
                    pass
            usb.util.dispose_resources(dev)


worker = threading.Thread(target=read_worker, daemon=True)
worker.start()
title = 'VelaVision USB - LIVE FOLLOW TEST' if args.control else 'VelaVision USB - LIVE PREVIEW - MOTORS OFF'
mirror = True
if args.title:
    title = args.title
cv2.namedWindow(title, cv2.WINDOW_NORMAL)
cv2.resizeWindow(title, 960, 780)
cv2.moveWindow(title, 40, 40)
deadline = float("inf")
try:
    while time.monotonic() < deadline:
        with lock:
            snap = dict(state)
        now = time.monotonic()
        canvas = np.zeros((560, 640, 3), np.uint8)
        if snap['image'] is not None:
            canvas[80:] = cv2.flip(snap['image'], 1) if mirror else snap['image']
            if args.control:
                try:
                    telemetry = json.loads((args.control/'telemetry.json').read_text())
                    bounds = display_box(telemetry, snap['frame']['sequence'], now, mirror)
                    if bounds:
                        (x1,y1),(x2,y2) = bounds
                        cv2.rectangle(canvas, (x1,y1+80), (x2,y2+80), (0,255,0), 2)
                        cv2.putText(canvas, 'BOARD FACE', (x1,max(96,y1+75)), cv2.FONT_HERSHEY_SIMPLEX, .45, (0,255,0), 1)
                        edges = telemetry.get('edge', 0)
                        if edges:
                            held = ('X ' if edges & 5 else '') + ('Y' if edges & 10 else '')
                            cv2.putText(canvas, 'EDGE: '+(('X HOLD ' if edges & 5 else '') + ('Y SLOW RECOVERY' if (edges & 10) in (2,8) else ('Y HOLD' if edges & 10 else ''))), (12,546), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,200,255), 2)
                except (OSError, ValueError, KeyError):
                    pass
        age = None if snap['last'] is None else now-snap['last']
        if args.control:
            viewtmp=args.control/'view.tmp'
            viewtmp.write_text(json.dumps(dict(at=now,age=999 if age is None else age)))
            viewtmp.replace(args.control/'view.json')
        message = snap['message']
        if age is not None and age > 1:
            message = 'NO NEW FRAME - MOTORS OFF'
        phase = 'waiting'
        if args.control:
            try:
                control = json.loads((args.control/'status.json').read_text())
                message = control['label']
                phase = control['phase']
            except (OSError, ValueError, KeyError):
                message = 'WAITING FOR TEST CONTROLLER'
                phase = 'unknown'
            if snap['error']:
                message = 'USB ERROR - STOP REQUESTED'
            elif phase == 'waiting' and not ready.exists():
                message = 'CONNECT OPENVELA USB TO UBUNTU'
        cv2.putText(canvas, message, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (0,255,255), 2)
        span = 0 if snap['first'] is None else snap['last']-snap['first']
        fps = (snap['decoded']-1)/span if span > 0 else 0
        label = '640x480  {:.1f} FPS  Frames {}  CRC bad {}'.format(fps,snap['decoded'],receiver.corrupt)
        cv2.putText(canvas, label, (12, 50), cv2.FONT_HERSHEY_SIMPLEX, .55, (255,255,255), 1)
        label = 'M: mirror {} | Q/Esc: close | No motor commands'.format('ON' if mirror else 'OFF')
        if args.control:
            label = 'SPACE: start | X +/-800, mid1492us | Y unchanged | Q/Esc: stop'
        cv2.putText(canvas, label, (12, 72), cv2.FONT_HERSHEY_SIMPLEX, .48, (180,180,180), 1)
        cv2.imshow(title, canvas)
        key = cv2.waitKey(10) & 255
        if key == ord('m'):
            mirror = not mirror
        if args.control and key == ord(' ') and phase == 'waiting' and ready.exists():
            (args.control/'start.request').write_text('start')
        if key in (27, ord('q')) or cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE)<1:
            break
        if False:  # Keep the completed test visible until Q/Esc or window close.
            break
        if not args.control and snap['first'] is not None and now-snap['first']>args.seconds:
            break
finally:
    if args.control:
        (args.control/'stop.request').write_text('hold')
    stop.set()
    worker.join(timeout=3)
    cv2.destroyAllWindows()
    with lock:
        result = dict(state)
    image = result.pop('image')
    frame = result.pop('frame')
    intervals = result.pop('intervals')
    span = 0 if result['first'] is None else result['last']-result['first']
    result['received_fps'] = (result['decoded']-1)/span if span>0 else 0
    result['crc_good'] = receiver.good
    result['crc_bad'] = receiver.corrupt
    result['expired'] = receiver.expired
    result['arrival_gap_p95_ms'] = float(np.percentile(intervals,95)) if intervals else None
    if frame is not None:
        result['last_sequence'] = frame['sequence']
        result['last_capture_us'] = frame['capture_us']
        (args.output/'last.jpg').write_bytes(frame['jpeg'])
    if image is not None:
        cv2.imwrite(str(args.output/'last.png'), image)
    (args.output/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result), flush=True)
