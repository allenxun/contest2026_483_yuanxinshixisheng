# SAI TX / codec 持续流 sink 候选

## 范围与结果

本目录只包含主机可验证候选，没有修改 `app/k7sound`、SDK、设备、虚拟机、串口或中央日志。它把一次完整的 SAI 播放事务拆成持续流生命周期：`ss_begin()` 只配置并占有一次硬件，`ss_write()` 可重复短写，`ss_drain()` 等待最后数据离开 FIFO，`ss_end()` 正常排空并清理，`ss_abort()` 立即执行同一套幂等清理。

每次提示资源的 256 帧块只写入同一个已启动的 TX 流；不会调用一次 `pio_play_buffer()` 就停一次硬件。候选使用固定的 16 kHz、双声道 signed-32 slot，与 `parallel-voice-prompt-adapter-sol` 的输出契约一致。

## 生命周期与错误语义

`ss_begin()` 通过共享 owner 门与录音互斥。成功后，`prepare_tx` 必须建立 raw32/16k stereo 配置、运行 CLK/FS、保持 TX 停止和 FIFO 空、调用 `kd_arm(..., false, true, ...)`，并保持功放物理低电平。首批 16 个 word（8 帧）写入后才启动 TX，再调用 `kd_enable_amp()`。不足 8 帧的短提示在 `drain/end` 时用实际已有 word 启动。

`ss_write()` 返回正的已接收帧数，FIFO 当前空间不足时允许短写。取消、超时、寄存器错误或启动错误不会伪装成短写成功，而是立即执行完整清理并返回负值。正常 `end` 和异常 `abort` 的清理顺序固定为：功放快速拉低、停止并清 TX、codec mute/power-down、平台/I2C 恢复、释放共享 owner。每一步都会尝试；任一步失败返回 `SS_CLEANUP`，本地 `held` 置位，并通过 `owner_release(ctx, held=1)` 毒化共享门，使后续录音或播放都不能误获硬件。

`prepare_tx` 可能在失败前只完成部分配置，所以 `begin` 在调用它之前就武装全部清理。正式回调需要持有根级阶段记录，使 `stop_tx/codec_stop/platform_cleanup` 在部分准备下也安全且幂等。

## 正式接入点

候选应在 `app/k7sound` 内新增正式文件后接到以下现有实现，不能直接改成逐块调用 `pio_play_buffer()`：

| 候选回调 | `app/k7sound` 正式接入 |
| --- | --- |
| `owner_try_acquire/release(held)` | 与 capture 共用 `owner` 及 `data_held/reset_fault`；trylock 忙时返回 busy，held 时毒化所有音频入口 |
| `prepare_tx` | `prepare_i2c`、`amp_prepare`、`sap_prepare`、`kd_bind/kd_prepare`，再提取 `pio.c::run` 的 TX profile/CLK-FS 配置并调用 `kd_arm` |
| `fifo_words` | 先读 `SAI_INTSR` 拒绝 TX underrun，再读 `SAI_TXFIFOLR` 并调用现有 `pio_fifo_count()`；总数必须 `<=16` |
| `write_word` | 有序写 `SAI_TXDR`；仅在可用空间至少 2 word 时写一帧 |
| `start_tx` | 只置 `SAI_XFER_TXS` 并读回，不重配 CLK/FS |
| `enable_amp/amp_off_fast` | 现有 `kd_enable_amp()` 与 `<100us` 的 GPIO `amp_off` 路径 |
| `stop_tx` | 从 `pio.c::stop` 提取共享 helper：清 TXS、等 TX idle、清 FIFO、最后停 CLK/FS |
| `codec_stop` | 现有 `kd_stop()`，必须排在 TX 已停之后 |
| `platform_cleanup` | 现有 `sap_cleanup`、clock restore、I2C restore，使用根级阶段记录 |

录音和播放必须使用同一个 owner，不能只各自维护布尔值。播放期间 capture 返回 busy；capture 期间固定提示播放返回 busy。清理失败后的 poisoned/held 状态只能由现有显式恢复流程处理，不能自动重试或切换方向。

接 `parallel-voice-prompt-adapter-sol::AudioSinkPort` 时，固定格式允许 `acquire()` 调用 `ss_begin(16000, 2, deadline)`，随后的 `begin()` 只核对同一格式；`writeFrames()` 调用 `ss_write()`，`finish()` 调用 `ss_end()`（内部 drain），`abort()` 调用 `ss_abort()`，`release()` 只检查 wrapper 已回到 idle。这样 adapter 原有的 busy、取消和幂等 abort 契约保持不变。

## 主机假 PIO 测试

在本目录执行：

```powershell
gcc -std=c11 -Wall -Wextra -Werror -pedantic -O0 -c sai_stream_sink.c -o sai_stream_sink_O0.o
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -O0 test_sai_stream_sink.cpp sai_stream_sink_O0.o -o sai_stream_sink_test_O0.exe
.\sai_stream_sink_test_O0.exe
gcc -std=c11 -Wall -Wextra -Werror -pedantic -O2 -c sai_stream_sink.c -o sai_stream_sink_O2.o
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -O2 test_sai_stream_sink.cpp sai_stream_sink_O2.o -o sai_stream_sink_test_O2.exe
.\sai_stream_sink_test_O2.exe
```

O0/O2 都应输出：

```text
PASS 10/10: continuous short-write, short drain, capture busy, cancel cleanup, mid-write cancel, start cleanup, amp cleanup, drain timeout, cleanup hold, prepare cleanup
```

覆盖同一硬件会话内多次短写且只启停一次、不足预填充的 drain、录音 owner 忙、开始前和写入中取消、TX 启动错误、功放启动错误、drain 超时、三层清理同时失败仍全部尝试并锁存 held、部分 prepare 失败后的全路径清理。原始命令结果及工具链限制保存在 `test-results.txt`。

## 真机未完成项

- 尚未迁入 `app/k7sound`，未做 ARM64 SDK 编译、ELF/反汇编核对或正式固件构建。
- 尚未真机验证 FIFO 总数、短写节奏、underrun 标志、drain 尾音、取消延迟、功放启停爆音和长提示连续性。
- 尚未把 VoiceLink 固定提示资源通过 adapter 接入此 sink，未做板载可懂度或音量验收。
- 尚未实测与 MIC ASR capture 的并发 busy、方向切换、取消竞态和 held/显式恢复流程。
- 假 PIO 只能验证调用顺序和状态机，不能代替 RK3576 SAI、codec、I2C、GPIO 或声学结果。

文件哈希见 `verification.json`；生成的 `.o/.exe` 是可再生成主机产物，不纳入源码哈希。
