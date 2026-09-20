import difflib,hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[2]
src=H.parent/'native-sherpa-offline-stage-v3/sources/kaldifst/kaldifst/csrc/kaldi-io.cc'
s=src.read_text();new=s
for cls,end in [('PipeOutputImpl','Output::Output('),('PipeInputImpl','/*\n#else')]:
 start=new.index('class '+cls+' :'); stop=new.index(end,start)
 new=new[:start]+'#if !defined(__NuttX__)\n'+new[start:stop]+'#endif  // !__NuttX__: no process pipes\n\n'+new[stop:]
for kind in ('Output','Input'):
 old='    impl_ = new Pipe'+kind+'Impl();'
 replacement='#if defined(__NuttX__)\n    KALDIFST_WARN << "Process pipe '+kind.lower()+' is unsupported on NuttX";\n    return false;\n#else\n'+old+'\n#endif'
 assert new.count(old)==1
 new=new.replace(old,replacement)
(H/'kaldi-io.cc').write_text(new,newline='\n')
(H/'candidate.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),new.splitlines(True),fromfile='a/kaldifst/csrc/kaldi-io.cc',tofile='b/kaldifst/csrc/kaldi-io.cc')),newline='\n')
paths=[src,R/'evidence/native-sherpa-link1-20260911/result.json',R/'evidence/native-sherpa-link1-20260911/missing.txt']
sherpa=R/'work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9/sherpa-onnx/csrc'
paths += [sherpa/n for n in ('file-utils.cc','online-paraformer-model.cc')]
(H/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2))
