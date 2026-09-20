"""Ubuntu entry point for an already initialized, held voicecam session.

Windows forwards port 8001 to this loopback bridge over SSH. The speech-service
URL points back to Windows. This program never adopts coordinates or reboots.
"""
import argparse
import asyncio
import ipaddress
import re
import time
import uuid
from pathlib import Path
from host.streaming_asr.board_bridge import serve
from host.vision.photo_protocol import FrameCache, atomic_json
from .serial_owner import SerialOwner
from .native_speech import NativeSpeech
from .native_ports import NativePorts
from .controller import DeviceController
from .command_session import CommandSession
from .usb_frames import USBFrames


class RecognitionInbox:
    def __init__(self):self.pending=None
    def arm(self):
        if self.pending is not None and not self.pending.done():raise RuntimeError('recording_already_pending')
        self.pending=asyncio.get_running_loop().create_future()
        return self.pending
    def deliver(self,finals):
        if self.pending is not None and not self.pending.done():self.pending.set_result(finals)
    def clear(self):
        if self.pending is not None and not self.pending.done():self.pending.cancel()
        self.pending=None


async def run(args):
    import serial
    args.output.mkdir(parents=True,exist_ok=False)
    port=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2,exclusive=True)
    port.dtr=port.rts=False;port.port=args.serial;port.open()
    owner=SerialOwner(port,char_interval=.004);owner.start()
    cache=FrameCache();video=USBFrames(cache)
    speech=NativeSpeech(owner,args.bridge_ip)
    controller=DeviceController(NativePorts(owner,cache,args.output/'photos',speech))
    commands=CommandSession(controller);inbox=RecognitionInbox()
    bridge=asyncio.create_task(serve('127.0.0.1',8001,args.service,on_recognition=inbox.deliver))
    tasks=[bridge];started=time.monotonic()
    def status(phase,**extra):
        atomic_json(args.output/'status.json',dict(phase=phase,device_state=controller.state,**extra))
    async def watchdog():
        while True:
            await asyncio.sleep(.1)
            last=video.last_frame
            if video.error or (last is None and time.monotonic()-started>8) or (last is not None and time.monotonic()-last>1):
                raise OSError('video_missing_or_stale')
    async def listen():
        # All microphone and speaker operations share the same audio turn lock.
        # This is repeated 3-second capture, not full-duplex barge-in.
        while True:
            identity=str(uuid.uuid4());commands.begin(identity)
            future=inbox.arm()
            try:
                async with speech.lock:
                    status('recording_preparing')
                    line=await owner.request('asr-record','k7cloud asr-live '+args.bridge_ip+' &',
                        lambda s:bool(re.fullmatch(r'K7CLOUD asr result=-?\d+ frames_sent=\d+ completed=[01]',s)),timeout=45)
                    if line!='K7CLOUD asr result=0 frames_sent=150 completed=1':raise OSError('asr_capture_failed')
                    finals=await asyncio.wait_for(future,5)
                if finals is None:raise OSError('asr_cloud_failed')
                for number,text in sorted(finals.items()):
                    outcome=await commands.accept(identity,number,'final',text)
                    status('command_result',outcome=outcome)
            finally:inbox.clear();commands.end()
            await asyncio.sleep(.1)
    try:
        await asyncio.sleep(0)
        if bridge.done():await bridge
        video.start()
        while video.last_frame is None:
            if video.error or time.monotonic()-started>8:raise OSError('video_not_ready')
            await asyncio.sleep(.05)
        tasks += [asyncio.create_task(watchdog()),asyncio.create_task(listen())]
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:await task
    finally:
        commands.end();inbox.clear()
        for task in tasks[1:]:task.cancel()
        await asyncio.gather(*tasks[1:],return_exceptions=True)
        try:
            stopped=await controller.stop()
            status('stopped' if stopped else 'stop_unconfirmed')
        finally:
            bridge.cancel();await asyncio.gather(bridge,return_exceptions=True)
            await owner.close();await asyncio.to_thread(video.close)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',default='/dev/ttyUSB0')
    parser.add_argument('--bridge-ip',required=True,type=lambda s:str(ipaddress.IPv4Address(s)))
    parser.add_argument('--service',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--camera-ready',required=True,action='store_true',help='Verified calibrated voicecam is already running in hold')
    asyncio.run(run(parser.parse_args()))
