"""Synthetic observer tests. These results are not hardware acceptance."""
import unittest
from observe_ble_reconnect import ReconnectTracker, clean_console_line

D = 'RADIO BLE disconnected status=0 handle=17 reason=19'
C = 'RADIO BLE connection status=0 handle=17 role=1'
E = 'RADIO BLE encryption status=0 handle=17 enabled=1'
P = 'PROV command=2 id=701 ret=0 notify_ret=0'


class ObserverTests(unittest.TestCase):
    def replay(self, lines):
        tracker = ReconnectTracker()
        for line in lines:
            tracker.feed(line, 'synthetic')
        return tracker

    def test_ten_user_cycles_with_reused_controller_handle(self):
        tracker = self.replay([D, C, E, P]*10)
        self.assertEqual(len(tracker.cycles), 10)
        self.assertEqual(tracker.failures, [])

    def test_initial_connection_is_not_reconnection(self):
        self.assertEqual(self.replay([C, E, P]).cycles, [])

    def test_repeated_requests_do_not_inflate_cycle_count(self):
        self.assertEqual(len(self.replay([D, C, E, P, P, P]).cycles), 1)

    def test_failed_notification_is_not_accepted(self):
        tracker = self.replay([D, C, E, P.replace('notify_ret=0', 'notify_ret=-107')])
        self.assertEqual(tracker.cycles, [])
        self.assertEqual(tracker.failures[0]['reason'], 'provisioning_command_failed')

    def test_encryption_from_other_handle_is_not_accepted(self):
        self.assertEqual(self.replay([D, C, E.replace('handle=17', 'handle=18'), P]).cycles, [])

    def test_disconnect_before_reply_is_retained(self):
        tracker = self.replay([D, C, E, D, C, E, P])
        self.assertEqual(len(tracker.cycles), 1)
        self.assertEqual(tracker.failures[0]['reason'], 'disconnected_before_successful_response')

    def test_private_payload_is_not_allowed(self):
        tracker = ReconnectTracker()
        self.assertFalse(tracker.feed('ATT value=password example', 'synthetic'))

    def test_first_disconnect_after_console_prompt_is_preserved(self):
        line = clean_console_line('nsh> \x1b[K'+D+'\r')
        self.assertEqual(line, D)
        self.assertEqual(len(self.replay([line, C, E, P]).cycles), 1)


if __name__ == '__main__':
    unittest.main()
