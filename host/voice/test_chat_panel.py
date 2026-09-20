import unittest
from host.voice.chat_panel import Status
class StatusTests(unittest.TestCase):
    def test_only_loop_terminal_completes_session(self):
        s=Status()
        self.assertIsNone(s.line('K7CLOUD asr result=0 frames_sent=150 completed=1'))
        self.assertFalse(s.finished)
        self.assertIsNone(s.line('K7CLOUD prompt_done result=0'))
        self.assertFalse(s.finished)
        self.assertIn('已结束',s.line('K7CLOUD chat loop_done=0')[0])
        self.assertTrue(s.finished)
    def test_cue_log_is_after_capture_not_start(self):
        s=Status()
        self.assertIn('听短音',s.line('K7CLOUD chat listening round=2')[0])
        self.assertEqual(s.round,2)
        self.assertIn('录音结束',s.line('SOUND cue frames=3200 stop=0')[0])
    def test_cancel_and_failure_not_reported_success(self):
        s=Status();self.assertEqual(s.line('K7CLOUD chat loop_done=-125')[0],'已停止')
        s=Status();self.assertIn('暂停',s.line('K7CLOUD chat loop_done=-22')[0]);self.assertEqual(s.result,-22)
    def test_unrelated_logs_do_not_change_state(self):
        s=Status()
        for line in ['RADIO ack=1','SOUND result=0','nsh>','Error']:
            self.assertIsNone(s.line(line))
        self.assertFalse(s.finished)


class RunnerTests(unittest.TestCase):
    def execute(self, replies, fail_open=False):
        import tempfile,itertools,types
        from unittest.mock import patch
        from pathlib import Path
        from host.voice.chat_panel import Runner
        class Port:
            def __init__(self,**kwargs):self.is_open=False;self.written=[];self.closed=False
            def open(self):
                if fail_open:raise OSError('serial unavailable')
                self.is_open=True
            def read(self,n):
                item=replies.pop(0) if replies else b''
                if isinstance(item,Exception):raise item
                return item
            def write(self,b):self.written.append(b);return len(b)
            def flush(self):pass
            def close(self):self.is_open=False;self.closed=True
        port=Port();updates=[]
        with tempfile.TemporaryDirectory() as d:
            args=types.SimpleNamespace(logs=Path(d),port='fake',gateway='127.0.0.1',rounds=1)
            runner=Runner(args,lambda *values:updates.append(values))
            with patch.dict('sys.modules',{'serial':types.SimpleNamespace(Serial=lambda **kw:port)}),patch('host.voice.chat_panel.time.monotonic',side_effect=itertools.count()):
                runner.run()
        return runner,port,updates

    def test_success_releases_port_without_stop(self):
        r,p,u=self.execute([b'nsh>',b'K7CLOUD chat listening round=1\nK7CLOUD chat loop_done=0\n'])
        self.assertTrue(r.safe and p.closed)
        self.assertEqual(sum(b'chat-loop' in x for x in p.written),1)
        self.assertFalse(any(b'device-stop' in x for x in p.written))

    def test_open_error_never_starts_capture(self):
        r,p,u=self.execute([],True)
        self.assertFalse(r.started);self.assertFalse(p.written);self.assertTrue(r.safe)

    def test_io_error_attempts_stop_and_accepts_terminal_ack(self):
        r,p,u=self.execute([b'nsh>',OSError('read failed'),b'K7CLOUD chat loop_done=-125\n'])
        self.assertTrue(r.safe and p.closed)
        self.assertTrue(any(b'device-stop' in x for x in p.written))

    def test_missing_ack_disables_restart(self):
        r,p,u=self.execute([b'nsh>',OSError('read failed')])
        self.assertFalse(r.safe);self.assertTrue(p.closed)
        self.assertIs(u[-1][-1],False)
