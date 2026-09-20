# 固定语音提示播放适配候选

## 范围

本目录是主机可验证的有界候选，不修改 `app/k7sound`、`app/voicelink` 或 SDK，也未在板端播放。它只负责读取固定提示资源、校验 WAV、分块转换并交给独占音频 sink；不包含 ASR 文本运行时、VoiceLink Controller 编排、动态 TTS 或设备操作。

`voice_prompt_adapter.hpp/.cpp` 定义三个端口：

- `ResourcePort`：按提示 ID 打开只读资源，允许短读，明确区分资源缺失。
- `AudioSinkPort`：独占获取、开始、允许短写、正常结束、异常中止和释放。`abort()` 必须幂等。
- `CancelPort`：在读资源和每次 sink 写入前轮询取消。

输入限定为 RIFF/WAVE、PCM16、单声道、16 kHz。适配器每次读 256 帧（512 字节、16 ms），扩展成左右相同的 signed 32-bit 槽（2048 字节工作块），不增益、不保留资源指针。错误或取消只要已经取得 sink，都会执行 `abort()` 和 `release()`；清理失败会覆盖为 `cleanup_error`，避免把硬件安全状态伪报为已恢复。

## 与现有板端代码的接口边界

`app/k7sound/pio.h` 的 `pio_play_buffer()` 已证明有严格的 amp-off、stream stop 和 held 状态语义，可作为 sink 清理契约的依据。但它当前是一次完整播放事务，最大 48000 帧，并不是可连续调用的短写流。正式集成需要在 `app/k7sound` 内新增一个独占、持续持有 SAI/codec 的流式后端，或预先按不超过 48000 帧的段落提供整段缓冲并接受段间启停。直接把本候选的每个 256 帧块逐次传给 `pio_play_buffer()` 会每 16 ms 启停硬件，存在间隙和爆音风险，不建议这样接。

`app/voicelink` 的 `TtsPort::speak(text)` 仍接受任意文本。正式接入需要由 Controller 上层明确选择“固定 ID”或“动态文本”，不能用模糊文本匹配偷偷替换。此候选不修改该接口。

## 配网提示覆盖和缺口

现有 `provisioning-fixed-prompts-20260911/pcm16k` 共 22 个 WAV，合计 2,456,108 字节（约 2.342 MiB），去除每文件 44 字节头后 PCM 合计 2,455,140 字节。最长 `p004` 为 108393 帧、216830 字节，约 6.775 秒。资源均为 16 kHz 单声道 PCM16，但由 8 kHz TTS 重采样而来，没有新增高频带宽；全部未在板端播放、未做人工可懂度验收。

| 流程用途 | 固定资源 | 状态 |
| --- | --- | --- |
| 重听、空扫描、无效编号、当前字符重听 | p000-p003 | 与 Controller 固定文字一致 |
| 密码最大长度、清空、重输、大小写、长度不足 | p004-p009 | 与 Controller 固定文字一致 |
| 收到凭据、连接中、密码错、超时、忙、不支持、找不到、通用失败 | p010-p017 | 与 Controller 固定文字一致 |
| 扫描开始 | p018 | 资源已有，当前 Controller 未发出该提示 |
| 连接成功 | p019 | 只有通用提示；Controller 当前还会播 SSID 和 IP |
| 请求说网络名称 | p020 | 资源已有，当前 Controller 以动态候选列表请求选择编号 |
| 取消 | p021 | 与 Controller 固定文字一致 |

当前资源缺口如下：

- 唤醒问候：`你好，我是 openvela，开始为你配置网络`。
- 扫描终态：扫描失败、扫描接口无事务编号、扫描服务忙、扫描不支持、扫描超时。
- 网络选择：带 SSID 的候选列表、已选择开放网络、已选择加密网络。它们含动态 SSID，固定资源只能拆成前后片段或改成交互编号语句。
- 密码输入反馈：第 N 个字符、当前长度 N、密码共 N 位及显式确认、尚未提交提示。N 是动态值；可准备 0-63 数字片段，或调整交互避免逐字符播报。
- 连接内部错误：连接失败并停止、连接接口无事务编号。
- 成功详情：Controller 当前包含 SSID 和 IPv4；p019 只能作为不播详情的通用替代。

## 大小与分块建议

- 存储侧可去掉 WAV 头，采用一个只读 PCM blob 加 `{id, offset, frames, sha256}` 索引，当前规模约 2.342 MiB。若仍保留 WAV，本适配器支持短读和非 `fmt`/`data` 辅助块。
- I/O 工作块建议保持 256 帧：资源读 512 字节，转换后 sink 数据 2048 字节，取消检查间隔 16 ms，常驻工作内存约 2.5 KiB。
- 若临时复用 `pio_play_buffer()`，每段不得超过 48000 帧（3 秒、原 PCM 96000 字节、展开后 384000 字节）。22 条中超过 48000 帧的提示必须分段，最长 p004 需要 3 段。该方案会有段间启停，正式体验应优先实现持续流 sink。
- 资源安装时保留现有 pcm16k manifest 的逐文件 SHA256，并在板端读取前或打包阶段核对；本候选没有内置 SHA256，避免在播放实时路径重复做大块校验。

## 主机复现

在本目录执行：

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -O0 voice_prompt_adapter.cpp test_voice_prompt_adapter.cpp -o voice_prompt_adapter_test_O0.exe
.\voice_prompt_adapter_test_O0.exe
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -O2 voice_prompt_adapter.cpp test_voice_prompt_adapter.cpp -o voice_prompt_adapter_test_O2.exe
.\voice_prompt_adapter_test_O2.exe
```

预期两次均输出：

```text
PASS 6/6: short I/O, cancel, busy, write cleanup, cleanup failure, missing resource
```

测试覆盖：资源每次最多短读 3 字节、sink 每次最多短写 7 帧、播放中取消、sink 忙、写错误后的清理、清理自身失败可见、提示资源缺失。首次编译夹具失败和修正后的原始结果保存在 `test-results.txt`。

## 资产来源

- 原提示清单：`../provisioning-fixed-prompts-20260911/manifest.json`
- 16 kHz 清单和逐文件哈希：`../provisioning-fixed-prompts-20260911/pcm16k/manifest.json`
- 原 8 kHz 波形检查：`../provisioning-fixed-prompts-20260911/audio-format-check.json`

本目录最终文件哈希见 `verification.json`。生成的 `.exe` 是可再生成主机产物，不纳入源码哈希清单。
