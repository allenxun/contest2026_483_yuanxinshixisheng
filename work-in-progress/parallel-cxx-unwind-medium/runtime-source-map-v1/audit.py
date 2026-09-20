"""Local provenance and source-map extraction; no SDK or network operations."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REF=ROOT/'evidence/gcc-unwind-reference-20260910'
DIAG=ROOT/'evidence/cxx-eh-20260910/diagnostics'
def entry(p):
    data=p.read_bytes()
    return dict(path=str(p.relative_to(ROOT)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
source_index=json.loads((REF/'sources.json').read_text(encoding='utf-8'))
references=[]
for spec in source_index['sources']:
    actual=entry(REF/spec['path'])
    actual.update(url=spec['url'],matches_index=actual['sha256']==spec['sha256'] and actual['bytes']==spec['bytes'])
    references.append(actual)
paths=[REF/'sources.json']+[DIAG/p for p in ['abi-macros.txt','uw_init_context_1.txt','_Unwind_Find_FDE.txt','__cxa_get_globals.txt','__cxa_get_globals_fast.txt']]
paths.append(HERE.parent/'cold-failure-v1/symbols.txt')
paths.extend([ROOT/'README.md',ROOT/'project-manifest.json',ROOT/'docs/代码日志对应表.md'])
extracts=[]
for p in [REF/'unwind-dw2.c',REF/'unwind-dw2-fde.c',REF/'gthr-posix.h',REF/'gthr-single.h']:
    selected=[]
    for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
        if re.search(r'#\s*include|__GTHREAD|__gthread_once|__gthread_mutex_(lock|unlock)|GTHREAD_USE_WEAK|GTHR_ACTIVE_PROXY',line):
            selected.append(dict(line=i,text=line))
    extracts.append(dict(path=str(p.relative_to(ROOT)),lines=selected))
symbol_text=(HERE.parent/'cold-failure-v1/symbols.txt').read_text(encoding='utf-8')
symbols={}
for name in ['pthread_once','pthread_mutex_lock','pthread_mutex_unlock','pthread_mutex_init','pthread_getspecific','pthread_setspecific','pthread_key_create','pthread_key_delete','pthread_cancel','pthread_mutexattr_settype']:
    matches=[line for line in symbol_text.splitlines() if re.search(r'\bFUNC\s+GLOBAL\b',line) and line.rstrip().endswith(' '+name)]
    symbols[name]=dict(linked_definitions=matches,missing_does_not_prove_api_absent=True)
report=dict(reference_scope=source_index['scope'],references=references,inputs=[entry(p) for p in paths],
            extracts=extracts,linked_pthread_symbols=symbols,reference_hashes_match=all(x['matches_index'] for x in references),
            built=False,hardware_access=False,network_access=False)
(HERE/'audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
delivery=dict(files=[entry(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='delivery.json'],
              reference_hashes_match=report['reference_hashes_match'],scope='local source dependency review, no runtime build')
(HERE/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf-8')
print('references={} hashes_match={} built=False network=False hardware=False'.format(len(references),report['reference_hashes_match']))
raise SystemExit(0 if report['reference_hashes_match'] else 1)
