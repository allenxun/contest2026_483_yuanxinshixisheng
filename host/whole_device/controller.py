"""Single owner of voice task state; hardware ports are explicit dependencies.

start_tracking/stop_tracking return True only after their readiness/stop checks.
capture_views yields (phase, view) from real telemetry and confirmed files.
No raw shell commands, backend access, or implicit motor operation on import.
"""
import asyncio


class DeviceController:
    def __init__(self, ports):
        self.ports = ports
        self.state = 'voice_ready'
        self.generation = 0
        self.operation = None
        self.stopping = False

    def _current(self, generation):
        if generation != self.generation:
            raise asyncio.CancelledError()

    async def _say(self, key, generation):
        self._current(generation)
        await self.ports.announce(key, generation)
        self._current(generation)

    async def _halt(self):
        # Audio cancellation can involve network cleanup. Dispatch the motor
        # hold concurrently instead of delaying it behind that cleanup.
        results = await asyncio.gather(self.ports.stop_audio(),
                                       self.ports.stop_tracking(),
                                       return_exceptions=True)
        return not isinstance(results[0], BaseException) and results[1] is True

    def start(self, intent):
        """Schedule an explicit start; a duplicate/busy request does not restart."""
        if intent not in ('tracking_start', 'assessment_start'):
            raise ValueError('unsupported_start')
        if self.stopping or (self.operation is not None and not self.operation.done()):
            return False
        if intent == 'tracking_start' and self.state == 'tracking':
            return False
        if self.state not in ('voice_ready', 'tracking'):
            return False
        self.generation += 1
        self.operation = asyncio.create_task(self._run(intent, self.generation))
        return True

    async def _run(self, intent, generation):
        try:
            if self.state != 'tracking':
                self.state = 'starting'
                await self._say('tracking_starting', generation)
                ready = await self.ports.start_tracking(generation)
                self._current(generation)
                if ready is not True:
                    raise RuntimeError('tracking_not_ready')
                self.state = 'tracking'
                await self._say('tracking_ready', generation)
            if intent == 'tracking_start':
                return
            self.state = 'capturing'
            await self._say('assessment_starting', generation)
            views = ('front', 'left', 'right')
            index, step, previous = 0, 0, None
            phases = ('aligning', 'ready', 'saved')
            source = self.ports.capture_views(generation)
            try:
                async for phase, view in source:
                    self._current(generation)
                    if (phase, view) == previous:
                        continue
                    # Accept only the expected phase of this view. Ignore exact
                    # repeated telemetry, reject out-of-order advancement.
                    if index >= 3:
                        raise RuntimeError('extra_capture_event')
                    if view == views[index] and phase in phases[:step]:
                        continue
                    if view != views[index] or phase != phases[step]:
                        raise RuntimeError('unexpected_capture_event')
                    await self._say(view + '_' + phase, generation)
                    previous = (phase, view)
                    step += 1
                    if step == 3:
                        index += 1
                        step = 0
                if index != 3:
                    raise RuntimeError('incomplete_capture')
            finally:
                close = getattr(source, 'aclose', None)
                if close:
                    await close()
            self.state = 'tracking'
            # Backend deliberately deferred. Do not announce uploading.
            await self._say('capture_saved_local', generation)
        except asyncio.CancelledError:
            raise
        except Exception:
            if generation == self.generation:
                stopped = await self._halt()
                self.state = 'voice_ready' if stopped is True else 'stop_unconfirmed'
                await self._say('task_failed' if stopped is True else 'stop_failed', generation)

    async def stop(self):
        if self.stopping:
            return False
        self.stopping = True
        self.generation += 1
        generation = self.generation
        pending = self.operation
        if pending is not None and not pending.done():
            pending.cancel()
        self.state = 'stopping'
        try:
            # Neither cloud synthesis nor an active photo task delays this call.
            stopped = await self._halt()
            self.state = 'voice_ready' if stopped is True else 'stop_unconfirmed'
            await self._say('tracking_stopped' if stopped is True else 'stop_failed', generation)
            return stopped is True
        finally:
            if pending is not None:
                await asyncio.gather(pending, return_exceptions=True)
            self.stopping = False
