"""Record the actual split between host cloud success and pending K7 work."""
import datetime
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
p=root/'project-manifest.json'
d=json.loads(p.read_text(encoding='utf-8'))
d['updated_at']=now
c=d['current_device']
c.update(state='Old heartbeat reset the board into Fastboot at 18:57. Old loader PID 308144 was stopped after identity verification. Ubuntu last enumerated CH340 only; no fresh RAM boot after reset. Historical 17:58 BLE service snapshot is invalid.',ram_booted=False,ble_service_ready=False,radio_host_online=False,wifi_shared_service_online=False,native_network=False,ble_wifi_provisioning_available=False)
c['evidence']='Ubuntu work-in-progress/asr-direct-cache-20260914/watch-direct-clean-tls-heartbeat-20260914.log'
build=json.loads((root/'evidence/cloud-radio-build-20260914/arm64-result-final.json').read_text())
d['pending_firmware'].update(revision='cloud-radio-20260914',status='Radio snapshot CLI enabled and ARM64 compiled after missing header fix. Cloud worker, audio WebSocket, TLS/runtime prerequisites and board acceptance remain pending.',radio_readiness_arm64_built=True,firmware_sha256=build['files']['nuttx.bin']['sha256'],firmware_bytes=build['files']['nuttx.bin']['bytes'],evidence='evidence/cloud-radio-build-20260914/arm64-result-final.json')
d['streaming_asr_gateway']={'provider':'Alibaba Cloud Bailian','model':'paraformer-realtime-v2','route':'/asr/stream','server':'127.0.0.1:8000','server_pid':34304,'real_synthetic_test_passed':True,'first_nonempty_partial_ms':640,'audio_duration_ms':3920,'final_ms':4281,'tts_ms':1219,'isolated_tests':11,'board_tested':False,'mimo_streaming_tested':False,'credentials_saved':False,'evidence':'evidence/speech-stream-live-20260914/result.json','document':'docs/speech-service流式ASR接入_20260914.md'}
d['handoff']['next_priority']='Complete K7 microphone PCM WebSocket sender to the now live-tested speech-service streaming gateway; restore current BLE RAM firmware with verified OTG and test real provisioning. The gateway uses Alibaba, not MiMo; keep provider distinction explicit.'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note='''
## 2026-09-14 流式 ASR 接续覆盖

用户最新提供 `E:/openvela/语音模块/speech-service`，明确 ASR 必须流式。
该服务原为阿里云百炼批式 ASR/TTS。主仓新增 `/asr/stream` 网关，以真实
Paraformer realtime-v2 WebSocket 协议双向转发 PCM；与原 app 挂接启动，原目录和
密钥配置未改。11项隔离测试通过；真实合成句 TTS 1219 ms，3.92秒PCM流式发送，
640 ms首个非空 partial、4281 ms final，识别完整测试句。不是小米流式验收。
详见 `docs/speech-service流式ASR接入_20260914.md` 和 `evidence/speech-stream-live-20260914/result.json`。
本机服务 PID34304，监听127.0.0.1:8000；K7网络端采集/WebSocket尚未接入。

板端状态更正：旧 heartbeat 18:57把板子重启到Fastboot，17:58运行快照失效。
已停止旧加载器308144并更新定时任务，不能恢复旧语音密码固件。
新的radio-status候选ARM64已成功构建，BIN 2782928字节，SHA256
`6efed4c48eaee8c51289f9d52a704203e7207799bd3aaf7f213dc790fa891a54`；未上板。
radio bridge漏采整个断开重连区间时的旧TLS/API门禁继承已修，O0/O2各7组通过。
前端迟到探针/回报状态污染已修，Node32项通过；runtime owner O0/O2各7组通过但未集成。
用户已要求停止子代理，当前均已停止，不自动重启。

AI日志：原有writer锁覆盖导出，但取锁前read会在Windows锁争用时直接失败。
修复及13项回归见 `docs/AI日志写入锁修复_20260914.md`。
实时独立校验改用 `tools/validate_project_logs.py`，它持锁调用原版官方校验器。
旧独立无锁校验曾读取JSONL/manifest混合快照；不能笼统说原来没有写锁。
'''
for rel in ['docs/模型接力交接_20260914.md','docs/代码日志对应表.md']:
    with (root/rel).open('a',encoding='utf-8') as f:f.write(note)
p=root/'README.md'
s=p.read_text(encoding='utf-8')
s=s.replace('## 当前状态','## 当前状态\n\n**最新流式ASR：**用户提供的阿里云 speech-service 已增加真实双向 WebSocket ASR。合成语音测试首个非空文字640ms、整句4281ms，TTS1219ms；11项隔离回归通过。新radio-status固件已ARM64构建，但K7仍待OTG恢复及麦克风WebSocket接入。见 [流式接入](docs/speech-service流式ASR接入_20260914.md)。',1)
p.write_text(s,encoding='utf-8')
with (root/'docs/speech-service流式ASR接入_20260914.md').open('a',encoding='utf-8') as f:
    f.write('\n## 真实云复测\n\n本机网关已运行（PID34304），健康返回ok。合成句“你好，联网成功。现在开始测试实时语音识别。”经真实TTS返回125440字节PCM（3.92秒），耗时1219ms；以20ms节奏上传流式ASR，640ms首个非空partial，4281ms返回完整final并completed。证据 `evidence/speech-stream-live-20260914/result.json`。这是一次合成句验证，不是板端麦克风、准确率统计或长期稳定验收。\n')
print(now)
