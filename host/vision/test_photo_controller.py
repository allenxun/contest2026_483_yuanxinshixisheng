"""Protocol integration test: simulated NSH, never opens real hardware."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
from photo_protocol import atomic_json

class ControllerTest(unittest.TestCase):
    def run_case(self,acknowledge):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);control=root/'control';preview=root/'preview'
            preview.mkdir();(preview/'ready.json').write_text('{}')
            profile=Path(__file__).with_name('calibration.json')
            commands=[]
            class Port:
                def __init__(self,**kwargs):self.buffer=b''
                def open(self):pass
                def flush(self):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,n):
                    time.sleep(.003)
                    result=self.buffer;self.buffer=b'';return result
                def write(self,data):
                    text=data.decode().strip();commands.append(text)
                    if text=='gimbal info':self.buffer+=b'MCU PROFILE v1.3-xcenter X_MID=1492\r\nnsh> '
                    elif text=='k7host photoreset':self.buffer+=b'PHOTO reset requested; saved files retained\r\nnsh> '
                    elif text=='gimbal adopt 0 0':self.buffer+=b'ADOPT OK x=0 y=0 NO UART TX\r\nnsh> '
                    elif text.startswith('k7host photos '):
                        if len(text.split())>8:raise AssertionError('NSH argument overflow')
                        if not text.endswith('&'):raise AssertionError('Foreground capture blocks control')
                        self.buffer+=b'k7host [10:100]\r\nnsh> '
                    elif text=='k7host halt' and acknowledge:self.buffer+=b'TRACK halt requested: hold last target; not motor disable.\r\nnsh> '
            stop=threading.Event()
            def operator():
                while not control.exists() and not stop.wait(.01):pass
                if stop.is_set():return
                (control/'start.request').write_text('simulated operator')
                while not stop.wait(.025):atomic_json(control/'view.json',dict(at=time.monotonic(),age=.02))
            thread=threading.Thread(target=operator);thread.start()
            args=['photo_controller.py','--profile',str(profile),'--control',str(control),
                '--preview',str(preview),'--initial-x','0','--initial-y','0','--duration','1']
            try:
                with patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=Port)}),patch.object(sys,'argv',args):
                    runpy.run_path(str(Path(__file__).with_name('photo_controller.py')),run_name='__main__')
            finally:stop.set();thread.join()
            status=json.loads((control/'status.json').read_text())
            self.assertIn('k7host photos 1 &',commands)
            self.assertEqual(commands.count('k7host photoreset'),2)
            self.assertIn('k7host halt',commands)
            return status
    def test_background_and_stop_ack(self):
        self.assertEqual(self.run_case(True)['label'],'TEST FINISHED - HOLD POSITION')
    def test_missing_stop_ack_is_not_reported_stopped(self):
        self.assertIn('STOP UNCONFIRMED',self.run_case(False)['label'])

if __name__=='__main__':unittest.main(verbosity=2)
