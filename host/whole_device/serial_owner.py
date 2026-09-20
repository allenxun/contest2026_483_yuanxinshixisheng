"""One serial reader/writer shared by speech and vision adapters.

The injected port follows pyserial's read/write interface and must have finite
read/write timeouts. Reply validators belong to audited adapters, not ASR text.
Opening a hardware port is intentionally left to the application entry point.
"""
import asyncio
import time


class SerialOwner:
    def __init__(self, port, char_interval=0):
        if not 0 <= char_interval <= .02:
            raise ValueError('invalid_char_interval')
        self.port = port
        self.char_interval = char_interval
        self._reader = None
        self._writer = asyncio.Lock()
        self._pending = {}
        self._subscribers = set()
        self._closed = False

    def start(self):
        if self._reader is not None or self._closed:
            raise RuntimeError('serial_owner_already_started')
        self._reader = asyncio.create_task(self._read())

    async def _read(self):
        buffer = bytearray()
        try:
            while not self._closed:
                block = await asyncio.to_thread(self.port.read, 4096)
                if not block:
                    continue
                buffer.extend(block)
                if len(buffer) > 65536:
                    raise OSError('serial_line_overflow')
                while b'\n' in buffer:
                    raw, _, buffer = buffer.partition(b'\n')
                    line = raw.decode('utf-8', errors='replace').strip('\r')
                    for queue in list(self._subscribers):
                        if queue.full():
                            # Lost photo telemetry cannot be treated as a
                            # successful capture. Terminate only this consumer.
                            while not queue.empty(): queue.get_nowait()
                            queue.put_nowait(OSError('serial_telemetry_overflow'))
                            self._subscribers.discard(queue)
                        else:
                            queue.put_nowait(line)
                    for key, (predicate, future) in list(self._pending.items()):
                        if not future.done() and predicate(line):
                            future.set_result(line)
        except Exception:
            self._closed = True
            for _, future in self._pending.values():
                if not future.done():
                    future.set_exception(OSError('serial_read_failed'))
            self._end_subscribers('serial_read_failed')

    def subscribe(self, capacity=256):
        if self._closed or self._reader is None:
            raise OSError('serial_not_running')
        if type(capacity) is not int or not 1 <= capacity <= 4096:
            raise ValueError('invalid_capacity')
        queue = asyncio.Queue(capacity)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._subscribers.discard(queue)

    def _end_subscribers(self, reason):
        for queue in self._subscribers:
            while not queue.empty(): queue.get_nowait()
            queue.put_nowait(OSError(reason))
        self._subscribers.clear()

    async def request(self, key, command, predicate, timeout=10):
        if self._closed or self._reader is None:
            raise OSError('serial_not_running')
        if not command or len(command) > 160 or any(c in command for c in '\r\n\x00'):
            raise ValueError('invalid_command')
        command.encode('ascii')
        if key in self._pending:
            raise RuntimeError('duplicate_pending_request')
        future = asyncio.get_running_loop().create_future()
        self._pending[key] = (predicate, future)
        try:
            async with self._writer:
                if self._closed:
                    raise OSError('serial_not_running')
                # Lock only the short write, not the response wait: halt can
                # be sent while a camera-start request is waiting for readiness.
                def send():
                    data=(command+'\r').encode('ascii')
                    chunks = [data] if not self.char_interval else [bytes([b]) for b in data]
                    for chunk in chunks:
                        if self.port.write(chunk) != len(chunk):
                            raise OSError('short_serial_write')
                        if self.char_interval:
                            time.sleep(self.char_interval)
                    self.port.flush()
                sending = asyncio.create_task(asyncio.to_thread(send))
                try:
                    await asyncio.shield(sending)
                except asyncio.CancelledError:
                    # A worker thread cannot be cancelled. Keep ownership until
                    # its command finishes, so halt cannot interleave its bytes.
                    await sending
                    raise
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(key, None)
            if not future.done():
                future.cancel()

    async def close(self):
        self._closed = True
        self._end_subscribers('serial_closed')
        for _, future in self._pending.values():
            if not future.done():future.set_exception(OSError('serial_closed'))
        if self._reader is not None:
            await asyncio.gather(self._reader, return_exceptions=True)
        async with self._writer:
            await asyncio.to_thread(self.port.close)
