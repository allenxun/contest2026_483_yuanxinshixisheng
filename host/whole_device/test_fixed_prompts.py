"""Validate the actual frozen speech assets against the shipping prompt contract."""
import hashlib,json,re,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class FixedPromptTests(unittest.TestCase):
    def test_complete_aligned_pcm_and_text_contract(self):
        folder=ROOT/'app/k7agent/cloud/assets'
        manifest=json.loads((folder/'fixed_prompts.json').read_text(encoding='utf-8'))
        data=(folder/'fixed_prompts.pcm').read_bytes()
        texts=json.loads((ROOT/'host/whole_device/voice_prompts.zh-CN.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['format'],'s16le')
        self.assertEqual((manifest['rate'],manifest['channels']),(16000,1))
        self.assertEqual(hashlib.sha256(data).hexdigest(),manifest['sha256'])
        self.assertLessEqual(len(data),4*1024*1024)
        self.assertEqual({x['key']:x['text'] for x in manifest['prompts']},texts)
        offset=0
        for item in manifest['prompts']:
            self.assertEqual(item['offset'],offset);self.assertEqual(offset%2,0)
            self.assertGreater(item['bytes'],0);self.assertEqual(item['bytes']%2,0)
            pcm=data[offset:offset+item['bytes']]
            self.assertEqual(hashlib.sha256(pcm).hexdigest(),item['sha256'])
            self.assertNotEqual(pcm,bytes(len(pcm)))
            offset+=item['bytes']
        self.assertEqual(offset,len(data))
        generated=(ROOT/'app/k7agent/cloud/src/board_fixed_pcm.inc').read_text()
        initializer=generated.split('= {',1)[1].split('};',1)[0]
        self.assertEqual(bytes(map(int,re.findall(r'\d+',initializer))),data)

if __name__=='__main__':unittest.main()
