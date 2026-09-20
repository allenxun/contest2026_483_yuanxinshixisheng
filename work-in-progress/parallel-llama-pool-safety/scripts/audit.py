from pathlib import Path
import hashlib,json,subprocess,sys,tarfile
R=Path(__file__).resolve().parents[1];out=Path(sys.argv[1]).resolve()
assert out.is_relative_to((R/'evidence').resolve())
nm=Path(r'D:\software\mingw64\mingw64\bin\nm.exe')
cmd=[str(nm),'-u',str(out/'build/llama/ggml/src/ggml-cpu.a')]
p=subprocess.run(cmd,capture_output=True,timeout=30)
(out/'cpu-undefined.log').write_bytes(p.stdout+p.stderr)
assert p.returncode==0
symbols=p.stdout.decode(errors='replace')
assert 'pthread_create' in symbols and 'pthread_join' in symbols and 'pthread_cond_wait' in symbols
assert 'CreateThread' not in symbols
compile_rows=json.loads((out/'build/compile_commands.json').read_text(encoding='utf8'))
candidate=[row for row in compile_rows if row['file'].replace('\\','/').endswith('/candidate/ggml-cpu.c')]
assert len(candidate)==1 and 'GGML_POOL_POSIX' in candidate[0]['command']
assert not any('-fopenmp' in row['command'] for row in compile_rows)
inputs=[]
for row in json.loads((R/'input/sources.json').read_text(encoding='utf8')):
    current=hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()
    inputs.append(dict(**row,current_sha256=current,unchanged=current==row['sha256']))
(out/'audit.json').write_text(json.dumps(dict(symbol_command=cmd,returncode=p.returncode,
    real_pthread_imports=True,win32_create_emulation=False,openmp=False,input_verification=inputs),ensure_ascii=False,indent=2),encoding='utf8')
print('audit_pass','inputs_unchanged',all(x['unchanged'] for x in inputs))
