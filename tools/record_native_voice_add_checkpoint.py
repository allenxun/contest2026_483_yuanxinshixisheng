"""Record native build/transfer progress without claiming model execution."""
import json,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
build=json.loads((R/'evidence/build/voice-ort-add-20260911/verification.json').read_text())
m['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
m['native_asr_runtime'].update(full_session_build='passed',firmware_linked=True,add_model_run=False,
 asr_model_run=False,tts_model_run=False,
 evidence=['evidence/native-ort-session-build61-20260911','evidence/native-session-link2-20260911',
 'evidence/build/voice-ort-add-20260911','evidence/native-sherpa-asr-config2-20260911'])
m['pending_firmware']=dict(revision=build['revision'],sha256=build['artifacts']['nuttx.bin']['sha256'],
 build_passed=True,ram_transfer_in_progress=True,booted=False,hardware_tested=False)
m['current_device']=dict(state='U-Boot; diagnostic image RAM transfer in progress',wifi_online=False,
 ble_service_started=False,asr_integrated=False,tts_integrated=False,
 previous_verified_revision='voice-owner-20260910',evidence='evidence/voice-ort-add-20260911')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text();old='完整CPU Session配置通过并进入编译，尚未完成固件链接或ASR/TTS模型运行，不能开始纯语音配网验收。'
assert old in s
s=s.replace(old,'完整CPU Session与真实C API依赖已编译、最终固件链接通过；带显式 Add 诊断入口的镜像正在 RAM 传输，当前处于 U-Boot，原无线服务已暂停。ASR第二轮配置通过、库编译进行中；尚未执行板端 Add 或 ASR/TTS 模型，不能开始纯语音配网验收。')
p.write_text(s,encoding='utf-8')
entry='''
2026-09-11 原生运行库增量：ORT 1.17.1完整CPU Session静态库编译通过；真实nsync及NuttX localeconv补齐后按需链接缺失强符号0。voice-ort-add-20260911正式独立固件编译成功，BIN SHA256 522047a5f8d6197ea0285227e581f3bce06e04ed23fb101af3dadc61b4f6fdd2，10,514,736字节；运行末址0x4129a000，异常表17477 FDE及首项注册静态检查通过。该版本仅显式Add诊断，尚未运行，不代表ASR/TTS。主会话已安全重启至U-Boot并开始CRC门禁RAM传输，没有刷写。
ASR配置2采用kaldifst1.7.17/OpenFST2024-06-19和Eigen实际C++11探测，通过；真实库编译开始。第一次传输因密钥权限失败、第二次归档路径未规范化被哈希门禁拒绝，均未伪造成功，修正后配置通过。
空间清理：仅删除73个历史构建目录中90,700个可再生成对象文件；893个固件/归档/配置等保护文件哈希全部不变，Ubuntu根分区可用从约1.3GiB恢复约21.2GiB。证据evidence/vm-space-cleanup-20260911；源码、SDK工具链、模型、原始日志未删。以上AI日志需后续真实导出并运行官方校验器。
'''
for name in ('docs/代码日志对应表.md','docs/原生语音运行库编译推进_20260911.md'):
 with (R/name).open('a',encoding='utf-8') as f:f.write(entry)
