"""Incremental binary receiver. Transport/GUI independent; returns latest frame.

The caller must call expire() when reads time out, and reset() on disconnect.
Never treat board timestamps as host timestamps. JPEG decoding belongs in a
separate display worker; malformed images must be rejected by that decoder.
"""
import struct
import time
import zlib

MAGIC = b'K7MJPG1\0'
HEADER = struct.Struct('<8sIQIHHII')
MAX_BYTES = 1024 * 1024


class Receiver:
    def __init__(self, frame_timeout=1.0):
        if frame_timeout <= 0:
            raise ValueError('positive frame timeout required')
        self.frame_timeout = frame_timeout
        self.buffer = bytearray()
        self.started = None
        self.good = self.corrupt = self.expired = 0

    def reset(self):
        self.buffer.clear()
        self.started = None

    def expire(self, now=None):
        now = time.monotonic() if now is None else now
        if self.started is not None and now - self.started >= self.frame_timeout:
            self.expired += 1
            self.reset()
            return True
        return False

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        self.expire(now)
        latest = None
        # Input reads can be arbitrarily large; never append all of them at once.
        for offset in range(0, len(data), 65536):
            self.buffer.extend(data[offset:offset + 65536])
            while True:
                pos = self.buffer.find(MAGIC)
                if pos < 0:
                    del self.buffer[:-7]
                    self.started = None
                    break
                if pos:
                    del self.buffer[:pos]
                    self.started = None
                if self.started is None:
                    self.started = now
                if len(self.buffer) < HEADER.size:
                    break
                fields = HEADER.unpack_from(self.buffer)
                _, seq, stamp, size, width, height, crc, header_crc = fields
                valid_header = (
                    zlib.crc32(self.buffer[:32]) == header_crc and
                    4 <= size <= MAX_BYTES and 0 < width <= 4096 and
                    0 < height <= 4096)
                if not valid_header:
                    self.corrupt += 1
                    del self.buffer[:1]
                    self.started = None
                    continue
                end = HEADER.size + size
                if len(self.buffer) < end:
                    break
                payload = bytes(self.buffer[HEADER.size:end])
                if (zlib.crc32(payload) != crc or
                        payload[:2] != b'\xff\xd8' or payload[-2:] != b'\xff\xd9'):
                    self.corrupt += 1
                    del self.buffer[:1]
                    self.started = None
                    continue
                self.good += 1
                latest = {'sequence': seq, 'capture_us': stamp, 'width': width,
                          'height': height, 'jpeg': payload, 'received_at': now}
                del self.buffer[:end]
                self.started = None
        return latest
