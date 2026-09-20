"""Hash-pinned RAM loader for the built native integration candidate.

Run only after the board is explicitly in Fastboot and OTG attached.
Importing or using --check does not contact hardware.
"""
import argparse
import hashlib
from load_device_intent import CODE
from cloud_radio_stage_audit import ROOT, remote

REV = 'vision-ble-coexist-20260915'
SHA = '30f6a77c377574f53bdb11696a6936279f290e05c519edcd87ffcc792df79305'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--load', action='store_true')
    args = parser.parse_args()
    fw = (ROOT / 'evidence' / REV / 'nuttx.bin').read_bytes()
    assert len(fw) == 2803824 and hashlib.sha256(fw).hexdigest() == SHA
    code = CODE.replace('device-intent-20260915', REV)
    code = code.replace('velavision_device_intent_20260915', 'velavision_vision_ble_coexist_20260915')
    code = code.replace('2799680', '2803824')
    code = code.replace('c3b862d2c62ced7504e1c7a4babfe317fb0c18aeee285c1c3b7f133939c5e137', SHA)
    assert 'device_intent' not in code and 'device-intent' not in code
    compile(code, '<remote-loader>', 'exec')
    if not args.load:
        print('Local hash/size and loader syntax verified; no hardware contacted.')
        return
    import subprocess
    try:
        result = remote(code)
    except subprocess.CalledProcessError as exc:
        (ROOT / 'evidence' / REV / 'startup-failed.log').write_bytes(exc.output or b'')
        raise
    (ROOT / 'evidence' / REV / 'startup.log').write_bytes(result)
    print(result.decode(errors='replace'))

if __name__ == '__main__':
    main()
