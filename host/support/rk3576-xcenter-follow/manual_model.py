"""Manual calibration in legacy MCU units; no hardware I/O."""
import time

LIMITS = {'x': (-800, 800), 'y': (-120, 1030)}
DIRECTIONS = {'a': (-1, 0), 'd': (1, 0), 'w': (0, 1), 's': (0, -1)}
MARKS = {'c': 'center', '1': 'xmin', '2': 'xmax', '3': 'ymin', '4': 'ymax'}


def move(x, y, key, step):
    if key not in DIRECTIONS or type(step) is not int or step not in (5, 20):
        raise ValueError('invalid jog')
    dx, dy = DIRECTIONS[key]
    nx, ny = x + dx * step, y + dy * step
    if not LIMITS['x'][0] <= nx <= LIMITS['x'][1] or not LIMITS['y'][0] <= ny <= LIMITS['y'][1]:
        raise ValueError('software pulse boundary')
    return nx, ny


def pulse(x, y):
    # Match signed C integer division (truncate toward zero).
    return 1492 - int(12*x/10), 700 + int(15*y/10)


def validate(marks):
    if set(marks) != set(MARKS.values()):
        return False, 'SAVE CENTER AND ALL FOUR LIMITS FIRST'
    cx, cy = marks['center']
    if not LIMITS['x'][0] <= marks['xmin'] < cx < marks['xmax'] <= LIMITS['x'][1]:
        return False, 'X MIN < CENTER < X MAX REQUIRED'
    if not LIMITS['y'][0] <= marks['ymin'] < cy < marks['ymax'] <= LIMITS['y'][1]:
        return False, 'Y MIN < CENTER < Y MAX REQUIRED'
    if min(cx-marks['xmin'], marks['xmax']-cx, cy-marks['ymin'], marks['ymax']-cy) < 20:
        return False, 'LEAVE AT LEAST 20 UNITS EACH SIDE'
    return True, 'CALIBRATION SAVED - HOLD POSITION'


def fresh(request, last_id, now=None):
    now = time.monotonic() if now is None else now
    try:
        return (type(request['id']) is int and request['id'] > last_id and
                0 <= now-request['at'] <= .35 and
                request['key'] in set(DIRECTIONS) | set(MARKS) | {'save'})
    except (KeyError, TypeError):
        return False


def resume_state(record):
    if record.get('schema') != 1 or record.get('mcu') != 'STM32F103RCT6-v1.3-xcenter':
        raise ValueError('incompatible calibration record')
    xy = record.get('last_requested')
    if not isinstance(xy, list) or len(xy) != 2:
        raise ValueError('missing last requested target')
    for axis, value in zip(('x','y'), xy):
        if type(value) is not int or not LIMITS[axis][0] <= value <= LIMITS[axis][1]:
            raise ValueError('last target outside bounds')
    marks = record.get('marks', {})
    if not isinstance(marks, dict) or not set(marks) <= set(MARKS.values()):
        raise ValueError('invalid marks')
    for name, value in marks.items():
        values = value if name == 'center' else [value]
        axes = ('x','y') if name == 'center' else (name[0],)
        if not isinstance(values, list) or len(values) != len(axes):
            raise ValueError('invalid mark')
        for axis, val in zip(axes, values):
            if type(val) is not int or not LIMITS[axis][0] <= val <= LIMITS[axis][1]:
                raise ValueError('mark outside bounds')
    return xy[0], xy[1], marks.copy()
