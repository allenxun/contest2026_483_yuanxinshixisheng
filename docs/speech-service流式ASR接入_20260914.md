# speech-service 流式 ASR 接入

用户提供的 `E:/openvela/语音模块/speech-service` 是阿里云百炼服务，不是 MiMo。
既有 `/asr` 是 multipart 整段上传，`/tts` 返回 16 kHz mono S16LE PCM。
新增 `host/streaming_asr/gateway.py` 使用真实上游 WebSocket 双向音频协议；
`serve.py` 在原 FastAPI app 上挂载 `/asr/stream`，保留旧 HTTP 路由和原目录。
没有修改原 `.env`，也不向 K7 发放云 API key。

## 协议

连接 `ws://服务电脑IP:8000/asr/stream`，发送一次：

```json
{"type":"start","sample_rate":16000,"channels":1,"encoding":"pcm_s16le","frame_ms":20}
```

收到 `ready` 后发送二进制消息：4 字节 little-endian uint32 序号（从 0 开始）+
640 字节 PCM（20 ms）；上游仅收到 PCM，不含序号、WAV 头或 Base64。
每帧返回 `ack` 和 `next_seq`，客户端限制未确认帧，不能无限缓存。
服务端的上游发送有超时、接收队列有界，最长一次录音 60 秒。

识别同时返回 `partial`、`final`，包含 `sentence_id`、`revision` 和 `text`。
同一句的 partial 是替换快照，不是增量拼接。`final` 只结束一句，后续句子仍可录入。
客户端输入结束发送 `{"type":"stop","next_seq":已发送帧数}`；
收到 `completed` 才表示整任务结束。`cancel` 或断开立即清理会话。
错误仅回传安全代码，不透传云请求头、密钥或异常正文。

## 上游

北京区域默认端点 `wss://dashscope.aliyuncs.com/api-ws/v1/inference`，模型
`paraformer-realtime-v2`，16 kHz PCM，600 ms VAD 静音断句。
读取原服务的 `ALIYUN_API_KEY`，可显式设置 `ALIYUN_STREAMING_ASR_MODEL`；
此实现只支持上述已核实协议模型，不复用批式 `ALIYUN_ASR_MODEL`。
这不代表 MiMo 流式接口已接入。

官方依据：
- https://www.alibabacloud.com/help/en/model-studio/websocket-for-paraformer-real-time-service
- https://www.alibabacloud.com/help/en/model-studio/paraformer-client-events
- https://www.alibabacloud.com/help/en/model-studio/paraformer-server-events

## 启动与测试

在主仓用 Python 3.12 安装 `host/streaming_asr/requirements.txt` 后：

```powershell
python -m host.streaming_asr.serve --service-dir E:/openvela/语音模块/speech-service --host 127.0.0.1 --port 8000
python -m unittest host.streaming_asr.test_gateway -v
python -m host.streaming_asr.client sample.pcm
```

本机隔离依赖位于 `private/streaming-dependencies`，可用 PYTHONPATH 指向它。
用户原 `.venv` 指向不存在的 `C:/Users/Admin/anaconda3/python.exe`，未覆盖该环境。
局域网联调需显式监听电脑局域网地址（当前查询为 `10.3.1.125`），K7 不能用 localhost。
旧服务无应用鉴权，本通道沿用其局域网开发用途。

11 项隔离测试通过，包括录音期间返回 partial、连续句 final、结束协议、取消、断线、
乱序、坏帧、心跳、上游失败、错误任务ID、缺配置和格式拒绝。
测试中的上游是假服务，不能称真实云 ASR 或板端麦克风已通过。
当前 K7 固件尚无 WebSocket 采集发送适配；服务端完成不等于整机完成。
`session.py` 是此前子代理留下的单句核心草稿，当前网关不用它，避免首句 final
错误终止连续识别。

## 真实云复测

### 2026-09-14 本轮运行进展

蓝牙配网程序保持运行，没有重启或重新加载固件。实际执行 `k7cloud capture-stream-check` 返回 result=0、pcm_frames=150、nonzero_bytes=73071，network_sent=0；这是板端三秒实时分帧采集通过，尚未上传麦克风音频。采集后蓝牙 host fault=0、PROV registered=1，快照 App 未连接；已出现两次处理成功的历史扫描命令，不能据此宣称 Wi-Fi 已连接。

本轮再次经过真实云 TTS→流式 ASR：TTS HTTP200、1329ms；首个非空 partial 为578ms，final/completed 为4094ms。合成音频长3920ms，上传尚未结束就收到中间结果。新结果保存在 evidence/speech-stream-live-20260914 的时间戳子目录，不覆盖第一次验证。

新增 `host/streaming_asr/live_client.py`：接收实时 async PCM 帧源，ready 后开始取帧，同时接收 partial/final；最多8个未确认帧，支持取消、错误清理及源关闭。它无需先缓存完整录音，但当前只是主机侧接入模块，未替代板端缺失的 WebSocket 发送器。新增3项测试和原网关11项共14项通过。下一步仍需连接板端采集环形队列与网络发送、实现云 TTS PCM 下载播放。

现有 `/tts` 仍为整段合成后返回 PCM，不能称为流式 TTS。板端到云端完整语音对话尚未验收。

首次测试时本机网关 PID 为34304（历史进程号，不作为当前状态），健康返回ok。合成句“你好，联网成功。现在开始测试实时语音识别。”经真实TTS返回125440字节PCM（3.92秒），耗时1219ms；以20ms节奏上传流式ASR，640ms首个非空partial，4281ms返回完整final并completed。证据 `evidence/speech-stream-live-20260914/result.json`。这是一次合成句验证，不是板端麦克风、准确率统计或长期稳定验收。
