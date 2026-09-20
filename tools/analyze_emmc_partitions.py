"""Summarize verified GPT diagnostic output, never infer permission to write."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();d=json.loads(a.input.read_text(encoding='utf-8'))
assert d['prompt_returned']
assert any('EMMC GPT rc=0 primary_backup_crc=PASS' in x for x in d['lines'])
parts=[];sectors=None;expected=None
for line in d['lines']:
    if line.startswith('EMMC init rc=0 '):sectors=int(re.search(r' sectors=(\d+)',line)[1])
    if line.startswith('EMMC GPT rc=0 '):expected=int(re.search(r' partitions=(\d+)',line)[1])
    m=re.fullmatch(r'EMMC partition name=(.*?) first=(\d+) last=(\d+) sectors=(\d+)',line)
    if m:
        name,first,last,count=m.groups();first,last,count=map(int,(first,last,count))
        assert count==last-first+1 and first<=last
        parts.append(dict(name=name,first=first,last=last,sectors=count,bytes=count*512))
assert sectors and len(parts)==expected
parts.sort(key=lambda x:x['first']);gaps=[]
for part in parts:assert 0<part['first']<=part['last']<sectors
for left,right in zip(parts,parts[1:]):
    assert left['last']<right['first']
    if left['last']+1<right['first']:
        gaps.append(dict(first=left['last']+1,last=right['first']-1,
                         note='Gap between GPT partitions; bootloader reservations and write authorization NOT established'))
out=dict(device_sectors=sectors,bytes=sectors*512,partitions=parts,inter_partition_gaps=gaps,
         filesystems_identified=False,write_authorized=False,
         note='No filesystem probing/mounting or storage modification; no start/end free-space inference')
assert not a.out.exists()
a.out.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(dict(partitions=len(parts),gaps=len(gaps),bytes=sectors*512)))
