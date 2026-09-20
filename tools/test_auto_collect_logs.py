import unittest
from auto_collect_logs import ROOT, collect, in_scope

class ScopeTests(unittest.TestCase):
    def test_scope(self):
        self.assertTrue(in_scope(ROOT))
        self.assertTrue(in_scope(ROOT/'app'))
        self.assertTrue(in_scope(ROOT.parent))
        self.assertFalse(in_scope(ROOT.parent/'another-project'))
        self.assertFalse(in_scope(str(ROOT)+'-other'))

    def test_other_workspace_never_reads_transcript(self):
        self.assertEqual(collect({'hook_event_name':'Stop', 'cwd':str(ROOT.parent/'other')})['status'], 'skipped')

    def test_subagent_event_is_skipped(self):
        self.assertEqual(collect({'hook_event_name':'SubagentStop', 'cwd':str(ROOT)})['status'], 'skipped')

    def test_invalid_id_is_rejected(self):
        with self.assertRaises(ValueError):
            collect({'hook_event_name':'Stop', 'cwd':str(ROOT), 'session_id':'../../escape'})

if __name__ == '__main__':
    unittest.main()
