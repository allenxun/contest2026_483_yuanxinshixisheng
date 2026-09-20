"""Offline model of proposed MSC first-read acceptance gates, not a driver."""
import argparse
import json

def request_errors(blocks, blocksize, lba, count, limit=4096):
    errors=[]
    if not 1 <= blocks <= 0xffffffff: errors.append('capacity10 unsupported/overflow')
    if blocksize not in (512,1024,2048,4096): errors.append('unsupported sector size')
    if not 0 <= lba <= 0xffffffff: errors.append('LBA outside READ10')
    if not 1 <= count <= 0xffff: errors.append('READ10 count outside 1..65535')
    if lba < 0 or lba >= blocks or count > blocks-lba: errors.append('outside capacity')
    if blocksize * count > limit: errors.append('exceeds initial bounded read')
    return errors

def completion_errors(t):
    errors=request_errors(t['blocks'],t['blocksize'],t['lba'],t['count'])
    expected=t['blocksize']*t['count']
    if t['opcode']!=0x28: errors.append('not READ10')
    if t['cbw_bytes']!=31: errors.append('short/invalid CBW transfer')
    if t['data_bytes']!=expected: errors.append('short/invalid data transfer')
    if t['csw_bytes']!=13: errors.append('short/invalid CSW transfer')
    if t['signature']!=0x53425355: errors.append('invalid CSW signature')
    if t['csw_tag']!=t['cbw_tag']: errors.append('CSW tag mismatch')
    if t['residue']!=0 or t['status']!=0: errors.append('CSW residue/status failure')
    return errors

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',help='JSON transaction metadata from an independently verified trace')
    args=parser.parse_args()
    with open(args.input,encoding='utf-8') as stream: transaction=json.load(stream)
    errors=completion_errors(transaction)
    print(json.dumps(dict(passed=not errors,errors=errors,hardware_proven=False,trace_completeness_proven=False),indent=2))
    raise SystemExit(bool(errors))
