"""Writer coordination regressions, using synthetic state only."""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import auto_collect_logs
import export_project_logs
import validate_project_logs


class CoordinationTests(unittest.TestCase):
    def test_programmatic_export_holds_lock_and_releases_on_error(self):
        order = []

        @contextlib.contextmanager
        def lock():
            order.append('enter')
            try:
                yield
            finally:
                order.append('exit')

        def export():
            self.assertEqual(order, ['enter'])
            raise RuntimeError('synthetic failure')

        with patch.object(export_project_logs.os, 'name', 'nt'), \
             patch.object(auto_collect_logs, 'writer_lock', lock), \
             patch.object(export_project_logs, '_export_locked', export):
            with self.assertRaises(RuntimeError):
                export_project_logs.main()
        self.assertEqual(order, ['enter', 'exit'])

    def test_validation_runs_inside_lock_and_preserves_nonzero_exit(self):
        order = []

        @contextlib.contextmanager
        def lock():
            order.append('enter')
            yield
            order.append('exit')

        def run(command, check):
            self.assertEqual(order, ['enter'])
            self.assertFalse(check)
            self.assertTrue(command[-2].endswith('validate-log.py'))
            return subprocess.CompletedProcess(command, 2)

        with patch.object(validate_project_logs, 'writer_lock', lock), \
             patch.object(validate_project_logs.subprocess, 'run', run):
            self.assertEqual(validate_project_logs.main(), 2)
        self.assertEqual(order, ['enter', 'exit'])

    @unittest.skipUnless(os.name == 'nt', 'Windows byte-range lock')
    def test_other_process_cannot_enter_until_writer_releases(self):
        # Child announces its attempted acquisition over stdout, before locking.
        # No sleeps or access to the real private collector or public logs.
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            child_code = (
                'import sys; from pathlib import Path; import auto_collect_logs as a; '
                'a.STATE=Path(sys.argv[1]); print("attempt", flush=True)\n'
                'with a.writer_lock():\n'
                ' print("acquired", flush=True)\n'
            )
            with patch.object(auto_collect_logs, 'STATE', state):
                with auto_collect_logs.writer_lock():
                    child = subprocess.Popen(
                        [sys.executable, '-c', child_code, directory],
                        cwd=Path(__file__).parent, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
                    try:
                        self.assertEqual(child.stdout.readline().strip(), 'attempt')
                        with self.assertRaises(subprocess.TimeoutExpired):
                            child.wait(timeout=0.2)
                    except BaseException:
                        child.kill()
                        child.communicate()
                        raise
                try:
                    output, error = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 0, error)
                    self.assertEqual(output.strip(), 'acquired')
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()


if __name__ == '__main__':
    unittest.main()
