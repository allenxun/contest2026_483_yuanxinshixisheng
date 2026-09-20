import unittest
import asyncio
from .native_speech import NativeSpeech


class Serial:
    def __init__(self, states):self.states=list(states);self.commands=[];self.queue=asyncio.Queue()
    def subscribe(self):return self.queue
    def unsubscribe(self,q):pass
    async def request(self,key,command,predicate,timeout):
        self.commands.append(command)
        if key=='speech-start':
            line='K7CLOUD prompt_started busy=1'
            self.queue.put_nowait('K7CLOUD prompt_done result=0')
        elif key=='speech-stop':line='K7CLOUD tts_stop requested=1'
        else:line=self.states.pop(0)
        assert predicate(line)
        return line


class NativeSpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_key_no_raw_text_in_serial(self):
        serial=Serial([]);speech=NativeSpeech(serial,'10.3.1.125')
        await speech.say('正面角度已达标。',1)
        self.assertEqual(serial.commands,['k7cloud tts-prompt 10.3.1.125 front_ready &'])
        with self.assertRaises(ValueError):await speech.say('未知命令; reboot',2)

    async def test_request_not_completion(self):
        serial=Serial(['K7CLOUD tts_state busy=1 result=0 cancelled=0',
                       'K7CLOUD tts_state busy=0 result=-125 cancelled=1'])
        await NativeSpeech(serial,'10.3.1.125').stop()
        self.assertEqual(serial.commands.count('k7cloud tts-state'),2)

    async def test_cleanup_failure_not_claimed_stopped(self):
        serial=Serial(['K7CLOUD tts_state busy=0 result=-5 cancelled=0'])
        with self.assertRaisesRegex(OSError,'cleanup_unconfirmed'):
            await NativeSpeech(serial,'10.3.1.125').stop()

    async def test_stop_waits_for_background_start_handshake(self):
        serial=Serial(['K7CLOUD tts_state busy=0 result=-125 cancelled=1'])
        speech=NativeSpeech(serial,'10.3.1.125')
        release=asyncio.Event()
        async def delayed_start():await release.wait();return 'K7CLOUD prompt_started busy=1'
        speech.starting=asyncio.create_task(delayed_start())
        stopping=asyncio.create_task(speech.stop())
        await asyncio.sleep(.01)
        self.assertEqual(serial.commands,[])
        release.set();await stopping
        self.assertEqual(serial.commands[0],'k7cloud tts-stop')

    async def test_uncertain_start_still_sends_stop_but_never_claims_safe(self):
        serial=Serial(['K7CLOUD tts_state busy=0 result=0 cancelled=0'])
        speech=NativeSpeech(serial,'10.3.1.125')
        async def failed():raise TimeoutError('start lost')
        speech.starting=asyncio.create_task(failed())
        with self.assertRaisesRegex(OSError,'start_unconfirmed'):await speech.stop()
        self.assertEqual(serial.commands[0],'k7cloud tts-stop')
