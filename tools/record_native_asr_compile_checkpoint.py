"""Record real ASR archive compilation separately from inference acceptance."""
import json,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[1]
build=json.loads((R/'evidence/native-sherpa-asr-build2-20260911/result.json').read_text());assert build['exit_code']==0
link=json.loads((R/'evidence/native-sherpa-link1-20260911/result.json').read_text());assert link['exit_code']==0
p=R/'project-manifest.json';m=json.loads(p.read_text())
m['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
m['native_asr_runtime'].update(sherpa_c_api_compiled=True,sherpa_abi='native NuttX AArch64 libc++',
 sherpa_symbol_missing=['popen','pclose'],asr_kernel_build='in_progress',asr_model_run=False,tts_model_run=False)
m['native_asr_runtime']['evidence']+=['evidence/native-sherpa-asr-build2-20260911','evidence/native-sherpa-link1-20260911','evidence/native-ort-asr-config2-20260911']
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
entry='''
2026-09-11 ASR实际编译推进：Sherpa1.12.14 C API第二轮198步全部成功，耗时248.017秒；KissFFT仅修复两个宏的命名冲突，普通日志语义六项预处理结果保留。未禁用原编译检查。真实Recognizer入口按需链接成功，396个外部强符号中SDK仅缺popen/pclose，暂未最终固件链接。该符号审计仍使用Add-only ORT，不代表ASR模型可用。28项ASR算子注册已另目录生成并配置成功，正在重新编译ORT；生成器首轮缺FlatBuffers Python导入路径，复用锁定源修正后通过，无新包安装。当前Add固件RAM传输进行中，尚未启动；不作板端ASR/TTS运行声明。
本轮真实日志导出：13文件、20,879事件、6会话，原版官方校验ALL OK；校验只覆盖该次采集时点，后续开发事件下次继续导出。
'''
for name in ('docs/代码日志对应表.md','docs/原生语音运行库编译推进_20260911.md'):
 with (R/name).open('a',encoding='utf-8') as f:f.write(entry)
