"""Hash-pinned RAM loader for the built native integration candidate.

Run only after the board is explicitly in Fastboot and OTG attached.
Importing or using --check does not contact hardware.
"""
import argparse
import hashlib
import re
from load_device_intent import CODE
from cloud_radio_stage_audit import ROOT, remote

REV = 'skin-command-20260916'
SHA = '9325afe85b768c84b9ec5e8f538c41ba156aca3b2f256a3c2592b3fa1e4603bf'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--load', action='store_true')
    parser.add_argument('--run-label', help='Unique evidence subdirectory for a repeat RAM load')
    args = parser.parse_args()
    if args.run_label and not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_label):
        parser.error('Invalid run label')
    fw = (ROOT / 'evidence' / REV / 'nuttx.bin').read_bytes()
    assert len(fw) == 2803832 and hashlib.sha256(fw).hexdigest() == SHA
    code = CODE.replace('device-intent-20260915', REV)
    code = code.replace('velavision_device_intent_20260915', 'velavision_skin_command_20260916')
    code = code.replace('2799680', '2803832')
    code = code.replace('c3b862d2c62ced7504e1c7a4babfe317fb0c18aeee285c1c3b7f133939c5e137', SHA)
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
