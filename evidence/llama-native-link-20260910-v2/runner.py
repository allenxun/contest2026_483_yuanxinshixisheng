
import hashlib,json,shlex,subprocess
from pathlib import Path
S=Path('/home/swl/openvela/work/llama-native-20260910T071713Z')
B=Path('/home/swl/openvela/cmake_out/velavision_cxx_locale_20260910')
O=S/'link-result-v2';O.mkdir()
report=json.loads((S/'result/result.json').read_text());assert report['passed']
ninja='/home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja'
commands=subprocess.check_output([ninja,'-t','commands','nuttx'],cwd=B,text=True)
line=commands.splitlines()[-1];tokens=shlex.split(line)
i=next(i for i,x in enumerate(tokens) if x.endswith('aarch64-none-elf-g++'))
cmd=[]
for x in tokens[i:]:
 if x=='&&':break
 cmd.append(x)
assert cmd[cmd.index('-o')+1]=='nuttx'
cmd[cmd.index('-o')+1]=str(O/'llama-link.elf')
cmd=[x.replace('-Map=nuttx.map','-Map='+str(O/'llama-link.map')) for x in cmd]
roots=['llama_model_load_from_file','llama_init_from_model','llama_decode','llama_tokenize',
       'ggml_pool_create_checked','ggml_pool_destroy_checked','ggml_pool_required_bytes']
cmd[1:1]=['-Wl,-u,'+x for x in roots]+[str(S/'result'/(str(i)+'.o')) for i in range(report['units'])]
inputs={}
for x in cmd:
 p=Path(x) if Path(x).is_absolute() else B/x
 if x.endswith(('.a','.o')) and p.is_file():inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
inputs[str(B/'dramboot.ld.tmp')]=hashlib.sha256((B/'dramboot.ld.tmp').read_bytes()).hexdigest()
p=subprocess.run(cmd,cwd=B,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(O/'link.log').write_bytes(p.stdout)
result=dict(command=cmd,exit_code=p.returncode,roots=roots,input_hashes=inputs,
 scope='Standalone link against completed NuttX locale build; no firmware integration, boot or model')
if p.returncode==0:
 elf=O/'llama-link.elf';result['elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest()
 nm=Path(cmd[0]).with_name('aarch64-none-elf-nm')
 out=subprocess.check_output([str(nm),str(elf)],text=True)
 defined={parts[-1]:parts[-2] for line in out.splitlines() if len(parts:=line.split())>=3}
 result['roots_defined_text']={x:defined.get(x) in {'T','t'} for x in roots}
 result['all_roots_defined']=all(result['roots_defined_text'].values())
 assert result['all_roots_defined'],result['roots_defined_text']
 result['correction']='Prior index checked name presence, which counted an undefined misspelled forced symbol; this gate requires actual text definitions for the real checked API.'
(O/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(p.stdout.decode(errors='replace')[-5000:]);print('LINK_EXIT',p.returncode)
