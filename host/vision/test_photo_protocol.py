import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from photo_protocol import Protocol,FrameCache,save_exact
from k7_video_receiver import Receiver,HEADER,MAGIC

class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.request=dict(q=11,epoch=1,side=1,raw_pose=dict(yaw=1,pitch=2,roll=3),
            filtered_pose=dict(yaw=1,pitch=2,roll=3),sharpness=100,face_size=120)
        self.frame=dict(sequence=11,capture_us=123000,width=640,height=480,
            jpeg=b'\xff\xd8test-fixture-not-real-image\xff\xd9',received_at=12.3)
    def tearDown(self):self.tmp.cleanup()
    def test_commit_exact_and_duplicate(self):
        path=Path(save_exact(self.root,self.request,self.frame))
        self.assertEqual(path.read_bytes(),self.frame['jpeg'])
        record=json.loads(path.with_suffix('.json').read_text())
        self.assertEqual(record['q'],11)
        self.assertEqual(record['jpeg_sha256'],hashlib.sha256(self.frame['jpeg']).hexdigest())
        self.assertEqual(str(path),save_exact(self.root,self.request,self.frame))
        self.assertEqual(len(list(self.root.rglob('*.jpg'))),1)
    def test_wrong_frame_rejected(self):
        self.frame['sequence']=12
        with self.assertRaises(ValueError):save_exact(self.root,self.request,self.frame)
        self.assertFalse(list(self.root.rglob('*.jpg')))
    def test_wrong_raw_angle_rejected(self):
        self.request['raw_pose']['yaw']=45
        with self.assertRaises(ValueError):save_exact(self.root,self.request,self.frame)
    def test_seven_degree_boundaries(self):
        for q,(side,yaw) in enumerate(((1,7),(2,38),(2,52),(4,-38),(4,-52)),100):
            self.request.update(q=q,side=side)
            self.frame['sequence']=q
            self.request['raw_pose']['yaw']=self.request['filtered_pose']['yaw']=yaw
            self.assertTrue(Path(save_exact(self.root,self.request,self.frame)).exists())
        self.request['raw_pose']['yaw']=-52.1
        with self.assertRaises(ValueError):save_exact(self.root,self.request,self.frame)
    def test_reversed_side_label_rejected(self):
        self.request['side']=2
        self.request['raw_pose']['yaw']=self.request['filtered_pose']['yaw']=-45
        with self.assertRaises(ValueError):save_exact(self.root,self.request,self.frame)
    def test_bad_metadata_rejected(self):
        self.request['raw_pose']['pitch']=float('nan')
        with self.assertRaises(ValueError):save_exact(self.root,self.request,self.frame)
    def test_file_failure_not_success(self):
        blocked=self.root/'blocked';blocked.write_text('file instead of directory')
        with self.assertRaises(OSError):save_exact(blocked,self.request,self.frame)
    def test_split_serial_pair(self):
        protocol=Protocol(self.root)
        data=b'noise\nPHOTO q=11 e=1 s=1 y=1.0 p=2.0 r=3.0\r\nPHOTOQ q=11 sy=1 sp=2 sr=3 sharp=100 size=120\r\n'
        for byte in data:protocol.feed(bytes([byte]))
        self.assertEqual(json.loads((self.root/'capture.request').read_text()),self.request)
    def test_mismatched_quality_not_requested(self):
        p=Protocol(self.root)
        p.feed(b'PHOTO q=11 e=1 s=1 y=1 p=2 r=3\nPHOTOQ q=12 sy=1 sp=2 sr=3 sharp=100 size=120\n')
        self.assertFalse((self.root/'capture.request').exists())
    def test_cache_all_frames_even_single_usb_read(self):
        def packet(q):
            b=self.frame['jpeg']
            h=struct.pack('<8sIQIHHI',MAGIC,q,123,len(b),640,480,zlib.crc32(b))
            return h+struct.pack('<I',zlib.crc32(h))+b
        cache=FrameCache(limit=2);r=Receiver(on_frame=cache.add)
        self.assertEqual(r.feed(packet(11)+packet(12))['sequence'],12)
        self.assertIsNotNone(cache.get(11));self.assertIsNotNone(cache.get(12))
        r.feed(packet(13));self.assertIsNone(cache.get(11))
    def test_corrupt_usb_never_cached(self):
        cache=FrameCache();r=Receiver(on_frame=cache.add)
        b=self.frame['jpeg'];h=struct.pack('<8sIQIHHI',MAGIC,11,123,len(b),640,480,123)
        r.feed(h+struct.pack('<I',zlib.crc32(h))+b)
        self.assertIsNone(cache.get(11));self.assertEqual(r.corrupt,1)

if __name__=='__main__':unittest.main(verbosity=2)
