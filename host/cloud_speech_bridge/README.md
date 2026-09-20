# MiMo 主机云语音桥接候选

该目录提供可注入到虚拟机前端或联调服务的同步 Python 接口，不修改板端代码，也不保存 API Key。

## 接口

- `MiMoSpeechBridge.transcribe(audio, audio_format="pcm16le")`：接收 **16 kHz、单声道、PCM16LE** 裸数据，或指定 `audio_format="wav"` 接收同格式 WAV；请求 `mimo-v2.5-asr`，返回文字。
- `MiMoSpeechBridge.synthesize(text)`：请求 `mimo-v2.5-tts` 的 WAV，校验单声道 PCM16 容器，将实际采样率转换为 K7 可播放的 **16 kHz、单声道、PCM16LE**。`TtsResult.as_wav()` 可供主机试听。
- 默认中文男声为 `白桦`，调用时可显式传 `voice=` 覆盖。

密钥和 Token Plan 区域地址只从运行环境注入：

```powershell
$env:MIMO_API_KEY = "运行时密钥"
$env:MIMO_BASE_URL = "https://控制台显示的区域地址/v1"
```

代码不会读取配置文件、命令行密钥或打印请求正文。生产部署仍建议由受控后端持有账户级密钥，K7 使用设备短期凭证调用后端，避免把 Token Plan Key 放入固件或前端。

## 错误映射

`BridgeError.code` 是稳定字符串：`invalid_audio`、`invalid_config`、`auth`、`rate_limited`、`timeout`、`network`、`upstream`、`bad_response`、`output_limit`。`retryable` 仅对限流、超时、网络和 5xx 为真。错误不带上游响应体，避免回显音频、文字或密钥。

当前候选使用非流式 Chat Completions：ASR 上传完整 WAV；TTS 收完整 WAV 后重采样。重采样是有界的线性插值，已保证格式和时长，尚未作为最终高音质重采样器验收。正式低延迟版本应按 `work-in-progress/integration-api-20260914/audio-wire-contract.md` 使用带低通滤波的 24→16 kHz 流式重采样器和有界环形缓冲。

## 离线验证

```powershell
python -m unittest discover -s host/cloud_speech_bridge -p "test_*.py" -v
```

测试使用内存 Fake Transport，不联网、不调用付费接口。覆盖环境变量注入、PCM→WAV、24→16 kHz、请求结构、错误映射、响应上限、坏 JSON/WAV/Base64 和密钥不进入异常文本。

## 本机 HTTP 接口

配置环境变量后启动：

```powershell
python host/cloud_speech_bridge/server.py --port 18086
```

服务固定绑定 `127.0.0.1`，命令行没有公网监听参数，也不返回任何 CORS 允许头。它适合虚拟机桌面前端或本机联调进程调用；需要跨主机时应由带设备鉴权、TLS 和访问控制的正式业务后端提供接口，不能直接暴露此开发服务。

| 方法 | 路径 | 请求 | 成功响应 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无 | JSON `status/ready/asr/tts/output`；`ready/asr/tts` 均为布尔值 |
| `POST` | `/v1/asr` | `audio/wav`；或 `application/octet-stream` / `audio/pcm` 的 16 kHz mono PCM16LE | JSON `{"text":"..."}` |
| `POST` | `/v1/tts` | JSON `{"text":"联网成功","voice":"白桦","format":"wav","sample_rate":16000,"channels":1}`；voice 和固定格式字段可省略 | `audio/wav`，16 kHz、单声道、PCM16 |

默认请求体上限为 2,000,000 字节，可用 `--max-request-bytes` 调低或调高。请求必须携带 `Content-Length`，不接受 chunked body。所有失败统一返回 `{"error":{"code","message","retryable"}}`；服务关闭默认访问日志，也不会把请求正文、转写、播报文字、上游响应或密钥写入错误信息。
