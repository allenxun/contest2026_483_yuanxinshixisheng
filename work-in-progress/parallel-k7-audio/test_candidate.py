import unittest
from audio_candidate import *

class Backend:
    def __init__(self,fail=None,ack=True):self.fail=fail;self.ack=ack;self.actions=[];self.exited=False
    def perform(self,action,tx,profile):
        self.actions.append(action)
        if action==self.fail:raise RuntimeError('injected hardware I/O failure')
        return True
    def quiesce(self,tx):self.exited=self.ack;return self.ack

class Tests(unittest.TestCase):
    def test_profile(self):
        self.assertEqual(BoardProfile().bclk,512000)
        for rate in [0,8000,48000]:
            with self.assertRaises(ValueError):BoardProfile(rate=rate).validate()
    def test_identity_gate(self):
        b=Backend();s=CaptureSession(b)
        with self.assertRaises(ValueError):s.start(lambda:0,10)
        self.assertFalse(b.actions)
    def test_success_busy_stop(self):
        b=Backend();s=CaptureSession(b);self.assertTrue(s.start(lambda:0,10,True))
        self.assertFalse(s.start(lambda:0,10,True));self.assertNotIn('amp_enable',b.actions)
        self.assertTrue(s.stop());self.assertTrue(b.exited)
    def test_each_failure_waits_for_cleanup(self):
        b=Backend();s=CaptureSession(b);s.start(lambda:0,100,True);s.stop()
        for fail in b.actions:
            with self.subTest(fail=fail):
                f=Backend(fail,False);s=CaptureSession(f)
                self.assertFalse(s.start(lambda:0,100,True));self.assertEqual(s.state,State.DRAINING)
                self.assertFalse(s.start(lambda:0,100,True));self.assertFalse(s.release_ack(0))
                self.assertTrue(s.release_ack(1));self.assertEqual(s.state,State.IDLE)
    def test_timeout_after_block(self):
        ticks=iter([0,0,20]);b=Backend(ack=False);s=CaptureSession(b)
        self.assertFalse(s.start(lambda:next(ticks),10,True));self.assertEqual(b.actions,['amp_disable'])
        self.assertEqual(s.state,State.DRAINING);self.assertIn('TimeoutError',s.error)
    def test_deadline_before_start(self):
        b=Backend();s=CaptureSession(b);self.assertFalse(s.start(lambda:10,10,True));self.assertFalse(b.actions)
    def test_stereo_channel_boundaries(self):
        pairs=[(-32768,32767),(32767,-32768),(-200,-400),(0,0),(1000,2000)]
        data=b''.join(x.to_bytes(2,'little',signed=True) for pair in pairs for x in pair)
        for select in ['left','right','mean']:
            expected=b''.join((a if select=='left' else b if select=='right' else int((a+b)/2)).to_bytes(2,'little',signed=True) for a,b in pairs)
            for width in range(1,len(data)+1):
                with self.subTest(select=select,width=width):
                    p=Pcm16Channels(16000,16000,2,1,select)
                    got=b''.join(p.push(data[i:i+width]) for i in range(0,len(data),width));p.finish()
                    self.assertEqual(got,expected)
    def test_mono_duplication(self):
        p=Pcm16Channels(8000,8000,1,2);self.assertEqual(p.push(b'\x00\x80'),b'\x00\x80'*2);p.finish()
    def test_reject_rate_and_truncation(self):
        with self.assertRaises(ValueError):Pcm16Channels(8000,16000,1,1)
        p=Pcm16Channels(16000,16000,2,1);p.push(b'x')
        with self.assertRaises(ValueError):p.finish()
        with self.assertRaises(ValueError):p.push(b'')
    def test_capacity_reject_keeps_pending(self):
        p=Pcm16Channels(16000,16000,1,1);p.push(b'\xff')
        with self.assertRaises(ValueError):p.push(b'x'*4097)
        self.assertEqual(p.push(b'\x7f'),b'\xff\x7f');p.finish()
    def test_packet_fraction(self):
        for rate in [8000,16000,44100,48000]:
            for ch in [1,2]:
                p=FullSpeedPacketPlan(rate,ch,192)
                self.assertEqual(sum(p.next_bytes() for _ in range(1000)),rate*ch*2)
        p=FullSpeedPacketPlan(44100,2,180)
        self.assertEqual([p.next_bytes() for _ in range(10)],[176]*9+[180])
    def test_packet_unsupported(self):
        for opts in [dict(sync='asynchronous'),dict(sync='adaptive'),dict(interval_ms=2),dict(max_packet=100)]:
            args=dict(rate=48000,channels=2,max_packet=192);args.update(opts)
            with self.assertRaises(ValueError):FullSpeedPacketPlan(**args)

if __name__=='__main__':unittest.main(verbosity=2)
