"""Stage prompt playback and confirmed stop through the single serial owner."""
import asyncio
import ipaddress
import json
from pathlib import Path
import re


class NativeSpeech:
    def __init__(self, serial, bridge_ip):
        self.serial=serial
        self.ip=str(ipaddress.IPv4Address(bridge_ip))
        prompts=json.loads(Path(__file__).with_name('voice_prompts.zh-CN.json').read_text(encoding='utf8'))
        self.keys={text:key for key,text in prompts.items()}
        self.lock=asyncio.Lock()
        self.starting=None

    async def say(self, text, generation):
        key=self.keys.get(text)
        if key is None:raise ValueError('unknown_stage_prompt')
        async with self.lock:
            events=self.serial.subscribe()
            self.starting=asyncio.create_task(self.serial.request('speech-start',f'k7cloud tts-prompt {self.ip} {key} &',
                lambda line:line=='K7CLOUD prompt_started busy=1' or bool(re.fullmatch(r'K7CLOUD prompt_done result=-?\d+',line)),timeout=12))
            try:
                line=await asyncio.shield(self.starting)
                if line!='K7CLOUD prompt_started busy=1':raise OSError('prompt_start_failed')
                async with asyncio.timeout(60):
                    while True:
                        line=await events.get()
                        if isinstance(line,Exception):raise line
                        if re.fullmatch(r'K7CLOUD prompt_done result=-?\d+',line):break
                if line!='K7CLOUD prompt_done result=0':raise OSError('prompt_playback_failed')
            finally:
                # A background NSH job must enter busy before a stop can safely
                # conclude idle; otherwise it could start after that conclusion.
                await asyncio.gather(self.starting,return_exceptions=True)
                self.serial.unsubscribe(events)

    async def stop(self):
        start_uncertain=False
        if self.starting is not None:
            try:await asyncio.shield(self.starting)
            except Exception:start_uncertain=True
        await self.serial.request('speech-stop','k7cloud tts-stop',
            lambda line:line=='K7CLOUD tts_stop requested=1',timeout=3)
        deadline=asyncio.get_running_loop().time()+15
        while asyncio.get_running_loop().time()<deadline:
            line=await self.serial.request('speech-state','k7cloud tts-state',
                lambda line:bool(re.fullmatch(r'K7CLOUD tts_state busy=[01] result=-?\d+ cancelled=[01]',line)),timeout=2)
            match=re.fullmatch(r'K7CLOUD tts_state busy=([01]) result=(-?\d+) cancelled=([01])',line)
            if match[1]=='0':
                if start_uncertain:raise OSError('speech_start_unconfirmed')
                if match[2]=='0' or match[3]=='1':return
                raise OSError('speech_cleanup_unconfirmed')
            await asyncio.sleep(.05)
        raise TimeoutError('speech_stop_timeout')
