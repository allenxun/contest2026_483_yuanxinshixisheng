"""Hash-pinned RAM loader for the built native integration candidate.

Run only after the board is explicitly in Fastboot and OTG attached.
Importing or using --check does not contact hardware.
"""
import argparse
import hashlib
import re
from load_device_intent import CODE
from cloud_radio_stage_audit import ROOT, remote

REV = 'photo-foreground-20260917'
SHA = '189c3e5cbf0953586cdcd7b9af2ee164c1ebb7e57d5f30cfa240c3ef8913ce00'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--load', action='store_true')
    parser.add_argument('--run-label', help='Unique evidence subdirectory for a repeat RAM load')
    args = parser.parse_args()
    if args.run_label and not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_label):
        parser.error('Invalid run label')
    fw = (ROOT / 'evidence' / REV / 'nuttx.bin').read_bytes()
    assert len(fw) == 5011616 and hashlib.sha256(fw).hexdigest() == SHA
    code = CODE.replace('device-intent-20260915', REV)
    code = code.replace('velavision_device_intent_20260915', 'velavision_photo_foreground_20260917')
    code = code.replace('2799680', '5011616')
    code = code.replace('c3b862d2c62ced7504e1c7a4babfe317fb0c18aeee285c1c3b7f133939c5e137', SHA)
    # VMware may enumerate Fastboot with a fresh iSerial after each reset.
    # Wait for the single current device and pass that live serial to the
    # downloader instead of relying on the previous boot's serial string.
    wait = """\nimport sys\nsys.path.append(str(r.USB_DEPS))\nimport usb.core,usb.util\n_deadline=time.monotonic()+60\nwhile time.monotonic() < _deadline:\n _devs=list(usb.core.find(find_all=True,idVendor=0x18d1,idProduct=0x4d00) or [])\n if len(_devs)==1:\n  _serial=usb.util.get_string(_devs[0],_devs[0].iSerialNumber)\n  if _serial:\n   r.USB_SERIAL=_serial\n   break\n time.sleep(.25)\nelse:\n raise RuntimeError('Fastboot gadget not present after 60s')\n"""
    code = code.replace("subprocess.run([sys.executable,str(r.DOWNLOADER)", wait + "\nsubprocess.run([sys.executable,str(r.DOWNLOADER)")
    assert 'device_intent' not in code and 'device-intent' not in code
    output=ROOT/'evidence'/REV
    if args.run_label:
        code=code.replace("out=p/'evidence/"+REV+"';out.mkdir(exist_ok=True)",
                          "out=p/'evidence/"+REV+"/"+args.run_label+"';out.mkdir(exist_ok=False)")
        output=output/args.run_label
    compile(code, '<remote-loader>', 'exec')
    if not args.load:
        print('Local hash/size and loader syntax verified; no hardware contacted.')
        return
    import subprocess
    output.mkdir(exist_ok=not bool(args.run_label))
    try:
        result = remote(code)
    except subprocess.CalledProcessError as exc:
        (output / 'startup-failed.log').write_bytes(exc.output or b'')
        raise
    (output / 'startup.log').write_bytes(result)
    print(result.decode(errors='replace'))

if __name__ == '__main__':
    main()
