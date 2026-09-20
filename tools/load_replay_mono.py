"""Hash-pinned RAM loader for the built native integration candidate.

Run only after the board is explicitly in Fastboot and OTG attached.
Importing or using --check does not contact hardware.
"""
import argparse
import hashlib
from load_device_intent import CODE
from cloud_radio_stage_audit import ROOT, remote

REV = 'replay-mono-20260916'
SHA = '3d292eddcb605601ea72f9dea45dbc0782c8bbe27f6899b547359673d07de7a3'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--load', action='store_true')
    args = parser.parse_args()
    fw = (ROOT / 'evidence' / REV / 'nuttx.bin').read_bytes()
    assert len(fw) == 2803832 and hashlib.sha256(fw).hexdigest() == SHA
    code = CODE.replace('device-intent-20260915', REV)
    code = code.replace('velavision_device_intent_20260915', 'velavision_replay_mono_20260916')
    code = code.replace('2799680', '2803832')
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
