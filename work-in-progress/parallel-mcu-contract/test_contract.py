import random
import unittest
from contract import *

class ContractTests(unittest.TestCase):
    def test_golden(self):
        self.assertEqual(encode_pair(10, -10).hex(), '55aa000a0000fa55aafff6ff00fa')
    def test_signed_exhaustive(self):
        for value in range(-32768, 32768):
            self.assertEqual(decode_frame(encode_axis(255, value, 91)), (255, value, 91))
    def test_ranges(self):
        for x, y in [(-801, 0), (801, 0), (0, -201), (0, 1031), (True, 0)]:
            with self.assertRaises(ValueError): encode_pair(x, y)
    def test_all_splits(self):
        wire = encode_pair(-800, 1030)
        for split in range(15):
            p = Parser()
            p.feed(wire[:split], 0); p.feed(wire[split:], 1)
            self.assertEqual([p.pop(), p.pop()], [(0, -800, 0), (255, 1030, 0)])
    def test_structure_damage_and_overlap(self):
        good = encode_axis(0, 10)
        for index in (0, 1, 2, 6):
            bad = bytearray(good); bad[index] ^= 0x12
            p = Parser(); p.feed(b'\x55' + bad + good, 0)
            self.assertEqual(p.pop(), (0, 10, 0)); self.assertIsNone(p.pop())
    def test_undetectable_payload_damage(self):
        bad = bytearray(encode_axis(0, 10)); bad[3] ^= 1
        self.assertEqual(decode_frame(bad), (0, 11, 0))
    def test_reserved_not_crc(self):
        self.assertEqual(decode_frame(encode_axis(0, 0, 255)), (0, 0, 255))
    def test_noise_bounded(self):
        p = Parser(capacity=2)
        rng = random.Random(1701)
        for _ in range(1000):
            p.feed(rng.randbytes(1000), 0)
            self.assertLessEqual(len(p.buffer), 6)
            self.assertLessEqual(len(p.frames), 2)
    def test_overflow_rejects_newest(self):
        p = Parser(capacity=1); p.feed(encode_pair(1, 2), 0)
        self.assertEqual(p.dropped, 1); self.assertEqual(p.pop(), (0, 1, 0))
    def test_gap_boundary(self):
        p = Parser(gap_ms=50); wire=encode_axis(0, 10)
        p.feed(wire[:3], 0); p.feed(wire[3:], 50)
        self.assertIsNone(p.pop()); self.assertEqual(p.expired, 1)
        p.feed(wire, 51); self.assertEqual(p.pop(), (0, 10, 0))
    def test_disconnect_clears_parser(self):
        p = Parser(); p.feed(encode_pair(1, 2)[:10], 0); p.disconnect()
        self.assertFalse(p.buffer); self.assertIsNone(p.pop())
    def session(self, **kwargs):
        s = Session(**kwargs); s.connect(); return s
    def test_partial_write(self):
        s=self.session(); seq=s.enqueue(10, -10, 0)
        s.accept_write(3, 1); self.assertEqual(len(s.pending_bytes(2)), 11)
        s.accept_write(11, 3)
        self.assertEqual(list(s.history), [(seq, 'host_write_complete', 14)])
        with self.assertRaises(NotImplementedError): s.acknowledge(seq)
    def test_zero_progress_timeout(self):
        s=self.session(); s.enqueue(0, 0, 0); s.accept_write(0, 49)
        self.assertEqual(s.pending_bytes(50), b''); self.assertEqual(s.fault, 'timeout')
    def test_disconnect_mid_pair_no_replay(self):
        s=self.session(); seq=s.enqueue(1, 2, 0); s.accept_write(7, 1)
        s.disconnect(); s.connect()
        self.assertEqual(s.pending_bytes(2), b'')
        self.assertEqual(s.history[-1], (seq, 'disconnected', 7))
    def test_queue_bounds_and_ids(self):
        s=self.session(capacity=2)
        self.assertEqual([s.enqueue(0, 0, 0), s.enqueue(0, 0, 0)], [0, 1])
        with self.assertRaises(BufferError): s.enqueue(0, 0, 0)
        s.disconnect(); s.connect(); self.assertEqual(s.enqueue(0, 0, 0), 2)
        for _ in range(10): s.accept_write(14, 0); s.enqueue(0, 0, 0)
        self.assertLessEqual(len(s.history), 2)
    def test_seq_exhaustion(self):
        s=self.session(); s.next_sequence=2**64-1
        self.assertEqual(s.enqueue(0, 0, 0), 2**64-1)
        with self.assertRaises(OverflowError): s.enqueue(0, 0, 0)
    def test_expired_queue(self):
        s=self.session(); s.enqueue(0, 0, 0); s.enqueue(0, 0, 1)
        s.tick(50); self.assertEqual(len(s.queue), 0)
        with self.assertRaises(ConnectionError): s.enqueue(0, 0, 51)
    def test_halt_unknown_not_zero(self):
        s=self.session(); s.enqueue(10, 20, 0); s.accept_write(2, 1); s.halt()
        self.assertEqual(s.pending_bytes(2), b'')
        self.assertEqual(s.fault, 'host_halt_device_state_unknown')
    def test_invalid_write_and_clock(self):
        s=self.session(); s.enqueue(0, 0, 5)
        with self.assertRaises(ValueError): s.accept_write(15, 5)
        with self.assertRaises(ValueError): s.tick(4)
        self.assertEqual(len(s.pending_bytes(5)), 14)
    def test_capabilities(self):
        for k in ('can', 'ack', 'wire_sequence', 'checksum', 'motor_disable'):
            self.assertEqual(CAPABILITIES[k], 'unsupported')
    def test_pwm_model(self):
        self.assertEqual(pwm_simulation(0, 0), (1492, 700))
        self.assertEqual(pwm_simulation(1, -1), (1491, 699))
        self.assertEqual(pwm_simulation(-32768, 32767), (2500, 2300))
        self.assertEqual(pwm_simulation(32767, -32768), (500, 500))
    def test_pid_model(self):
        self.assertEqual(pid_step(10, 0, 6999, 9, 0, 0, 0), (0, 7000, 10))
        self.assertEqual(pid_step(-10, 0, -6999, -9, 1, 1, 1), (-7011, -7000, -10))

if __name__ == '__main__': unittest.main(verbosity=2)
