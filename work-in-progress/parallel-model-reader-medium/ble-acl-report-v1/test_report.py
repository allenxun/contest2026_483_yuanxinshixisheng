import hashlib
import unittest
from report import GROUPS, analyze, parse


def sample(**kw):
    return ''.join('RADIO BTM '+' '.join(k+'='+str(kw.get(k,0)) for k in group)+'\n' for group in GROUPS).encode()


class Tests(unittest.TestCase):
    def test_complete_and_hash(self):
        a = sample(); r = analyze(a,a)
        self.assertEqual(r['input_sha256']['before'], hashlib.sha256(a).hexdigest())
        self.assertTrue(all(v == 0 for v in r['uint32_modulo_delta'].values()))
        self.assertEqual(len(parse(a)),25)
    def test_missing_line(self):
        with self.assertRaises(ValueError): parse(b'\n'.join(sample().split(b'\n')[1:]))
    def test_duplicate_block(self):
        with self.assertRaises(ValueError): parse(sample()+sample())
    def test_duplicate_field(self):
        with self.assertRaises(ValueError): parse(sample().replace(b'ACL_SEND_OK=',b'ACL_QUEUED='))
    def test_duplicate_line(self):
        with self.assertRaises(ValueError): parse(sample()+sample().splitlines(keepends=True)[0])
    def test_truncated(self):
        for n in (1,4,20):
            with self.assertRaises(ValueError): parse(sample()[:-n])
    def test_wrap(self):
        r=analyze(sample(ACL_QUEUED=0xfffffffe),sample(ACL_QUEUED=1))
        self.assertEqual(r['uint32_modulo_delta']['ACL_QUEUED'],3)
        self.assertIn('ACL_QUEUED',r['counter_decreases'])
    def test_flow_zero_not_success(self):
        r=analyze(sample(),sample())
        self.assertIsNone(r['flow_complete']['after']['status'])
    def test_flow_error(self):
        r=analyze(sample(),sample(FLOW_COMPLETE=1,flow_status=12))
        self.assertEqual(r['flow_complete']['after']['status'],12)
    def test_noncoherent_not_rejected_or_loss_inferred(self):
        r=analyze(sample(),sample(ACL_ACK_MATCH=2,ACL_SEND_OK=1))
        self.assertEqual(r['uint32_modulo_delta']['ACL_ACK_MATCH'],2)
        self.assertTrue(any('not a coherent snapshot' in x for x in r['limitations']))
        self.assertTrue(any('not HCI, GATT' in x for x in r['evidence']))
    def test_last_error_persists(self):
        r=analyze(sample(last_send=-5),sample(last_send=-5,ACL_SEND_OK=1))
        self.assertEqual(r['last_error_before_after']['last_send'],{'before':-5,'after':-5})
    def test_invalid_ranges(self):
        for kw in ({'ACL_QUEUED':-1},{'ACL_QUEUED':2**32},{'last_send':-2**31-1},{'flow_status':256}):
            with self.assertRaises(ValueError):parse(sample(**kw))
    def test_unknown_field(self):
        with self.assertRaises(ValueError):parse(sample().replace(b'last_wait=',b'wrong='))
    def test_interleaved(self):
        with self.assertRaises(ValueError):parse(sample().replace(b'\n',b'\nnoise\n',1))
    def test_unrelated_preamble_and_crlf(self):
        self.assertEqual(parse(b'RADIO BLE connected=1\r\n'+sample().replace(b'\n',b'\r\n')),parse(sample()))
    def test_fault_evidence(self):
        r=analyze(sample(),sample(ACL_SEND_FAIL=1,ACL_ACK_WAIT_FAIL=1,PORT5_HCI_DECODE_FAIL=1,READY_REJECT=1))
        self.assertGreaterEqual(len(r['evidence']),5)


if __name__=='__main__':unittest.main(verbosity=2)
