"""Display only: decode board telemetry, never generate motion commands."""
import json
import math
import re
import time

BOX = re.compile(r'TRACK BOX q=(\d+) x=([\d.-]+) y=([\d.-]+) w=([\d.-]+) h=([\d.-]+) edge=(\d+)')
TRACK = re.compile(r'TRACK q=(\d+) s=(\d+) dx=([\d.-]+) dy=([\d.-]+) x=(-?\d+) y=(-?\d+) tx=(\d+) age=(\d+)')

class Telemetry:
    def __init__(self, directory):
        self.directory = directory
        self.buffer = ''
        self.box = None

    def feed(self, data):
        self.buffer += data.decode('ascii', errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            match = BOX.search(line)
            if match:
                q, x, y, w, h, edge = match.groups()
                box = [float(v) for v in (x, y, w, h)]
                if all(math.isfinite(v) for v in box) and 0 <= box[0] < 160 and 0 <= box[1] < 120 and 0 < box[2] <= 160 and 0 < box[3] <= 120:
                    self.box = dict(sequence=int(q), box=box, edge=int(edge))
            match = TRACK.search(line)
            if match:
                q, state, dx, dy, x, y, tx, age = match.groups()
                record = dict(sequence=int(q), state=int(state), x=int(x), y=int(y), tx=int(tx), received_at=time.monotonic())
                if self.box and self.box['sequence'] == int(q):
                    record.update(self.box)
                temporary = self.directory/'telemetry.tmp'
                temporary.write_text(json.dumps(record))
                temporary.replace(self.directory/'telemetry.json')
        self.buffer = self.buffer[-16384:]

def display_box(record, sequence, now, mirror):
    # A box is an approximately aligned board result, not host inference.
    # Drop stale/out-of-order telemetry instead of showing a stuck face box.
    if 'box' not in record or not 0 <= now-record['received_at'] <= .35 or not 0 <= sequence-record['sequence'] <= 10:
        return None
    x, y, w, h = record['box']
    x1, y1 = max(0, int(x*4)), max(0, int(y*4))
    x2, y2 = min(639, int((x+w)*4)), min(479, int((y+h)*4))
    if mirror:
        x1, x2 = 639-x2, 639-x1
    return (x1,y1), (x2,y2)
