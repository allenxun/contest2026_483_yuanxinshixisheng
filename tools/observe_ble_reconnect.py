"""Observe user-driven BLE reconnections; never disconnect/reboot the board.

Each accepted cycle needs a recorded disconnect, successful connection,
encryption, and a successful provisioning command queued for notification.
Phone receipt is a separate manual acceptance, never inferred from queuing.
Only allowlisted metadata is saved; no ATT payloads or credentials.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCONNECT = re.compile(r'RADIO BLE disconnected status=(\d+) handle=(\d+) reason=(\d+)')
CONNECT = re.compile(r'RADIO BLE connection status=(\d+) handle=(\d+) role=(\d+)')
ENCRYPT = re.compile(r'RADIO BLE encryption status=(\d+) handle=(\d+) enabled=(\d+)')
COMMAND = re.compile(r'PROV command=(\d+) id=(\d+) ret=(-?\d+) notify_ret=(-?\d+)')
HISTORY = re.compile(r'RADIO BLE history connections=(\d+) disconnections=(\d+) last_reason=(\d+) encrypt_status=(\d+) encrypted=(\d+)')


def clean_console_line(line):
    line = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', line).strip()
    return re.sub(r'^nsh>\s*', '', line)


class ReconnectTracker:
    def __init__(self):
        self.disconnect_seen = False
        self.current = None
        self.cycles = []
        self.failures = []

    def feed(self, line, at):
        if match := DISCONNECT.fullmatch(line):
            if int(match[1]) != 0:
                self.failures.append({'at': at, 'reason': 'disconnect_command_failed'})
                return True
            if self.current is not None:
                self.failures.append({'at': at, 'reason': 'disconnected_before_successful_response', 'cycle': self.current})
            self.current = None
            self.disconnect_seen = True
            return True
        if match := CONNECT.fullmatch(line):
            if int(match[1]) != 0:
                self.failures.append({'at': at, 'reason': 'connection_failed', 'status': int(match[1])})
            elif self.disconnect_seen:
                self.current = {'connected_at': at, 'handle': int(match[2]), 'encrypted': False}
                self.disconnect_seen = False
            return True
        if match := ENCRYPT.fullmatch(line):
            if self.current and int(match[2]) == self.current['handle']:
                self.current['encrypted'] = int(match[1]) == 0 and int(match[3]) == 1
                if not self.current['encrypted']:
                    self.failures.append({'at': at, 'reason': 'encryption_failed', 'status': int(match[1])})
            return True
        if match := COMMAND.fullmatch(line):
            if self.current:
                if int(match[3]) or int(match[4]):
                    self.failures.append({'at': at, 'reason': 'provisioning_command_failed', 'ret': int(match[3]), 'notify_ret': int(match[4])})
                elif self.current['encrypted']:
                    self.current.update(command=int(match[1]), transaction_id=int(match[2]), response_queued_at=at)
                    self.cycles.append(self.current)
                    self.current = None
            return True
        return bool(HISTORY.fullmatch(line))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--cycles', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 1800 or not 1 <= args.cycles <= 20:
        parser.error('seconds must be 1..1800, cycles 1..20')
    sys.path.insert(0, str(ROOT.parent/'无线适配_2026-09-08/tools/pydeps'))
    import serial
    args.out.mkdir(parents=True, exist_ok=False)
    tracker = ReconnectTracker()
    start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    error = None
    baseline = None
    serial_port = serial.Serial(port=None, baudrate=1500000, timeout=.05, write_timeout=2)
    serial_port.dtr = False
    serial_port.rts = False
    serial_port.port = 'COM8'
    with (args.out/'events.jsonl').open('x', encoding='utf-8') as output:
        def record(kind, **values):
            output.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), kind=kind, **values))+'\n')
            output.flush()
        try:
            with serial_port:
                # One baseline query; all subsequent observation is passive.
                serial_port.write(b'k7radio ble-status\r')
                serial_port.flush()
                buf = bytearray()
                record('started', port='COM8', target_cycles=args.cycles)
                last_count = 0
                last_progress = 0
                print('OBSERVING user-driven disconnect/reconnect; no board mutation', flush=True)
                while time.monotonic()-start < args.seconds:
                    buf.extend(serial_port.read(8192))
                    while b'\n' in buf:
                        row, _, rest = buf.partition(b'\n')
                        buf[:] = rest
                        line = clean_console_line(row.decode('ascii', errors='replace'))
                        stamp = datetime.now(timezone.utc).isoformat()
                        if tracker.feed(line, stamp):
                            record('serial', line=line)
                        if baseline is None and (match := HISTORY.fullmatch(line)):
                            baseline = dict(connections=int(match[1]), disconnections=int(match[2]), encrypted=int(match[5]))
                    if len(buf) > 8192:
                        buf.clear()
                        tracker.failures.append({'reason': 'serial_line_overflow'})
                    state = dict(elapsed_s=round(time.monotonic()-start, 2), target_cycles=args.cycles,
                                 board_verified_cycles=len(tracker.cycles), failures=tracker.failures,
                                 phone_receipt_verified=False)
                    if time.monotonic()-last_progress >= 2 or last_count != len(tracker.cycles):
                        temp = args.out/'progress.tmp'
                        temp.write_text(json.dumps(state, indent=2)+'\n', encoding='utf-8')
                        temp.replace(args.out/'progress.json')
                        last_progress = time.monotonic()
                    if last_count != len(tracker.cycles):
                        print(json.dumps(state), flush=True)
                        last_count = len(tracker.cycles)
                    if len(tracker.cycles) >= args.cycles:
                        break
        except Exception as exc:
            error = type(exc).__name__+': '+str(exc)
            record('collection_error', detail=error)
    result = dict(started_at=started_at, finished_at=datetime.now(timezone.utc).isoformat(),
                  elapsed_s=round(time.monotonic()-start, 2), baseline=baseline,
                  target_cycles=args.cycles, cycles=tracker.cycles, failures=tracker.failures,
                  collection_error=error, incomplete_cycle=tracker.current,
                  board_acceptance_passed=len(tracker.cycles) == args.cycles and not tracker.failures and error is None and baseline is not None,
                  phone_receipt_verified=False, full_acceptance_passed=False,
                  scope='User-triggered disconnect and encrypted reconnect plus provisioning notification queuing; phone receipt requires separate evidence')
    (args.out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('RESULT '+json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result['board_acceptance_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
