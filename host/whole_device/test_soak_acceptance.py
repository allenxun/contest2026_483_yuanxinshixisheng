import unittest
from .soak_acceptance import assess
class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'wall_time':100,'line':s} for s in ['RADIO BLE name=K7 connected=1 handle=1','RADIO BLE history connections=1 disconnections=0 last_reason=0 encrypt_status=0 encrypted=1','1000 200 800 300 700 2 3 Umem']]
        self.state=dict(sample_wall_time=100,network_age_s=1,wifi=True,camera=True,video_fresh=True,frames=20)
    def test_ready_and_heap(self):
        result=assess(self.state,self.rows,101)
        self.assertEqual(result['problems'],[]);self.assertEqual(result['heap_free'],800)
    def test_stale_panel_and_telemetry(self):
        result=assess(self.state,self.rows,200)
        self.assertIn('stale_panel',result['problems']);self.assertIn('memory_stale',result['problems'])
    def test_missing_samples_not_zero(self):
        result=assess(self.state,[],101)
        self.assertIsNone(result['heap_free']);self.assertIn('ble_stale',result['problems'])
    def test_network_freshness(self):
        self.assertIn('network_reply_stale',assess(dict(self.state,network_age_s=46),self.rows,101)['problems'])
    def test_ble_disconnected(self):
        self.rows[0]['line']='RADIO BLE name=K7 connected=0 handle=0'
        self.assertIn('ble_disconnected',assess(self.state,self.rows,101)['problems'])
    def test_encrypt_failure(self):
        self.rows[1]['line']='RADIO BLE history connections=1 disconnections=0 last_reason=0 encrypt_status=5 encrypted=0'
        self.assertIn('ble_not_encrypted',assess(self.state,self.rows,101)['problems'])
