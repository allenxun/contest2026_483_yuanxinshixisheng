"""Offline legacy UART contract candidate. No transport/device access.

Sequence values are local transaction IDs, never transmitted or acknowledged.
All times are caller-provided monotonic integer milliseconds. Single-owner API.
"""
from collections import deque
from dataclasses import dataclass

CAPABILITIES = dict(wire='legacy-7-byte', can='unsupported', ack='unsupported',
                    wire_sequence='unsupported', measured_position='unsupported',
                    motor_disable='unsupported', checksum='unsupported')

def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside contract range')
    return value

def encode_axis(axis, target, reserved=0):
    if axis not in (0, 255) or type(axis) is not int:
        raise ValueError('axis')
    integer(target, -32768, 32767)
    integer(reserved, 0, 255)
    return bytes((0x55, 0xaa, axis)) + target.to_bytes(2, 'little', signed=True) + bytes((reserved, 0xfa))

def encode_pair(x, y):
    # Match gimbal_link_pack, not a new motion safety envelope.
    integer(x, -800, 800)
    integer(y, -200, 1030)
    return encode_axis(0, x) + encode_axis(255, y)

def decode_frame(frame):
    if len(frame) != 7 or frame[:2] != b'\x55\xaa' or frame[2] not in (0, 255) or frame[6] != 0xfa:
        raise ValueError('structure')
    # MCU deliberately accepts any reserved value; do not reinterpret it as CRC.
    return frame[2], int.from_bytes(frame[3:5], 'little', signed=True), frame[5]

class Parser:
    """Bounded sliding window; feed returns count, pop drains bounded frame queue.

    Host diagnostic parser for command streams, NOT an MCU telemetry parser.
    On queue overflow reject newest complete frame and count it. Maximum retained
    input is 6 bytes after feed, 7 transiently, regardless of input size.
    """
    def __init__(self, capacity=16, gap_ms=50):
        self.capacity = integer(capacity, 1, 4096)
        self.gap_ms = integer(gap_ms, 1, 60000)
        self.buffer = bytearray()
        self.frames = deque()
        self.last = None
        self.now = 0
        self.dropped = self.invalid = self.expired = 0

    def tick(self, now):
        integer(now, self.now, 2**63-1)
        self.now = now
        if self.last is not None and now - self.last >= self.gap_ms:
            if self.buffer:
                self.expired += 1
            self.buffer.clear()
            self.last = None

    def feed(self, data, now):
        self.tick(now)
        accepted = 0
        for value in data:
            self.last = now
            self.buffer.append(value)
            if len(self.buffer) < 7:
                continue
            try:
                frame = decode_frame(bytes(self.buffer))
            except ValueError:
                del self.buffer[0]
                self.invalid += 1
                continue
            self.buffer.clear()
            if len(self.frames) == self.capacity:
                self.dropped += 1
            else:
                self.frames.append(frame)
                accepted += 1
        return accepted

    def pop(self):
        return self.frames.popleft() if self.frames else None

    def disconnect(self):
        self.buffer.clear()
        self.frames.clear()
        self.last = None

@dataclass
class Pending:
    sequence: int
    wire: bytes
    deadline: int
    offset: int = 0

class Session:
    """Pure local write simulator: enqueue -> pending_bytes -> accept_write.

    Does not call serial, sockets, files, or clocks. Deadlines include queue time.
    Fault flushes all pending items; no automatic replay on reconnect. History is
    bounded to capacity. 'host_write_complete' is not device receipt/execution.
    """
    def __init__(self, capacity=8, timeout_ms=50):
        self.capacity = integer(capacity, 1, 4096)
        self.timeout = integer(timeout_ms, 1, 60000)
        self.queue = deque()
        self.history = deque(maxlen=capacity)
        self.next_sequence = 0
        self.now = 0
        self.connected = False
        self.fault = None

    def tick(self, now):
        integer(now, self.now, 2**63-1)
        self.now = now
        if self.queue and now >= self.queue[0].deadline:
            self.disconnect('timeout')

    def connect(self):
        if self.connected:
            raise RuntimeError('already connected')
        self.connected = True
        self.fault = None

    def enqueue(self, x, y, now):
        self.tick(now)
        if not self.connected:
            raise ConnectionError('disconnected')
        wire = encode_pair(x, y)
        if len(self.queue) >= self.capacity:
            raise BufferError('queue full: newest rejected')
        # Deliberately never wrap/reuse a local ID during this object's lifetime.
        if self.next_sequence == 2**64:
            raise OverflowError('local sequence exhausted')
        seq = self.next_sequence
        self.next_sequence += 1
        self.queue.append(Pending(seq, wire, now + self.timeout))
        return seq

    def pending_bytes(self, now):
        self.tick(now)
        if not self.queue:
            return b''
        return self.queue[0].wire[self.queue[0].offset:]

    def accept_write(self, count, now):
        self.tick(now)
        if not self.queue:
            raise ConnectionError('no pending write')
        p = self.queue[0]
        integer(count, 0, len(p.wire) - p.offset)
        p.offset += count
        if p.offset == len(p.wire):
            self.queue.popleft()
            self.history.append((p.sequence, 'host_write_complete', p.offset))

    def disconnect(self, reason='disconnected'):
        self.connected = False
        self.fault = reason
        while self.queue:
            p = self.queue.popleft()
            self.history.append((p.sequence, reason, p.offset))

    def halt(self):
        # Cancels local work; partial axis/pair may already have left host.
        self.disconnect('host_halt_device_state_unknown')

    def acknowledge(self, sequence):
        raise NotImplementedError('legacy UART has no device ACK or wire sequence')

def pwm_simulation(x, y):
    """Read-only arithmetic model of Servo_ApplyLegacy; C truncates toward zero."""
    integer(x, -32768, 32767)
    integer(y, -32768, 32767)
    return (max(500, min(2500, 1492 + int(-x * 12 / 10))),
            max(500, min(2300, 700 + int(y * 15 / 10))))

def pid_step(target, current, integral, last_error, kp, ki, kd):
    """Mathematical model of unused positional PID; not a tuning recommendation."""
    error = target - current
    integral = max(-7000, min(7000, integral + error))
    return kp * error + ki * integral + kd * (error-last_error), integral, error
