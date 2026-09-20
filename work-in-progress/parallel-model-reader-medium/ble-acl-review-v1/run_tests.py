from pathlib import Path
import subprocess
p=Path(__file__).resolve().parent;logs=[]
for opt in ['O0','O2']:
 exe=p/('codec-'+opt+'.exe')
 for cmd in [['D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic',str(p/'skw_packet.c'),str(p/'test_codec.c'),'-o',str(exe)],[str(exe)]]:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=15);logs.append('$ '+' '.join(cmd)+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n');(p/'test-output.txt').write_text(''.join(logs));assert r.returncode==0
print('O0/O2 actual codec synthetic boundary tests passed')
