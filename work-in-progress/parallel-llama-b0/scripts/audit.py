from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[1];out=Path(sys.argv[1]).resolve()
assert out.is_relative_to((R/'evidence').resolve())
build=out/'build';tc=Path(r'D:\software\mingw64\mingw64\bin')
rows=[]
for name,cmd in [('nm-registry',[tc/'nm.exe','-u',build/'llama/ggml/src/ggml.a']),
                 ('exe-imports',[tc/'objdump.exe','-p',build/'b0-probe.exe']),
                 ('compiler',[tc/'gcc.exe','--version'])]:
    p=subprocess.run([str(x) for x in cmd],capture_output=True,timeout=30)
    (out/(name+'.log')).write_bytes(p.stdout+p.stderr)
    rows.append(dict(name=name,command=[str(x) for x in cmd],returncode=p.returncode))
    assert p.returncode==0,name
symbols=(out/'nm-registry.log').read_text(errors='replace')
for x in ['LoadLibrary','GetProcAddress','FreeLibrary','dlopen','dlclose','dlsym','filesystem']:
    assert x not in symbols,x
comp=json.loads((build/'compile_commands.json').read_text(encoding='utf8'))
assert not any('-fopenmp' in row['command'] for row in comp)
assert not any('/common/' in row['file'].replace('\\','/') or '/examples/' in row['file'].replace('\\','/') for row in comp)
assert any('candidate/ggml-backend-reg.cpp' in row['file'].replace('\\','/') for row in comp)
assert not any('/src/ggml-backend-reg.cpp' in row['file'].replace('\\','/') for row in comp)
inputs=[]
for row in json.loads((R/'input/sources.json').read_text(encoding='utf8')):
    current=hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()
    inputs.append(dict(**row,current_sha256=current,unchanged=current==row['sha256']))
archives=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
          for p in sorted(build.rglob('*.a')) if p.name!='objects.a']
(out/'audit.json').write_text(json.dumps(dict(commands=rows,input_verification=inputs,archives=archives,
    static_registry_dynamic_imports=False,openmp=False,compile_units=len(comp),inference=False),ensure_ascii=False,indent=2),encoding='utf8')
(out/'compiled-source-manifest.json').write_text(json.dumps([
    dict(path=row['file'],sha256=hashlib.sha256(Path(row['file']).read_bytes()).hexdigest()) for row in comp],indent=2),encoding='utf8')
print('audit_pass',len(archives),'archives',len(comp),'compile_units')
