# Xiaomi MiMo V2.5 ASR/TTS API 接续规范

状态：基于 2026-09-13 可访问的小米 MiMo 官方文档与 XiaomiMiMo 官方仓库整理；未调用任何付费 API，未读取、保存或打印真实密钥。

## 结论

VelaVision 联网后可以把录音交给 `mimo-v2.5-asr`，再把需要播报的文字交给 `mimo-v2.5-tts`。两个模型都使用 OpenAI 兼容的 Chat Completions 请求：

```text
POST {base_url}/chat/completions
Content-Type: application/json
api-key: ${MIMO_API_KEY}
```

也支持 `Authorization: Bearer ${MIMO_API_KEY}`。一个请求只能选择一种鉴权头。

用户提供的是 Token Plan 类型凭证时，必须使用 Token Plan 页面给出的专属 Base URL，不能与按量付费端点混用：

| 凭证 | Base URL | 用途 |
| --- | --- | --- |
| `sk-...` | `https://api.xiaomimimo.com/v1` | 按量付费 |
| `tp-...` | 以 Token Plan 页面展示为准；中国集群示例为 `https://token-plan-cn.xiaomimimo.com/v1` | Token Plan 套餐 |

官方还列出新加坡 `https://token-plan-sgp.xiaomimimo.com/v1` 和欧洲 `https://token-plan-ams.xiaomimimo.com/v1`。项目配置应把 Base URL 与凭证作为同一组原子配置，禁止自动把 `tp-...` 发往按量端点。

## ASR：板端录音转文字

模型名：`mimo-v2.5-asr`。

请求体最小形态：

```json
{
  "model": "mimo-v2.5-asr",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_audio",
          "input_audio": {
            "data": "data:audio/wav;base64,${BASE64_WAV}"
          }
        }
      ]
    }
  ],
  "asr_options": {
    "language": "zh"
  },
  "stream": false
}
```

输入限制：

- 每次只支持一条音频输入。
- 只支持 WAV 和 MP3。WAV MIME 为 `audio/wav`；MP3 MIME 为 `audio/mpeg` 或 `audio/mp3`。
- Base64 字符串上限 10 MB。该限制作用于编码后的字符串，因此原始音频应预留 Base64 约 4/3 的膨胀和 data URL 前缀空间。
- 可以传完整 data URL；也可只传纯 Base64，但纯 Base64 时 `input_audio.format` 必填，值为 `wav` 或 `mp3`。同时提供 MIME 与 `format` 时两者必须一致。
- `asr_options.language` 可为 `auto`、`zh`、`en`，默认 `auto`。语音配网固定中文时优先发 `zh`。

非流式结果文字位于：

```text
choices[0].message.content
```

用量对象可包含 `usage.seconds`、`prompt_tokens_details.audio_tokens`。`completion_tokens_details.reasoning_tokens` 对 ASR 始终为 0。

`stream: true` 返回 SSE，文字增量位于 `choices[0].delta.content`。这个“流式”是识别结果流式返回，不是麦克风 PCM 的双向实时上传：请求仍需先携带一整条 Base64 WAV/MP3。VelaVision 第一版应先录制一个有界片段、封装 WAV、完整上传，再消费文本流；不要把它设计成持续推 PCM 的 WebSocket。

对当前语音配网最直接的参数：16 kHz、单声道、16-bit PCM 的板载录音封成合法 WAV，再 Base64；官方只保证 WAV/MP3，并未在接口页规定 WAV 的采样率、声道数或位深，因此 16 kHz 单声道属于待真机 API 验证的实现选择。

## TTS：文字转板端播报

模型名：`mimo-v2.5-tts`。语音配网只需预置音色，不需要 `voicedesign` 或 `voiceclone`。

非流式请求：

```json
{
  "model": "mimo-v2.5-tts",
  "messages": [
    {
      "role": "user",
      "content": "用清楚、平稳、稍慢的普通话播报"
    },
    {
      "role": "assistant",
      "content": "扫描到三个无线网络。第一个，Lansee。第二个，REDMI K80。请说序号。"
    }
  ],
  "audio": {
    "format": "wav",
    "voice": "冰糖"
  },
  "stream": false
}
```

要合成的文字必须放在 `role: assistant` 的 `content`。前置 `role: user` 只作为语气、风格或上下文，不会被朗读；普通预置音色模式下可以省略它。

非流式音频是 Base64，位置为：

```text
choices[0].message.audio.data
```

解码后直接得到请求格式的字节。`message.audio.id` 是本次音频标识，`expires_at` 和 `transcript` 当前均为 `null`。

可选输出格式为 `wav`、`mp3`、`pcm`、`pcm16`。非流式默认 WAV。预置音色可用：`mimo_default`、`冰糖`、`茉莉`、`苏打`、`白桦`、`Mia`、`Chloe`、`Milo`、`Dean`。中国集群的 `mimo_default` 当前对应冰糖，其他集群当前对应 Mia；为避免区域变化，中文配网应显式指定一个中文 Voice ID。

### TTS 流式边界

低延迟播报使用：

```json
{
  "model": "mimo-v2.5-tts",
  "messages": [
    {"role": "assistant", "content": "正在连接无线网络，请稍候。"}
  ],
  "audio": {"format": "pcm16", "voice": "冰糖"},
  "stream": true
}
```

响应为 SSE。每个有音频的事件中读取：

```text
choices[0].delta.audio.data
```

对每个 `data` 独立做 Base64 解码，然后严格按接收顺序拼接字节。官方样例明确输出为 24 kHz、PCM16LE、单声道。播放器应按 24,000 Hz、单声道、有符号 16-bit little-endian 消费，不应再把流式结果当成带 WAV 头的文件。SSE 中允许出现没有 `choices` 或没有 `delta.audio` 的事件，解析器必须跳过。最终结束条件应同时兼容连接正常结束和 `finish_reason: stop`；官方 API 字段页没有承诺固定 chunk 大小，也没有保证每个 chunk 自成完整音频帧。

对板端实现，建议采用有界环形缓冲：网络任务连续解码 Base64 PCM，音频任务从缓冲区播放；缓存欠载时等待少量数据，不重复旧块。第一版也可以先用非流式 WAV 完成可验证闭环，之后再切流式 PCM16 降低首字延迟。

## 配网接入顺序

```text
离线提示/唤醒
  → 本地 ASR 识别“你好联网”
  → 板端真实扫描 Wi-Fi
  → TTS 播报网络序号和名称
  → 本地 ASR 识别序号
  → 密码采集与确认
  → 板端真实连接并取得 IP
  → DNS + HTTPS
  → 云端 mimo-v2.5-asr / mimo-v2.5-tts
```

第一次联网之前无法调用云端 TTS/ASR，所以“尚未联网，请说你好联网”及首次配网交互仍必须由板端离线提示音、离线 TTS 或本地 ASR 支撑。联网成功后，云端 ASR/TTS 可以替代对高精度离线识别和动态播报的要求；本地能力仍应保留为断网恢复入口。

## 错误处理与资源限制

- 官方账户级限速：`mimo-v2.5-asr` 为 100 RPM / 10K TPM；`mimo-v2.5-tts` 为 100 RPM / 10M TPM。所有同账户 API Key 调用相加。
- 高负载时可能延迟或返回 429；使用指数退避并设置连接/读取超时。配网提示不得无限自动重试，避免重复播报和额度消耗。
- Token Plan 的 ASR 按输入音频时长扣减，精确到秒后折算小时；当前换算为每音频小时 30M Credits。TTS 系列当前限时免费且不扣套餐 Credits，但“限时”意味着实现不能假定永久免费。
- 按量 ASR 当前官方价格为中国区 ¥0.5/小时、海外 $0.074/小时；TTS 当前限时免费。价格和促销会变化，运行时不应硬编码。
- 真实密钥不得写进仓库、镜像、串口日志或错误回包。板端接入时至少通过运行时安全配置注入；量产方案应使用受控网关或短期凭证，避免固件中长期保存账户级 Token Plan Key。

## 尚需一次无敏感信息的线上验证

官方规范仍未明确以下细节，接入测试时必须记录原始响应结构和音频元数据，但要脱敏：

1. Token Plan 页面为该账户实际分配的区域 Base URL；不能仅凭 `tp-` 前缀固定为中国区。
2. 16 kHz、单声道、16-bit WAV 是否被当前 ASR 集群接受，以及短语音端到端延迟。
3. TTS 流式 SSE 的实际终止事件、chunk 长度分布、chunk 是否始终偶数字节，以及网络中断后的重试语义。
4. 普通 `mimo-v2.5-tts` 单次目标文字的服务端硬上限。官方 Skill 只建议超过约 2500 字再考虑分段，这不是接口硬限制。
5. Token Plan 语音模型是否在该用户套餐和所选区域已启用。模型列表文档说明套餐支持，但最终以控制台和实际非计费/最小测试结果为准。

## 官方证据

- ASR API Reference：https://mimo.mi.com/docs/en-US/api/audio/Speech-Recognition
- ASR 使用指南：https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition
- TTS API Reference：https://mimo.mi.com/docs/en-US/api/audio/tts
- TTS 使用指南：https://mimo.mi.com/docs/usage-guide/speech-synthesis-v2.5
- Token Plan 与按量端点：https://mimo.mi.com/docs/en-US/tokenplan/integration/tools-overview
- Token Plan 区域端点：https://mimo.mi.com/docs/zh-CN/tokenplan/Token%20Plan/quick-access
- API Key 鉴权与凭证不可混用：https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration
- 限速：https://mimo.mi.com/docs/en-US/api/guidance/rate-limit
- 按量价格：https://mimo.mi.com/docs/en-US/price/pay-as-you-go
- Token Plan 计量：https://mimo.mi.com/docs/en-US/quick-start/faq/token-plan
- 官方 TTS 示例仓库：https://github.com/XiaomiMiMo/MiMo-Skills

