"""Record native build evidence without turning compilation into device success."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
deps=json.loads((R/'evidence/native-static-deps4-20260911/result.json').read_text())
closure=json.loads((R/'evidence/native-voice-link-audit3-20260911/result.json').read_text())
config=json.loads((R/'evidence/native-ort-session-config91-20260911/result.json').read_text())
assert deps['build']['exit_code']==0 and closure['missing_from_sdk_archives']==0
assert any(x.get('name')=='configure' and x['exit_code']==0 for x in config['records'])
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
m['native_asr_runtime']=dict(common_translation_units=21,static_dependency_archives=30,
 common_relocatable_link=True,common_external_symbols_found_in_sdk=True,
 full_session_configured=True,full_session_build='in_progress',firmware_linked=False,
 asr_model_run=False,tts_model_run=False,
 evidence=['evidence/native-static-deps4-20260911','evidence/native-voice-link-audit3-20260911','evidence/native-ort-session-config91-20260911'])
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';text=p.read_text(encoding='utf-8')
old='ORT common 的21个源文件已全部原生编译通过，静态依赖链接和模型运行仍未完成，不能开始纯语音配网验收。'
new='ORT common 21个源文件和30个静态依赖库已原生编译，正常按需链接的外部符号均有SDK实现；完整CPU Session配置通过并进入编译，尚未完成固件链接或ASR/TTS模型运行，不能开始纯语音配网验收。'
assert old in text;p.write_text(text.replace(old,new),encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n2026-09-11 原生语音运行库继续：static-deps4的138步/30个静态库编译通过；link-audit3正常archive抽取，21 common对象可重定位链接通过、172外部strong符号有SDK/libm/libgcc定义，非最终固件链接。session-config9真实Iconv编译归档、算子生成及完整NuttX CPU配置通过；749步构建进行中，ASR/TTS未运行。对应tools/build_native_voice_static_deps4.py、audit_native_voice_link_closure3.py、stage_native_ort_session.py、configure_native_ort_session9.py、build_native_ort_session.py。所有失败轮次保留，没有更换板端voice-owner镜像。\n')
