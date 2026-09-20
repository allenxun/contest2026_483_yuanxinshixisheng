import unittest
from .voice_intents import IntentRouter


class IntentTests(unittest.TestCase):
    def test_skin_detection_command(self):
        for text in ['皮肤检测。', '开始皮肤检测']:
            self.assertEqual(IntentRouter().route('a',0,'final',text),'assessment_start')
        for text in ['不要皮肤检测','皮肤检测是什么意思','皮肤检测意思']:
            self.assertEqual(IntentRouter().route('a',0,'final',text),'chat')

    def test_explicit_commands(self):
        r=IntentRouter()
        for n,(text,want) in enumerate([('你好OpenVela。','tracking_start'),('开始测肤','assessment_start'),('停止云台！','stop'),('停止播报','stop')]):
            self.assertEqual(r.route('a',n,'final',text),want)

    def test_partial_and_replayed_final_do_not_execute(self):
        r=IntentRouter()
        self.assertIsNone(r.route('a',1,'partial','你好OpenVela'))
        self.assertEqual(r.route('a',1,'final','你好OpenVela'),'tracking_start')
        self.assertIsNone(r.route('a',1,'final','你好OpenVela'))
        self.assertEqual(r.route('b',1,'final','你好OpenVela'),'tracking_start')

    def test_negation_and_discussion_are_not_motion_commands(self):
        for text in ['不要你好OpenVela','别启动','取消启动']:
            self.assertEqual(IntentRouter().route('a',1,'final',text),'chat')

    def test_start_keyword_and_openvela_aliases(self):
        for text in ['你好。','你好openvela','你好openvlea','你好 Open Vela','你好小维','你好联网']:
            self.assertEqual(IntentRouter().route('a',0,'final',text),'tracking_start')
        self.assertEqual(IntentRouter().route('a',0,'final','你好openvela停止云台'),'stop')

    def test_old_broad_start_and_embedded_greeting_do_not_start(self):
        for text in ['启动','启动openvela','openvela','云台已启动','他说你好','你好不要启动']:
            self.assertEqual(IntentRouter().route('a',0,'final',text),'chat')
