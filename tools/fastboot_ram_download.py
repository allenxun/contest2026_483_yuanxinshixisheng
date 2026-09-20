"""Download bytes only to an already active, explicitly selected Fastboot device.

No flash, erase, boot, continue, reboot, or OEM commands are implemented.
Operator must first verify the running U-Boot buffer address and size.
Requires PyUSB and a working USB backend only for actual transfer.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path


def download(out_ep, in_ep, payload, timeout_ms=10000):
    def send(data):
        if out_ep.write(data, timeout=timeout_ms) != len(data):
            raise RuntimeError('Short USB write; abort without further commands')

    def response():
        for _ in range(32):
            data = bytes(in_ep.read(64, timeout=timeout_ms))
            if data.startswith(b'INFO'):
                continue
            return data
        raise RuntimeError('Too many INFO responses')

    if not 0 < len(payload) <= 0x07000000:
        raise ValueError('Outside audited SDK buffer size')
    expected = ('%08x' % len(payload)).encode()
    send(b'download:' + expected)
    if response() != b'DATA' + expected:
        raise RuntimeError('Device did not accept exact download size')
    for offset in range(0, len(payload), 16384):
        send(payload[offset:offset + 16384])
    if response() != b'OKAY':
        raise RuntimeError('Download not acknowledged')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--vid', type=lambda s: int(s, 0), required=True)
    p.add_argument('--pid', type=lambda s: int(s, 0), required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--audited-running-buffer', required=True,
                   help='Must be 0x40c00800:0x07000000; SDK defaults alone are insufficient')
    p.add_argument('--result', type=Path, required=True)
    a = p.parse_args()
    if a.audited_running_buffer != '0x40c00800:0x07000000':
        p.error('Running U-Boot memory audit required')
    if a.result.exists():
        p.error('Refusing to overwrite evidence')
    payload = a.image.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != a.sha256.lower():
        p.error('Image SHA256 mismatch')
    import usb.core
    import usb.util
    matches = [d for d in usb.core.find(find_all=True, idVendor=a.vid, idProduct=a.pid)
               if usb.util.get_string(d, d.iSerialNumber) == a.serial]
    if len(matches) != 1:
        raise RuntimeError('Require exactly one matching USB serial')
    device = matches[0]
    interfaces = [i for i in device.get_active_configuration()
                  if (i.bInterfaceClass, i.bInterfaceSubClass, i.bInterfaceProtocol)
                  == (0xff, 0x42, 0x03)]
    if len(interfaces) != 1:
        raise RuntimeError('Require exactly one Fastboot interface')
    interface = interfaces[0]
    inputs = [e for e in interface if e.bmAttributes & 3 == 2 and e.bEndpointAddress & 128]
    outputs = [e for e in interface if e.bmAttributes & 3 == 2 and not e.bEndpointAddress & 128]
    if len(inputs) != 1 or len(outputs) != 1:
        raise RuntimeError('Unexpected bulk endpoints')
    record = dict(sha256=digest, bytes=len(payload), usb_ack=False,
                  ram_crc_verified=False, firmware_started=False, flash_commands=False)
    start = time.monotonic()
    try:
        usb.util.claim_interface(device, interface.bInterfaceNumber)
        download(outputs[0], inputs[0], payload)
        record['usb_ack'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        record['seconds'] = time.monotonic() - start
        a.result.parent.mkdir(parents=True, exist_ok=True)
        a.result.write_text(json.dumps(record, indent=2), encoding='utf-8')
        usb.util.dispose_resources(device)
    print(json.dumps(record))


if __name__ == '__main__':
    main()
