"""Strict offline k7storage evidence-bundle checks. No device operations."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
FAULT=re.compile(r'\b(?:error|fail|failed|fault|abort|panic|assert|assertion|sched_dumpstack|backtrace)\b|re-enumeration required',re.I)
NODE=re.compile(r'/dev/sd[a-z]')
SHA=re.compile(r'[0-9a-f]{64}')
def sha(data): return hashlib.sha256(data).hexdigest()

def stage(data,command):
    errors=[]; records=[]
    try: text=data.decode('utf-8','strict')
    except UnicodeDecodeError: return ['invalid UTF-8/truncated bytes'],[]
    lines=[ANSI.sub('',line).strip() for line in text.splitlines()]
    lines=[line for line in lines if line]
    if not lines or lines[0] not in ('k7storage '+command,'nsh> k7storage '+command): errors.append('missing/extraneous command echo')
    if not lines or lines[-1]!='nsh>': errors.append('missing terminal completion prompt')
    for line in lines:
        if any(ord(ch)<32 and ch!='\t' for ch in line): errors.append('invalid terminal control bytes')
        if FAULT.search(line): errors.append('fault/failure diagnostic')
    for line in lines[1:-1]:
        if 'k7storage ' in line or line.startswith('nsh>'): errors.append('mixed command/prompt')
        if line.startswith('USB_') and not line.startswith('USB_STORAGE '): errors.append('truncated/unknown USB protocol')
        if 'USB_STORAGE' in line:
            if not line.startswith('USB_STORAGE '): errors.append('interleaved/truncated protocol'); continue
            body=line[len('USB_STORAGE '):]
            kind='read' if body.startswith('read ') else 'fields'
            if kind=='read': body=body[5:]
            fields={}
            for token in body.split():
                if token.count('=')!=1: errors.append('unknown/malformed protocol token'); continue
                key,value=token.split('=')
                if key in fields or not value: errors.append('duplicate/missing field')
                fields[key]=value
            records.append((kind,fields))
    expected=dict(command=command.split()[0],result='0',mount_attempted='0')
    if not records or records[-1]!=('fields',expected): errors.append('missing/wrong final command result')
    if sum('command' in f for _,f in records)!=1: errors.append('duplicate/missing command result')
    return errors,records

def evaluate(captures,node,scope,identity,identity_dir):
    errors=[]; parsed={}; hashes={k:sha(v) for k,v in captures.items()}
    def fail(message): errors.append(message)
    if not NODE.fullmatch(node): fail('invalid requested node')
    commands={'before':'list','start':'start','after':'list','read':'read '+node}
    for name,command in commands.items():
        err,records=stage(captures[name],command)
        errors.extend(name+': '+e for e in err); parsed[name]=records
    def nodes(name):
        rows=parsed[name]; found=[]
        for kind,f in rows[:-2]:
            if kind!='fields' or set(f)!={'node'} or not NODE.fullmatch(f.get('node','')): fail(name+': malformed node list')
            else: found.append(f['node'])
        if len(rows)<2 or rows[-2]!=('fields',{'nodes':str(len(found))}): fail(name+': missing/wrong nodes count')
        if len(found)!=len(set(found)): fail(name+': duplicate node')
        return set(found)
    before=nodes('before'); after=nodes('after')
    if node in before or after-before!={node} or not before.issubset(after): fail('requested node is not the sole newly enumerated node')
    if len(parsed['start'])!=1: fail('start: extra protocol records')
    read=parsed['read']
    summary={}
    if len(read)!=2 or read[0][0]!='read': fail('read: missing/duplicate summary')
    else:
        summary=read[0][1]
        keys={'node','sector_size','sectors','readonly','lba','reads','crc32','repeated','boot_signature','exfat_oem'}
        if set(summary)!=keys: fail('read: unexpected/missing fields')
        for key,value in {'node':node,'readonly':'1','lba':'0','reads':'2','repeated':'1'}.items():
            if summary.get(key)!=value: fail('read: '+key+' mismatch')
        if summary.get('sector_size') not in ('512','1024','2048','4096'): fail('read: unsupported sector size')
        sectors=summary.get('sectors','')
        if not re.fullmatch(r'[1-9][0-9]*',sectors) or not 1<=int(sectors)<=0xffffffff: fail('read: invalid capacity')
        if not re.fullmatch(r'[0-9a-f]{8}',summary.get('crc32','')): fail('read: invalid CRC32')
        for key in ('boot_signature','exfat_oem'):
            if summary.get(key) not in ('0','1'): fail('read: invalid '+key)
    frozen=json.loads((HERE/'input.json').read_text(encoding='utf-8'))
    if sha((HERE/'k7storage_main.frozen.c').read_bytes())!=frozen['source_sha256']: fail('frozen source hash mismatch')
    if scope not in ('synthetic','target') or identity.get('scope')!=scope: fail('identity scope mismatch')
    if identity.get('evidence_origin')!=('synthetic' if scope=='synthetic' else 'device-capture'): fail('evidence origin/scope mismatch')
    if identity.get('capture_sha256')!=hashes: fail('external identity capture hashes mismatch')
    if identity.get('node')!=node: fail('external identity node mismatch')
    if identity.get('source_sha256')!=frozen['source_sha256']: fail('external source hash mismatch')
    if not re.fullmatch(r'[0-9a-f]{4}',identity.get('vid','')) or not re.fullmatch(r'[0-9a-f]{4}',identity.get('pid','')): fail('missing/invalid external VID/PID')
    if not SHA.fullmatch(identity.get('firmware_sha256','')): fail('missing firmware hash')
    if not identity.get('run_id') or identity.get('ordered_phases')!=['before','start','after','read']: fail('missing ordered run attestation')
    if identity.get('identity_reviewed') is not True or not identity.get('reviewer'): fail('external identity review required')
    bound=[]
    for key in ('enumeration_evidence','build_evidence'):
        ref=identity.get(key,{})
        try:
            path=identity_dir/ref['path']; raw=path.read_bytes()
            if not raw or sha(raw)!=ref.get('sha256'): raise ValueError()
            bound.append(dict(kind=key,path=str(path),sha256=sha(raw)))
        except (OSError,KeyError,TypeError,ValueError): fail('missing/mismatched '+key)
    return dict(passed=not errors,scope=scope,errors=errors,node=node,read_summary=summary,
                capture_sha256=hashes,external_artifacts=bound,
                physical_identity_independently_proven=False,boot_freshness_independently_proven=False,
                target_test_performed_by_parser=False,raw_sector_equality_independently_proven=False,
                interpretation='Output contract and externally reviewed evidence binding only; source code defines repeated=1 semantics. No nonce exists in this protocol.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('before','start','after','read'): p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--node',required=True); p.add_argument('--scope',required=True,choices=['synthetic','target'])
    p.add_argument('--identity',required=True,type=Path); p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        identity=json.loads(a.identity.read_text(encoding='utf-8'))
        result=evaluate({key:getattr(a,key).read_bytes() for key in ('before','start','after','read')},a.node,a.scope,identity,a.identity.parent)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        result=dict(passed=False,errors=['invalid/missing input: '+str(exc)],scope=a.scope)
    rendered=json.dumps(result,indent=2)
    if a.output: a.output.write_text(rendered+'\n',encoding='utf-8')
    print(rendered); return 0 if result['passed'] else 1
if __name__=='__main__': raise SystemExit(main())
