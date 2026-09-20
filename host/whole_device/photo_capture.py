"""Real board pose -> exact USB frame -> durable save -> board acknowledgment.

The existing USB Receiver must publish to the injected FrameCache. This class
does not infer poses, open USB/serial, or substitute a recent unrelated frame.
"""
import asyncio
from pathlib import Path
from host.vision.photo_protocol import POSE, PHOTO, PHOTOQ, validate_request, save_exact


class PhotoCapture:
    def __init__(self, serial, motion, cache, directory):
        self.serial, self.motion, self.cache = serial, motion, cache
        self.directory = Path(directory)

    async def events(self):
        # A spoken prompt may take seconds; board save ACKs must not wait for
        # the speech consumer. One capture has exactly nine phase events.
        output = asyncio.Queue(12)
        async def produce():
            try:
                async for event in self._capture():
                    await output.put(event)
            except Exception as exc:
                await output.put(exc)
            else:
                await output.put(None)
        worker = asyncio.create_task(produce())
        try:
            while True:
                event = await output.get()
                if event is None: return
                if isinstance(event, Exception): raise event
                yield event
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    async def _capture(self):
        queue = self.serial.subscribe()
        pending = {}
        epoch = None
        index = 0
        views = ((1, 'front'), (2, 'left'), (4, 'right'))
        seen = set()
        try:
            if not await self.motion.set_mode('photo'):
                raise OSError('photo_mode_rejected')
            # Discard telemetry preceding the worker's mode transition.
            while True:
                line = await asyncio.wait_for(queue.get(), 8)
                if isinstance(line, Exception): raise line
                if line == 'VOICE MODE applied=2 result=0': break
            yield 'aligning', 'front'
            while index < 3:
                line = await asyncio.wait_for(queue.get(), 8)
                if isinstance(line, Exception): raise line
                pose = POSE.fullmatch(line)
                if pose:
                    current = int(pose[2])
                    if epoch is None:
                        if current <= 0: raise ValueError('invalid_photo_epoch')
                        epoch = current
                    elif current != epoch:
                        raise ValueError('photo_epoch_changed')
                photo = PHOTO.fullmatch(line)
                if photo:
                    q,e,s,y,p,r = photo.groups()
                    key = (int(q), int(e), int(s))
                    if key in seen: continue
                    if epoch is None or int(e) != epoch:
                        raise ValueError('photo_epoch_mismatch')
                    if int(s) != views[index][0]:
                        raise ValueError('unexpected_photo_side')
                    pending[int(q)] = dict(q=int(q), epoch=int(e), side=int(s),
                        raw_pose=dict(yaw=float(y),pitch=float(p),roll=float(r)))
                    if len(pending)>4: raise ValueError('too_many_photo_requests')
                quality = PHOTOQ.fullmatch(line)
                if not quality or int(quality[1]) not in pending: continue
                request = pending.pop(int(quality[1]))
                request.update(filtered_pose=dict(yaw=float(quality[2]),pitch=float(quality[3]),roll=float(quality[4])),
                               sharpness=float(quality[5]),face_size=float(quality[6]))
                validate_request(request)
                side, view = views[index]
                yield 'ready', view
                deadline = asyncio.get_running_loop().time()+.5
                frame = self.cache.get(request['q'])
                while frame is None and asyncio.get_running_loop().time()<deadline:
                    await asyncio.sleep(.02)
                    frame = self.cache.get(request['q'])
                # save_exact checks sequence, dimensions, pose, quality and
                # existing-file hash; fsync completes before a positive ACK.
                await asyncio.to_thread(save_exact, self.directory, request, frame)
                def acknowledged(line):
                    match = POSE.fullmatch(line)
                    return bool(match and int(match[2])==epoch and int(match[9]) & side)
                command = 'k7host photoack {q} {epoch} {side} 1'.format(**request)
                await self.serial.request('photo-save', command, acknowledged, timeout=5)
                seen.add((request['q'],epoch,side))
                yield 'saved', view
                index += 1
                if index < 3: yield 'aligning', views[index][1]
            if not await self.motion.set_mode('track'):
                raise OSError('tracking_resume_failed')
        finally:
            self.serial.unsubscribe(queue)
