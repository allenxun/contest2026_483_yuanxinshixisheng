import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from .report_audio import deliver_report
from .report_narration import NarrationContractError


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, bad_ack=False):
        task='11111111-1111-4111-8111-111111111111'
        result={'taskId':task,'status':'report_ready','reportId':'report',
                'brief':{'conclusion':'balanced','description':None}}
        started=False; delivered=asyncio.Event(); packets=[]; synth_calls=0
        async def read(reader, limit):
            nonlocal started
            if not started:
                started=True;return b'R',task.encode()
            return (b'X' if bad_ack else b'A'), b''
        async def synth(base,text):
            nonlocal synth_calls
            synth_calls+=1
            if synth_calls>1:await delivered.wait()
            return b'\0\0'*320, 1
        async def packet(writer,kind,body):
            packets.append(kind)
            if kind==b'D':delivered.set()
        with patch.dict('os.environ',{'K7_REPORT_NARRATION_MODE':'brief'}), patch(
                'host.whole_device.report_audio.fetch_result',AsyncMock(return_value=result)):
            value=await asyncio.wait_for(deliver_report(None,None,None,read,packet,synth,'http://tts'),2)
        return value,packets

    async def test_playback_starts_before_remaining_synthesis(self):
        result, packets=await self.exercise()
        self.assertEqual(result['report_segments_played'],3)
        self.assertEqual(packets,[b'J',b'D',b'D',b'D',b'E'])

    async def test_requires_board_playback_ack(self):
        with self.assertRaisesRegex(ValueError,'not_acknowledged'):
            await self.exercise(True)

    async def test_real_sse_falls_back_to_real_brief_when_contract_missing(self):
        task='22222222-2222-4222-8222-222222222222'
        result={'taskId':task,'status':'report_ready','reportId':'report',
                'brief':{'conclusion':'balanced','description':None}}
        started=False; packets=[]; texts=[]
        async def read(reader, limit):
            nonlocal started
            if not started:
                started=True; return b'R', task.encode()
            return b'A', b''
        async def synth(base,text):
            texts.append(text)
            return b'\0\0'*320, 1
        async def packet(writer,kind,body): packets.append(kind)
        async def unavailable(*args):
            if False: yield ''
            raise NarrationContractError('UNSUPPORTED_CONTRACT')
        with patch.dict('os.environ',{'K7_REPORT_NARRATION_MODE':'real-sse'}), patch(
                'host.whole_device.report_audio.fetch_result',AsyncMock(return_value=result)), patch(
                'host.whole_device.report_narration.stream_sentences',unavailable):
            value=await asyncio.wait_for(deliver_report(None,None,None,read,packet,synth,'http://tts'),2)
        self.assertTrue(value['completed'])
        self.assertEqual(len(texts),3)
        self.assertTrue(any('balanced' in text for text in texts))
