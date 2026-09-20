"""One USB JPEG receiver; only decoded and CRC-checked frames enter the cache."""
import threading
import time
from host.vision.k7_video_receiver import Receiver


class USBFrames:
    def __init__(self, cache):
        self.cache=cache;self.last_frame=None;self.error=None
        self.stop_event=threading.Event();self.thread=None

    def start(self):
        if self.thread is not None:raise RuntimeError('usb_already_started')
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.thread.start()

    def _run(self):
        dev=None;claimed=False
        try:
            import usb.core, usb.util
            import cv2
            import numpy as np
            cv2.setNumThreads(2)
            def decoded(frame):
                image=cv2.imdecode(np.frombuffer(frame['jpeg'],np.uint8),cv2.IMREAD_COLOR)
                if image is None or image.shape[:2]!=(480,640):return
                if (frame['width'],frame['height'])!=(640,480):return
                self.cache.add(frame);self.last_frame=time.monotonic()
            receiver=Receiver(on_frame=decoded)
            dev=usb.core.find(idVendor=0x1209,idProduct=0x0001)
            if dev is None:raise OSError('video_usb_missing')
            if usb.util.get_string(dev,dev.iProduct)!='openvela link probe':
                raise OSError('wrong_usb_product')
            cfg=dev.get_active_configuration()
            ep=usb.util.find_descriptor(cfg[(0,0)],bEndpointAddress=0x81)
            if cfg.bConfigurationValue!=1 or ep is None or ep.wMaxPacketSize!=512:
                raise OSError('wrong_usb_endpoint')
            usb.util.claim_interface(dev,0);claimed=True
            while not self.stop_event.is_set():
                try:receiver.feed(bytes(dev.read(0x81,16384,timeout=200)))
                except usb.core.USBTimeoutError:receiver.expire()
        except Exception as exc:
            self.error=type(exc).__name__+': '+str(exc)
        finally:
            if dev is not None:
                try:
                    if claimed:usb.util.release_interface(dev,0)
                finally:usb.util.dispose_resources(dev)

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(2)
            if self.thread.is_alive():raise OSError('usb_reader_stop_unconfirmed')
