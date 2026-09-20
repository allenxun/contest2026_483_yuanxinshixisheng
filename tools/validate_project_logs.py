"""Run the unmodified official validator while holding the project writer lock.

Use this entry point for a live Windows collection; a direct validator invocation
can otherwise inspect JSONL partitions and the manifest from different snapshots.
"""
import subprocess
import sys

from auto_collect_logs import ROOT, writer_lock


def main():
    with writer_lock():
        return subprocess.run([
            sys.executable, '-X', 'utf8',
            str(ROOT/'tools/official-validator/tools/validate-log.py'),
            str(ROOT/'logs'),
        ], check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
