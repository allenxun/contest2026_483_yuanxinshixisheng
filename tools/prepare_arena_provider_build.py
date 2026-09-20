"""Stage frozen minimal arena diagnostic as a separate application/revision."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-model-reader-medium/model-arena-provider-v1'
D=json.loads((C/'delivery.json').read_text())
for x in D['files']:
 p=C/x['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
A=R/'app/k7arena';assert not A.exists();A.mkdir()
files=['k7_target_provider.c','k7_target_provider.h','k7_arena_diagnostic.c','k7_arena_diagnostic.h','k7_arena_provider_main.c']
copied={}
for name,src in [(n,C/n) for n in files]+[(n,C/'input/buft'/n) for n in ['k7_host_buft.cpp','k7_host_buft.h']]:
 (A/name).write_bytes(src.read_bytes());copied[name]=dict(source=str(src.relative_to(R)),sha256=hashlib.sha256(src.read_bytes()).hexdigest())
(A/'k7arena_main.c').write_text('int velavision_arena_provider_main(int, char **);\nint main(int argc, char **argv) { return velavision_arena_provider_main(argc, argv); }\n',newline='\n')
(A/'CMakeLists.txt').write_text('''if(CONFIG_EXAMPLES_K7ARENA)
  include_directories(../k7graph/vendor/ggml/include ../k7graph/vendor/ggml/src ../k7graph/vendor/ggml/src/ggml-cpu)
  nuttx_add_application(NAME k7arena SRCS k7arena_main.c k7_target_provider.c
    k7_arena_diagnostic.c k7_arena_provider_main.c k7_host_buft.cpp
    STACKSIZE 16384 PRIORITY 100 MODULE ${CONFIG_EXAMPLES_K7ARENA})
endif()
''',newline='\n')
(A/'Kconfig').write_text('config EXAMPLES_K7ARENA\n\ttristate "K7 bounded ggml model arena diagnostic"\n\tdepends on EXAMPLES_K7GRAPH && CXX_EXCEPTION\n\tdefault n\n',newline='\n')
(A/'README.md').write_text('''# 显式模型池 ggml 诊断

入口 k7arena，独占模型池、最多1MiB，正常两个64x64张量共32KiB。8192项set/get及范围/归还检查；不计算图，不加载权重。
仅CMake接入，复用k7graph的固定b5046实现，不重复编译BSP arena。未编入host-mock/KAP_HOST_MAIN/K7_BUFT_TESTING。模型池/普通堆的失败、隔离和生命周期边界以来源候选HANDOFF为准。
来源哈希见evidence/arena-provider-20260910/integration.json；单次正常通过不等于OOM/全DDR/模型验收。
''',encoding='utf-8')
E=R/'evidence/arena-provider-20260910';E.mkdir()
(E/'integration.json').write_text(json.dumps(dict(files=copied,candidate_delivery_sha256=hashlib.sha256((C/'delivery.json').read_bytes()).hexdigest(),hardware_tested=False),indent=2)+'\n')
profile=R/'board/kickpi_k7/configs/velavision_arena_provider_local/defconfig';profile.parent.mkdir()
profile.write_text((R/'board/kickpi_k7/configs/velavision_graph_core_local/defconfig').read_text()+'\nCONFIG_EXAMPLES_K7ARENA=y\n',newline='\n')
for name in ['build_graph_core.sh','build_graph_core_vm.py']:
 s=(R/'tools'/name).read_text().replace('graph-core','arena-provider').replace('graph_core','arena_provider')
 if name.endswith('_vm.py'):
  # Keep the unchanged graph library source inventory while adding the new app.
  s=s.replace("R/'app/k7graph'", "R/'app/k7graph'")
  s=s.replace('paths=list(dict.fromkeys(paths))', "paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7arena').iterdir()) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
  s=s.replace("['CONFIG_EXAMPLES_K7GRAPH=y',", "['CONFIG_EXAMPLES_K7ARENA=y','CONFIG_EXAMPLES_K7GRAPH=y',")
 p=R/'tools'/name.replace('graph_core','arena_provider');assert not p.exists();p.write_text(s,newline='\n')
print('Separate k7arena sources/build prepared, no model or hardware execution')
