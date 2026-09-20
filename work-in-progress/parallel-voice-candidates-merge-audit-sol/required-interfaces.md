# 建议的最小接口契约

## 指定样本 ASR

建议在 C ABI 中表达，不把 C++ worker 类型泄漏给 k7sound：

```c
struct k7_asr_audio_request {
  const float *samples;       /* 调用期间只读且有效 */
  unsigned frames;            /* 1..48000 */
  unsigned sample_rate_hz;    /* 第一版必须为 16000 */
  uint64_t deadline_ms;       /* CLOCK_MONOTONIC 绝对时间 */
  int (*cancel_requested)(void *ctx); /* 非阻塞、线程安全 */
  void *cancel_ctx;
};

int k7_asr_audio_text(const struct k7_asr_audio_request *request,
                      char *utf8_text, size_t capacity);
```

返回负 errno：无样本 `-ENODATA`、帧数越界 `-EOVERFLOW`、忙 `-EBUSY`、取消 `-ECANCELED`、截止 `-ETIMEDOUT`、输出不足 `-ENOSPC`、模型/设备错误 `-EIO`。输出在任何失败时清空。函数返回后不得保留 samples、cancel callback 或输出指针。

## 持续 SAI voice session

建议以一个 owner session 同时仲裁录音与提示播放：

```c
int k7sound_voice_acquire(struct k7sound_voice **out);
int k7sound_voice_start_rx(struct k7sound_voice *voice);
int k7sound_voice_begin_utterance(struct k7sound_voice *voice,
                                  uint64_t *generation);
int k7sound_voice_end_utterance(struct k7sound_voice *voice,
                                uint64_t generation);
int k7sound_voice_poll_utterance(struct k7sound_voice *voice,
                                 uint64_t generation, unsigned *frames);
int k7sound_voice_copy_utterance(struct k7sound_voice *voice,
                                 uint64_t generation, float *out,
                                 unsigned capacity, unsigned *frames);
int k7sound_voice_release_utterance(struct k7sound_voice *voice,
                                    uint64_t generation);

int k7sound_voice_tx_begin(struct k7sound_voice *voice);
int k7sound_voice_tx_write(struct k7sound_voice *voice,
                           const int32_t *stereo, unsigned frames,
                           unsigned *consumed);
int k7sound_voice_tx_finish(struct k7sound_voice *voice);
int k7sound_voice_tx_abort(struct k7sound_voice *voice);
int k7sound_voice_release(struct k7sound_voice *voice);
```

generation 在 session 生命周期内严格递增且不复用。copy 只能读已完成且尚未 release 的不可变快照。TX 短写不停止 SAI/codec；finish/abort 才形成终态。若硬件不能同时 RX/TX，session 必须显式暂停 RX、清除回声污染窗口并在 TX quiescent 后恢复，不能让 VoiceLoop 猜测时序。

## Loop 与 worker

推荐让 concrete AsrPort 在 `begin(capture_id, grammar)` 返回 Accepted 前，把指定 generation 的样本复制到 worker 自有双槽。这样 capture 可以立即 release，worker 的 cancel 只管理自有内存。若选择零复制，AsrPort 必须增加可轮询的 drained 终态，Loop 在 drained 前不得 release capture。

密码 grammar 的 transcript 只允许存在于 worker 私有缓冲和 Controller 调用栈；发布后立即逐字节清零，不进入日志、错误文本或 result history。worker 结果必须同时带 ASR request ID 和 capture generation，Controller 只接受当前期望 generation。

## Prompt

不要把任意中文文本隐式匹配为资源 ID。建议增加 `PromptId` 与有界参数：网络序号、SSID 显示策略、密码长度、IPv4。`play()` 必须明确是同步播放完成，或返回唯一事务号并提供 poll/cancel；Loop 只有看到播放终态及 TX quiescent 才能开始下一次录音。
