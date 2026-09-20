import asyncio
import unittest
from .report_speech import ReportNarrator, ReportStreamError, SentenceBuffer


def event(kind, seq, **extra):
    return dict(type=kind, seq=seq, requestId='request', reportId='report', **extra)


class ReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.spoken=[];self.stops=0
        async def synth(text):return text.encode('utf-16-le')
        async def play(pcm):self.spoken.append(pcm.decode('utf-16-le'))
        async def stop():self.stops+=1
        self.narrator=ReportNarrator(synth,play,stop)

    async def test_first_sentence_plays_before_stream_done(self):
        played=asyncio.Event()
        original=self.narrator.play
        async def play(pcm):await original(pcm);played.set()
        self.narrator.play=play
        async def source():
            yield event('start',0)
            yield event('text_delta',1,text='第一')
            yield event('text_delta',2,text='句。')
            await asyncio.wait_for(played.wait(),1)
            yield event('text_delta',3,text='第二句')
            yield event('done',4)
        stats=await self.narrator.run(source(),'request','report')
        self.assertEqual(self.spoken,['第一句。','第二句'])
        self.assertEqual(stats['played'],2)

    async def test_wrong_report_and_duplicate_sequence_rejected(self):
        for bad in [dict(event('text_delta',1,text='错误。'),reportId='old'),event('text_delta',0,text='错误。')]:
            async def source():
                yield event('start',0)
                yield bad
            with self.assertRaises(ReportStreamError):await self.narrator.run(source(),'request','report')
        self.assertEqual(self.spoken,[])

    async def test_stop_drops_late_synthesis_and_allows_next_session(self):
        began=asyncio.Event()
        async def slow(text):
            began.set()
            try:await asyncio.sleep(100)
            except asyncio.CancelledError:return b'\0\0'
        self.narrator.synthesize=slow
        async def source():
            yield event('start',0)
            yield event('text_delta',1,text='旧句。')
            await asyncio.sleep(100)
        task=asyncio.create_task(self.narrator.run(source(),'request','report'))
        await began.wait();await self.narrator.stop()
        self.assertTrue(task.cancelled());self.assertEqual(self.spoken,[])
        async def empty():
            yield event('start',0);yield event('done',1)
        result=await self.narrator.run(empty(),'request','report')
        self.assertEqual(result['played'],0)

    async def test_unfinished_stream_fails(self):
        async def source():yield event('start',0)
        with self.assertRaises(ReportStreamError):await self.narrator.run(source(),'request','report')

    def test_long_sentence_is_bounded(self):
        parts=SentenceBuffer().feed('字'*200,final=True)
        self.assertEqual(''.join(parts),'字'*200)
        self.assertLessEqual(max(map(len,parts)),64)


if __name__=='__main__':unittest.main()
