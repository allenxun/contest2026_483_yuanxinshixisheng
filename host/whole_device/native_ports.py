"""Compose the actual motion and exact-frame capture adapters.

Speech must provide async say(text, generation) and stop(). The production
player is mandatory; no silent-success speech implementation is supplied.
Camera/USB initialization stays with the application that owns FrameCache.
"""
import json
from pathlib import Path
from .native_motion import NativeMotion
from .photo_capture import PhotoCapture


class NativePorts:
    def __init__(self, serial, cache, photo_directory, speech):
        if not callable(getattr(speech, 'say', None)) or not callable(getattr(speech, 'stop', None)):
            raise TypeError('real_speech_adapter_required')
        self.motion = NativeMotion(serial)
        self.photos = PhotoCapture(serial, self.motion, cache, photo_directory)
        self.speech = speech
        self.prompts = json.loads(Path(__file__).with_name('voice_prompts.zh-CN.json').read_text(encoding='utf8'))

    async def announce(self, key, generation):
        await self.speech.say(self.prompts[key], generation)

    async def start_tracking(self, generation):
        return await self.motion.set_mode('track')

    async def stop_tracking(self):
        return await self.motion.stop()

    async def stop_audio(self):
        await self.speech.stop()

    async def capture_views(self, generation):
        source = self.photos.events()
        try:
            async for event in source:
                yield event
        finally:
            await source.aclose()
