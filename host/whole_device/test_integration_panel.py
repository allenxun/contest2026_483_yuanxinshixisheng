import unittest
from .integration_panel import State, display_box
import time

class PanelStateTests(unittest.TestCase):
    def test_photo_retry_finishes_without_marking_analysis_complete(self):
        s=State();s.busy=True;s.done=7
        s.line('K7CLOUD photo_upload epoch=3 result=0 accepted=1 task=id')
        s.line('K7CLOUD photo_retry result=0 retained_views=7')
        self.assertFalse(s.busy);self.assertEqual(s.done,7)
        self.assertIn('不代表分析完成',s.upload)
        s.busy=True;s.line('K7CLOUD photo_retry result=-5 retained_views=7')
        self.assertFalse(s.busy);self.assertEqual(s.done,7)
        self.assertIn('失败',s.status)
    def test_lost_photo_lock_does_not_show_zero_angles_as_measurement(self):
        s=State()
        s.line('POSE q=8718 e=2 y=0.00 p=0.00 r=0.00 v=0 st=6 next=4 done=3')
        self.assertNotIn('0.00',s.pose)
        s.line('POSEQ q=8718 sy=0.00 sharp=0.0 settle=1 lost=1 age=88')
        self.assertIn('重新拍摄',s.pose_guidance);self.assertEqual(s.done,3)
        s.line('POSE q=9000 e=3 y=2.00 p=1.00 r=0.00 v=1 st=1 next=1 done=0')
        self.assertNotIn('重新拍摄',s.pose_guidance)
    def test_hold_ack_needs_following_halted_telemetry(self):
        s=State()
        halted='TRACK q=12 s=4 dx=0.0 dy=0.0 x=0 y=0 tx=0 age=1000'
        s.line(halted);self.assertFalse(s.camera)
        s.line('VOICE MODE requested=0 result=-19')
        s.line(halted);self.assertFalse(s.camera)
        s.line('VOICE MODE requested=0 result=0');self.assertFalse(s.camera)
        s.line(halted);self.assertTrue(s.camera);self.assertTrue(s.held)
        s.line('UVC STREAM elapsed_ms=1800000 result=0')
        s.line(halted);self.assertFalse(s.camera)
    def test_applied_voice_mode_recovers_missing_session_line(self):
        s=State()
        s.line('VOICE MODE requested=0 result=0')
        self.assertFalse(s.camera)
        s.line('VOICE MODE applied=0 result=-5')
        self.assertFalse(s.camera)
        s.line('VOICE MODE applied=9 result=0')
        self.assertFalse(s.camera)
        s.line('VOICE MODE applied=0 result=0')
        self.assertTrue(s.camera);self.assertTrue(s.held)
        s.line('UVC STREAM elapsed_ms=1800000 result=0')
        self.assertFalse(s.camera)
    def test_accepted_overlay_mirror_and_expiry(self):
        s=State();s.line('TRACK BOX q=12 x=10.0 y=20.0 w=30.0 h=40.0 edge=0')
        s.line('TRACK q=12 s=2 dx=0.0 dy=0.0 x=0 y=0 tx=0 age=1000')
        now=s.telemetry['received_at']
        self.assertEqual(display_box(s.telemetry,12,now,False),((40,80),(160,240)))
        self.assertEqual(display_box(s.telemetry,12,now,True),((479,80),(599,240)))
        self.assertIsNone(display_box(s.telemetry,12,now+1,True))
        s.line('TRACK q=13 s=0 dx=0.0 dy=0.0 x=0 y=0 tx=0 age=1000')
        self.assertNotIn('box',s.telemetry)
    def test_single_completion_does_not_require_timing_line(self):
        s=State();s.single=True;s.busy=True
        s.line('K7CLOUD asr result=0 frames_sent=150 completed=1')
        self.assertFalse(s.busy);self.assertFalse(s.single);self.assertIn('识别完成',s.status)
        s.single=True;s.busy=True
        s.line('K7CLOUD asr result=-5 frames_sent=17 completed=0')
        self.assertFalse(s.busy);self.assertIn('失败',s.status)
    def test_stream_end_clears_camera_readiness(self):
        s=State();s.camera=True
        s.line('UVC STREAM requested_s=1800 elapsed_ms=1800226 batches=56257 complete_JPEG=53802 result=0')
        self.assertFalse(s.camera);self.assertIn('采集已结束',s.status)
    def test_network_reply_completes_recovery(self):
        s=State();s.recovery_started=1
        s.line('K7CLOUD radio_generation=1 wifi=1 ipv4_ready=1')
        self.assertEqual(s.recovery_started,0);self.assertIn('已恢复',s.status)
    def test_truncated_network_line_does_not_overwrite_valid_state(self):
        s=State();s.line('K7CLOUD radio_generation=1 wifi=1 ipv4_ready=1')
        stamp=s.network_stamp
        s.line('K7CLOUD radio_generation=1 wifi=1 ipv4_reTRACK q=4')
        self.assertTrue(s.wifi);self.assertEqual(s.network_stamp,stamp)
        s.line('K7CLOUD radio_generation=2 wifi=0 ipv4_ready=0')
        self.assertFalse(s.wifi)
    def test_probe_requires_explicit_success(self):
        s=State();s.line('UVC probe result=-19 committed=0 (no streaming yet)')
        self.assertFalse(s.probed)
        s.line('UVC probe result=0 committed=1 (no streaming yet)')
        self.assertTrue(s.probed);self.assertFalse(s.camera)
    def test_no_actions_are_inferred_from_asr_completion(self):
        s=State();s.line('K7CLOUD device round=1')
        s.line('K7CLOUD timing asr_completed_us=10 result=0')
        self.assertTrue(s.busy);self.assertTrue(s.held);self.assertEqual(s.done,0)
        s.line('K7CLOUD device intent=2');self.assertEqual(s.command,'皮肤检测')
        self.assertTrue(s.held)
        s.line('VOICE MODE applied=2 result=0');self.assertFalse(s.held)
        s.line('K7CLOUD device loop_done=0');self.assertFalse(s.busy)
    def test_capture_is_not_backend_acceptance(self):
        s=State();s.line('PHOTO complete e=1 views=7 hold_requested=1 upload_started=0')
        self.assertEqual(s.done,7);self.assertEqual(s.upload,'尚未上传')
        s.line('K7CLOUD photo_upload epoch=1 result=-5 accepted=0 task=')
        self.assertIn('未获受理',s.upload)
        s.line('K7CLOUD photo_upload epoch=1 result=0 accepted=1 task=id')
        self.assertIn('不代表分析完成',s.upload)
    def test_pose_and_network(self):
        s=State();s.line('K7CLOUD radio_generation=1 wifi=1 ipv4_ready=1')
        self.assertTrue(s.wifi)
        s.line('POSE q=4 e=1 y=-30.00 p=2.00 r=0.00 v=1 st=2 next=4 done=3')
        self.assertEqual(s.done,3);self.assertIn('-30.00',s.pose)
        s.line('K7CLOUD radio_generation=2 wifi=0 ipv4_ready=0');self.assertFalse(s.wifi)

if __name__=='__main__':unittest.main()
