import unittest
import tempfile
import os
from pathlib import Path
from log_daily import partition, write_session

class DailyLayout(unittest.TestCase):
    def test_new_day_does_not_rewrite_history(self):
        sid='01a07ed4-3f0d-7450-8bb1-bb756849cb4e'
        events=[{'ts':'2026-09-09T01:00:00Z','seq':0}]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            parts=write_session(root,'tester',sid,events,events[0]['ts'])
            old=root/parts[0]['file_path']
            os.utime(old,ns=(1000000000000000000,1000000000000000000))
            old_time=old.stat().st_mtime_ns
            directory_time=old.parent.stat().st_mtime_ns
            events.append({'ts':'2026-09-10T01:00:00Z','seq':1})
            parts=write_session(root,'tester',sid,events,events[0]['ts'])
            self.assertEqual(old.stat().st_mtime_ns,old_time)
            self.assertEqual(old.parent.stat().st_mtime_ns,directory_time)
            new=root/parts[-1]['file_path']
            before=new.read_bytes()
            events.append({'ts':'2026-09-10T02:00:00Z','seq':2})
            write_session(root,'tester',sid,events,events[0]['ts'])
            self.assertNotEqual(new.read_bytes(),before)
            self.assertEqual(old.stat().st_mtime_ns,old_time)

    def test_beijing_midnight_preserves_sequence(self):
        events=[{'ts':'2026-09-08T15:59:59Z','seq':120}, {'ts':'2026-09-08T16:00:00Z','seq':121}, {'ts':'2026-09-09T01:00:00Z','seq':122}]
        days=partition(events,'01a07ed4-3f0d-7450-8bb1-bb756849cb4e','2026-09-08T02:00:00Z')
        self.assertEqual([e['seq'] for e in days['2026-09-08']],[120])
        self.assertEqual([e['seq'] for e in days['2026-09-09']],[121,122])
        self.assertEqual([e for group in days.values() for e in group],events)

    def test_other_history_keeps_layout(self):
        events=[{'ts':'2026-09-09T01:00:00Z','seq':0}]
        self.assertEqual(list(partition(events,'another-session','2026-09-03T01:00:00Z')),['2026-09-03'])

if __name__=='__main__': unittest.main()
