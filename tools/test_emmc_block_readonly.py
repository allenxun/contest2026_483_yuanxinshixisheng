"""Run the block-driver policy test against a fake inode registry, no disk I/O."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'app/k7emmc';E=R/'evidence/emmc-source-review-20260910'
cmd=['D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11','-Wall','-Wextra','-Werror','-O2',
     str(S/'test_block_readonly.c'),'-o',str(E/'test_block_readonly.exe')]
subprocess.run(cmd,check=True,timeout=60)
r=subprocess.run([str(E/'test_block_readonly.exe')],check=True,capture_output=True,text=True,timeout=10)
result=dict(command=cmd,exit_code=r.returncode,stdout=r.stdout,hardware_accessed=False,
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
             [S/'block_readonly.inc',S/'test_block_readonly.c',S/'sdhci_command.h',S/'sdhci_read.h',S/'gpt_readonly.h']})
(E/'host-block-test.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(r.stdout,end='')
