"""Host protocol checks; no USB device is accessed."""
import unittest
from fastboot_ram_download import download


class Endpoint:
    def __init__(self, replies=(), short=False):
        self.replies = iter(replies)
        self.sent = []
        self.short = short

    def write(self, data, timeout):
        self.sent.append(bytes(data))
        return len(data) - int(self.short)

    def read(self, size, timeout):
        return next(self.replies)


class ProtocolTests(unittest.TestCase):
    def test_chunks_and_exact_command(self):
        data = bytes(range(256)) * 129
        output = Endpoint()
        download(output, Endpoint([b'INFOready', b'DATA00008100', b'OKAY']), data)
        self.assertEqual(output.sent[0], b'download:00008100')
        self.assertEqual(b''.join(output.sent[1:]), data)
        self.assertLessEqual(max(map(len, output.sent[1:])), 16384)

    def test_rejected_size_sends_no_payload(self):
        output = Endpoint()
        with self.assertRaises(RuntimeError):
            download(output, Endpoint([b'DATA00000002']), b'x')
        self.assertEqual(output.sent, [b'download:00000001'])

    def test_final_failure(self):
        with self.assertRaises(RuntimeError):
            download(Endpoint(), Endpoint([b'DATA00000001', b'FAILtransfer']), b'x')

    def test_short_write_aborts(self):
        output = Endpoint(short=True)
        with self.assertRaises(RuntimeError):
            download(output, Endpoint(), b'x')
        self.assertEqual(len(output.sent), 1)

    def test_empty_rejected_without_command(self):
        output = Endpoint()
        with self.assertRaises(ValueError):
            download(output, Endpoint(), b'')
        self.assertEqual(output.sent, [])

    def test_info_loop_bounded(self):
        with self.assertRaises(RuntimeError):
            download(Endpoint(), Endpoint([b'INFOwait'] * 32), b'x')


if __name__ == '__main__':
    unittest.main(verbosity=2)
