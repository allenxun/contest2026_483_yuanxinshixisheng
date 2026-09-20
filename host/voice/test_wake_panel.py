import unittest
import types
from unittest.mock import patch
from wake_panel import outcome
from manual_wifi import networks, success_ip, Connector

class OutcomeTests(unittest.TestCase):
    def test_password_requires_echo_off_and_is_not_reported(self):
        for ready in (True, False):
            writes = []
            replies = iter([b'nsh> ', b'VOICE_UI INPUT_READY echo=off' if ready else None,
                            b'VOICE_UI connected ip=10.3.0.214\r\n'])
            class Port:
                def __init__(self, *a, **k): pass
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def write(self, b): writes.append(bytes(b))
                def flush(self): pass
                def read(self, n):
                    value = next(replies)
                    if value is None: raise OSError('port closed before handshake')
                    return value
            updates = []
            worker = Connector(types.SimpleNamespace(port='fake'), lambda *a: updates.append(a), 'Lansee', 'TestOnly123')
            with patch.dict('sys.modules', {'serial': types.SimpleNamespace(Serial=Port)}):
                worker.run()
            self.assertEqual(b'TestOnly123' in writes, ready)
            self.assertNotIn('TestOnly123', str(updates))
            self.assertFalse(any(worker.password))
    def test_scan_and_real_ip(self):
        self.assertEqual(networks(b'VOICE AP ssid_hex=4c616e736565\r\n'), ['Lansee'])
        self.assertEqual(networks(b'VOICE AP ssid_hex=ff\n'), [])
        self.assertEqual(success_ip(b'VOICE_UI connected ip=10.3.0.214\r\n'), '10.3.0.214')
        for raw in (b'VOICE_UI connecting', b'VOICE_UI connected ip=0.0.0.0', b'VOICE_UI connected ip=127.0.0.1'):
            self.assertIsNone(success_ip(raw))
    def test_requires_board_scan_state(self):
        prefix = 'VOICE_FLOW wake_text=你好联网 bytes=12\n'.encode()
        self.assertEqual(outcome(prefix), ('你好联网', False))
        self.assertEqual(outcome(prefix + b'VOICE_FLOW mic_state=2 grammar=1 count=4\n'), ('你好联网', True))
    def test_rejects_missing_list_and_partial_console(self):
        for raw in (b'VOICE_FLOW mic_state', b'VOICE_FLOW mic_state=2 grammar=1 count=0',
                    b'VOICE_FLOW mic_state=0 grammar=0 count=4', b'VOICE_FLOW asr_error=-61'):
            self.assertFalse(outcome(raw)[1])
    def test_latest_complete_result_wins(self):
        self.assertFalse(outcome(b'VOICE_FLOW mic_state=2 grammar=1 count=4\nVOICE_FLOW mic_state=0 grammar=0 count=0')[1])

if __name__ == '__main__':
    unittest.main()
