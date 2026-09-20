from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/configure_native_ort_session2.py').read_text().replace('native-ort-session-config2','native-ort-session-config3').replace('config-attempt2','config-attempt3')
s=s.replace('import hashlib,json,shlex,subprocess,tarfile','import hashlib,json,shlex,subprocess,tarfile,os')
start=s.index('def patch(name,file,tree):');end=s.index('\ntry:',start)
s=s[:start]+'''def patch(name,file,tree):
 data=file.read_bytes().replace(bytes([13,10]),bytes([10]))
 p=subprocess.run(['patch','--dry-run','-R','--binary','--ignore-whitespace','-p1'],input=data,cwd=tree,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (O/(name+'-already-applied.log')).write_bytes(p.stdout)
 if p.returncode:raise RuntimeError(p.stdout.decode())
 records.append(dict(name=name,mode='reverse dry-run verified earlier patch',patch_sha256=hashlib.sha256(data).hexdigest(),exit_code=0))
os.environ['PYTHONPATH']=str(S/'sources/flatbuffers/python')
'''+s[end:]
target=R/'tools/configure_native_ort_session3.py';assert not target.exists()
compile(s,str(target),'exec');target.write_text(s)
