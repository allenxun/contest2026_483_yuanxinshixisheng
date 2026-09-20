import json
from pathlib import Path
import re
import unittest


class PromptContractTests(unittest.TestCase):
    def test_generated_board_prompts_match_host(self):
        root=Path(__file__).resolve().parents[2]
        prompts=json.loads((Path(__file__).with_name('voice_prompts.zh-CN.json')).read_text(encoding='utf8'))
        code=(root/'app/k7agent/cloud/src/board_voice_prompts.inc').read_text(encoding='utf8')
        actual={json.loads(k):json.loads(v) for k,v in re.findall(r'\{("[^"\\]+"), ("(?:[^"\\]|\\.)*")\}',code)}
        self.assertEqual(actual,prompts)
        for key,text in actual.items():
            self.assertLessEqual(len(text.encode('utf8')),644)
            self.assertLessEqual(len('k7cloud tts-prompt 255.255.255.255 '+key+' &'),160)
