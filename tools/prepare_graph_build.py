"""Integrate fixed ggml CPU graph probe into its own diagnostic firmware."""
import hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-model-reader-medium/graph-probe-v1'
raw=(C/'delivery.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='724caf72dbb62b005d676e83f878a9d9626008ac976700dae60e574de1c63c4e'
for item in json.loads(raw)['files']:
    assert hashlib.sha256((C/item['path']).read_bytes()).hexdigest()==item['sha256']
inputs=json.loads((R/'evidence/llama-native-compile/20260910T071713Z/inputs.json').read_text())
B=R/'work-in-progress/parallel-llama-b0'
V=B/'vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
P=R/'work-in-progress/parallel-llama-pool-safety'
A=R/'app/k7graph';assert not A.exists();A.mkdir()
copied={}
for rel,digest in inputs['files'].items():
    if not (rel.startswith('vendor/ggml/') or rel.startswith(('candidate/','include/')) or rel=='vendor/LICENSE'):
        continue
    src=(V/rel[len('vendor/'):]) if rel.startswith('vendor/') else (B/rel if rel.endswith('ggml-backend-reg.cpp') else P/rel)
    data=src.read_bytes()
    if any(x['path']==rel for x in inputs['derivations']):
        data=re.sub(r'\bUNUSED\b','GGML_LOCAL_UNUSED',data.decode('utf-8')).replace('\r\n','\n').encode('utf-8')
    assert hashlib.sha256(data).hexdigest()==digest,rel
    dest=A/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    copied[rel]=dict(source=str(src.relative_to(R)),sha256=digest)
for name in ['graph_probe.c','graph_probe.h','graph_probe_main.c']:
    data=(C/name).read_bytes();(A/name).write_bytes(data)
    copied[name]=dict(source=str((C/name).relative_to(R)),sha256=hashlib.sha256(data).hexdigest())
(A/'k7graph_main.c').write_text('#include "graph_probe.h"\nint main(int argc, char **argv) { return velavision_graph_probe_main(argc, argv); }\n',newline='\n')
units=[u for u in inputs['units'] if not u.startswith('vendor/src/')]
assert all((A/u).is_file() for u in units)
cmake='''if(CONFIG_EXAMPLES_K7GRAPH)
  include_directories(vendor/ggml/include vendor/ggml/src vendor/ggml/src/ggml-cpu include)
  add_compile_definitions(GGML_USE_CPU GGML_POOL_POSIX=1 GGML_SCHED_MAX_COPIES=4 _GNU_SOURCE)
  # Keep vendor warnings visible without inheriting application-specific fatality.
  add_compile_options(-Wno-error=undef -Wno-error=unused-function)
  nuttx_add_application(NAME k7graph SRCS k7graph_main.c graph_probe.c graph_probe_main.c
'''+''.join('    '+u+'\n' for u in units)+'''    STACKSIZE 16384 PRIORITY 100 MODULE ${CONFIG_EXAMPLES_K7GRAPH})
endif()
'''
(A/'CMakeLists.txt').write_text(cmake,newline='\n')
(A/'Kconfig').write_text('config EXAMPLES_K7GRAPH\n\ttristate "K7 real ggml CPU graph diagnostic"\n\tdepends on SMP && HAVE_CXX && LIBCXX && CXX_EXCEPTION\n\tdefault n\n',newline='\n')
(A/'README.md').write_text('''# 真实 CPU 张量图诊断

固定b5046 ggml、checked线程池、graph-probe-v1。入口k7graph both，2/4软件线程，64x64逐元素乘法，4096项独立校验；不加载权重，不是矩阵乘法或token推理。
此版本只接入CMake构建。默认未绑核，不能说已利用四颗A72。底层compute/join可能阻塞，主会话外部监督；不强杀后释放仍被线程使用的内存。上游部分OOM仍abort。
来源与文件哈希在evidence/graph-core-20260910/integration.json，许可证vendor/LICENSE。原始vendor冻结不改，局部UNUSED宏仅作命名空间派生。
''',encoding='utf-8')
E=R/'evidence/graph-core-20260910';E.mkdir()
(E/'integration.json').write_text(json.dumps(dict(files=copied,units=units,hardware_tested=False),indent=2)+'\n')
profile=R/'board/kickpi_k7/configs/velavision_graph_core_local/defconfig'
profile.parent.mkdir(parents=True)
s=(R/'board/kickpi_k7/configs/velavision_cxx_eh_local/defconfig').read_text()
profile.write_text(s+'\nCONFIG_EXAMPLES_K7GRAPH=y\n',newline='\n')
for name in ['build_cxx_eh.sh','build_cxx_eh_vm.py']:
    s=(R/'tools'/name).read_text().replace('cxx-eh','graph-core').replace('cxx_eh','graph_core')
    if name.endswith('_vm.py'):
        s=s.replace('paths=list(dict.fromkeys(paths))',"paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7graph').rglob('*')) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
        s=s.replace("['CONFIG_EXAMPLES_K7EH=y',", "['CONFIG_EXAMPLES_K7GRAPH=y','CONFIG_EXAMPLES_K7EH=y',")
    (R/'tools'/name.replace('cxx_eh','graph_core')).write_text(s,newline='\n')
print('Prepared native graph build:',len(units),'ggml units,',len(copied),'source files')
