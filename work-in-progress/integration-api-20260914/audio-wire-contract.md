# VelaVision 音频线格式与流式缓冲契约

状态：2026-09-14 接口审计稿。本文只定义设备、业务后端与 MiMo 之间的音频边界；未写入凭证，未发起网络请求，未操作硬件。

## 给业务后端的明确答复

| 方向 | 交付格式 | 容器 | 时长单位 | 备注 |
| --- | --- | --- | --- | --- |
| K7 → ASR 上传 | 16,000 Hz、单声道、有符号 16-bit little-endian PCM | **WAV** | 1 frame = 1 个单声道样本 = 2 字节 | 不上传裸 PCM；第一版整段录制、封装后再发 HTTP |
| MiMo 流式 TTS → K7 | 24,000 Hz、单声道、有符号 16-bit little-endian PCM | **无容器的 raw PCM** | 1 frame = 1 个单声道样本 = 2 字节 | 每个 SSE `audio.data` Base64 解码后按顺序拼接，不按 WAV 解析 |
| K7 当前直接播放入口 | 16,000 Hz、单声道 S16 输入 | 无容器 | 最多 30 秒 | `k7sound_speak_mono16` 固定按 16 kHz 消费 |

因此，MiMo 的 24 kHz 流进入当前固件前必须二选一：为 codec/SAI 增加并真机验收 24 kHz 播放模式，或先做 **24 kHz → 16 kHz** 的有界重采样。当前代码不能把 24 kHz 字节直接交给 16 kHz 播放入口，否则音高和时长都会错误。

“K7 采集 16 kHz mono S16LE”是云端交付格式。设备内部并非直接保存这种字节流：底层 SAI 使用固定 16 kHz 双 32-bit slot，`k7sound_copy_mono()` 从已完成快照取左槽并归一化为 float；云端适配层须饱和量化为 S16LE，再写 WAV 头。参见 [`codec_duplex.h`](../../app/k7sound/codec_duplex.h)、[`k7sound_main.c`](../../app/k7sound/k7sound_main.c) 和 [`asr_runtime.h`](../../app/voicelink/include/voicelink/asr_runtime.h)。

## ASR 的 WAV 上传边界

WAV 至少必须包含合法 `RIFF`、总长度、`WAVE`、PCM `fmt ` 和 `data` 块。固定参数为：

```text
audio_format    = 1          # integer PCM
channels        = 1
sample_rate     = 16000
bits_per_sample = 16
block_align     = 2
byte_rate       = 32000
data_bytes      = frames * 2
```

所有 WAV 整数字段和 PCM 样本均为 little-endian。float 转 S16 时须处理非有限值并做饱和；建议采用 `round(clamp(x, -1, 1) * 32767)`，并将 `x <= -1` 明确映射为 `-32768`。不得直接把 float 的内存字节当作 PCM 上传。

MiMo ASR 的直接调用仍是 `application/json`：完整 WAV 被 Base64 后放入 `data:audio/wav;base64,...`。这里“HTTP 上传 WAV”指音频对象必须是 WAV 容器，不代表把裸 PCM 作为请求 body。若业务后端另设二进制上传端点，可以用 `Content-Type: audio/wav` 接收同一 WAV 字节，但后端转发 MiMo 时仍须按官方 JSON 结构编码。MiMo 的 `stream:true` 只流式返回文字，不能持续上传麦克风 PCM。现有规范与 codec 分别见 [`mimo-api-spec-20260913`](../mimo-api-spec-20260913/README.md) 和 [`mimo_v25_profile.c`](../../app/k7agent/cloud/src/mimo_v25_profile.c)。

第一版建议每段最多 5 秒：160,000 字节 PCM，加 44 字节常规 WAV 头；Base64 约 213,392 字节，明显低于已审计的 10 MB Base64 上限。封装器仍需用 64-bit 中间值检查乘法和加法溢出，再写 32-bit RIFF 字段。

## 20 ms PCM 分块

业务后端和板端音频任务之间统一用 20 ms 逻辑块：

| 采样率 | 每块 frames | 每块 PCM 字节 | 每秒块数 |
| --- | ---: | ---: | ---: |
| 16 kHz | 320 | 640 | 50 |
| 24 kHz | 480 | 960 | 50 |

MiMo 不保证 SSE 音频片段为固定大小，也不保证 Base64 解码结果落在 16-bit 样本边界。接收器必须保留至多 1 个奇数字节，把连续解码字节重新切成 960-byte 的 24 kHz 块；最终块可以短于 960 字节，但必须为偶数字节。缺半个样本、非法 Base64 或终止后残留奇数字节都应使该流失败，不能补猜一个字节。

建议的传输无关逻辑记录如下：

```text
AudioChunk {
  stream_id:       uint64       # 每次合成唯一，重连不得复用
  seq:             uint32       # 从 0 连续递增
  timestamp_us:    uint64       # 音频时间轴，不是网络到达时间
  sample_rate_hz:  uint32       # MiMo 流固定 24000
  channels:        uint8        # 固定 1
  sample_format:   "s16le"
  payload:         bytes        # 通常 960 B；末块可短，始终为偶数
  eof:             bool
}
```

约束：

- `timestamp_us = 已提交的累计 frames × 1,000,000 / sample_rate_hz`。24 kHz 完整块依次为 0、20,000、40,000 微秒。
- 同一 `stream_id` 的 `seq` 必须严格连续；重复、倒退、跳号或格式字段变化立即取消该流。
- `eof=true` 只出现一次。它可以携带最后一个偶数字节短块；若音频恰好整块结束，则发送零 payload 的下一序号 EOF。EOF 后的任何数据都是协议错误。
- 正常 SSE 连接结束或 `finish_reason: stop` 只表示上游结束；适配器完成 Base64 尾部校验、偶数字节校验并发出 EOF 后，板端才视为完整音频。
- 若用 SSE 承载自有协议，建议 `event: audio`，`data` JSON 中只放上述元数据和 `pcm_b64`。MiMo 原始 SSE 没有 `seq/timestamp/eof`，这些字段由可信适配层按解码后的累计样本生成。

## 背压和缓冲状态机

采用单生产者/单消费者的有界环形缓冲。初始建议 8 个 20 ms 槽（160 ms），开始播放水位 3 槽（60 ms），高水位 6 槽，低水位 3 槽。槽必须拥有 PCM 数据，网络解析回调返回后不能保留其临时指针。

```text
FILLING --达到 3 槽--> PLAYING --收到 EOF 且排空--> DRAINED
   |                      |              |
   +--协议/溢出/取消------+--------------+--> ABORTED
```

- 达到高水位后暂停从 TLS socket 读取，让 TCP 接收窗口形成背压；消费到低水位再恢复。不要让生产者覆盖未播放槽。
- 若上游接口无法安全暂停且下一块放不下，终止整条流并报告 overflow。禁止丢块后继续，也禁止重放旧块掩盖溢出。
- 播放前先达到启动水位。播放中的短暂欠载可以等待至一个 20 ms 周期；连续两个周期仍无新块则中止本流。禁止重复上一块；是否插入静音必须成为可观测策略，不能悄悄改变音频时间轴。
- `cancel`、协议错误、HTTP/TLS 错误或播放错误都必须停止生产、唤醒双方、清空环形缓冲和奇数字节尾部，并让 codec/SAI 完成 quiesce。旧 `stream_id` 的迟到数据必须丢弃。
- 网络任务不得等待音频任务时持有全局 TLS、模型或音频 owner 锁；音频任务也不得在等待网络时持有 codec owner。环形缓冲锁只保护索引和槽状态。
- 记录可包含 `stream_id` 的非敏感内部编号、seq、水位、错误码、欠载/溢出计数；不得记录 PCM、Base64、提示文本、转写文本、密码或鉴权内容。

160 ms 是起始参数，不是验收常数。真机应记录网络抖动和调度延迟后调整，但必须保持固定内存上限。24 kHz 下 8 个 payload 槽仅占 7,680 字节，另加少量元数据。

## 24 kHz 播放或重采样

当前 [`k7sound_api.h`](../../app/k7sound/k7sound_api.h) 将 mono S16 播放明确限定为 16 kHz，codec 准备接口也固定 `Fs16000/MCLK4096000`。现有 [`speech_pcm.hpp`](../../app/voicelink/include/voicelink/speech_pcm.hpp) 只接受 8 kHz 或 16 kHz，不能处理 24 kHz。

建议先实现有界流式 24→16 kHz 重采样，以避免改动已验证的 codec 时钟。比例为 2/3：每个 20 ms 输入块 480 frames，输出 320 frames，输出仍为 640 字节。实现应使用带低通滤波的有状态有理重采样器，并跨 chunk 保存滤波历史和 3 相位状态；不能简单“每三个样本丢一个”，否则会混叠。EOF 时按明确的滤波尾部策略 flush，取消时清空历史。

如果改为原生 24 kHz 播放，则必须同步修改并验收 codec PLL/MCLK/BCLK、SAI frame 时钟、PIO 超时公式、FIFO 供给速率及 `k7sound_speak_mono16` 的接口参数，不能只改函数参数或延时常数。

## 与现有 VoiceLink 接口的关系

- [`k7_asr_audio_request`](../../app/voicelink/include/voicelink/asr_runtime.h) 已携带 float 样本、frames 和 `sample_rate_hz`，正式运行时只接受 16 kHz，最多 48,000 frames（3 秒）。它适合本地 ASR，不是 WAV/HTTP 上传接口。
- [`k7sound_copy_mono`](../../app/k7sound/k7sound_main.c) 只复制完成且可用的最多 48,000-frame 快照，并用 try-lock 返回 busy；云端上传任务必须先取得自己的快照，不能在编码或网络阶段重读全局最近录音。
- [`k7_tts_synthesize`](../../app/voicelink/include/voicelink/tts_runtime.h) 是板端离线 Sherpa TTS 的整段 float→S16 输出接口，返回实际采样率；它不是 MiMo SSE 接收器。
- [`NativeSpeechOutput`](../../app/voicelink/src/native_speech_output.hpp) 会把整段离线 TTS 放入 vector，并只接受 8/16 kHz 转为 16 kHz stereo S32。云端流式 TTS 应使用独立的有界 ring + resampler + mono16 播放流接口，不能复用这个整段 vector 路径。
- [`TtsPort`](../../app/voicelink/include/voicelink/ports.hpp) 当前只有同步 `speak/stop`，没有 chunk、drained 或 transaction ID。正式流式接入前需增加独立事务接口，或在 concrete port 内完全封装 producer、ring、播放和取消，并让 `speak()` 只在真正 drained/quiescent 后成功返回。
- [`VoiceLoop`](../../app/voicelink/include/voicelink/voice_loop.hpp) 已用不可复用 request ID 管理 capture/ASR，但未定义云端音频 chunk。云端 `stream_id` 不得复用 capture ID 或 ASR request ID；跨层关联应显式保存三者映射。

## 尚未验证

当前正式 `app/` 已有非流式 MiMo JSON/Base64/WAV codec 和有界 HTTPS 基础，但没有 MiMo SSE 音频 parser、20 ms ring、24→16 kHz 重采样器或 24 kHz 播放入口。本文的 chunk 水位、欠载阈值和重采样方案尚未做主机测试、ARM64 构建、真实 API 调用或板端播放验收。MiMo 是否接受当前 16 kHz mono S16LE WAV 也仍需无敏感日志的真实 API 验证。
