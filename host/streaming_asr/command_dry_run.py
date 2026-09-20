"""Explicit audio-only command test. No device, motion, backend or serial APIs."""
import time
import unicodedata

class CommandDryRun:
    def __init__(self, pcm, elapsed_ms=0, clock=time.monotonic, photo_pcm=None):
        self.pcm = bytes(pcm)
        if not self.pcm or len(self.pcm) % 2 or len(self.pcm) > 960000:
            raise ValueError('invalid_cached_prompt')
        self.photo_pcm = bytes(photo_pcm) if photo_pcm is not None else None
        if self.photo_pcm is not None and (not self.photo_pcm or len(self.photo_pcm) % 2 or len(self.photo_pcm) > 960000):
            raise ValueError('invalid_cached_prompt')
        self.clock = clock
        self.clear()

    def clear(self):
        self.pending = None
        self.outcome = {}

    def completed(self, text):
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError('invalid_command_text')
        self.pending = (self.clock(), text)

    async def reply(self, service, synthesize):
        pending, self.pending = self.pending, None
        self.outcome = {'chat_reply_kind': 'command_dry_run', 'motion_enabled': False}
        if pending is None or self.clock() - pending[0] > 60:
            raise ValueError('no_fresh_chat_question')
        text = ''.join(c for c in pending[1] if not c.isspace() and not unicodedata.category(c).startswith('P'))
        pcm = self.pcm if text == '启动云台' else self.photo_pcm if text == '开始拍照' else None
        matched = pcm is not None
        self.outcome.update(command_matched=matched, prompt_cache_hit=matched)
        if not matched:
            return None
        return pcm, 0
