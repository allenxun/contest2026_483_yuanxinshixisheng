# Spoken TTS + k7cloud combined profile audit

日期：2026-09-13。范围仅为静态配置、构建契约与内存布局审计；没有修改正式 defconfig/SDK，没有构建大镜像、联网、使用密钥或操作板子。

## 结论

现有 `velavision_spoken_tts_local` 与 `velavision_cloud_probe_local` 的主体配置相同，配置差异只有 18 个符号。可以从 spoken-TTS 配置派生 combined profile，保留 ROMFS 和 512 MiB 语音模型池，再叠加 DNS、mbedTLS 与 `k7cloud` 的 16 个云侧符号。候选见 `combined-linkonly.fragment`。

这个候选目前只允许“编译和链接”。它不能用于真实 HTTPS：两个源配置都关闭 `CLOCK_TIMEKEEPING`、`DEV_URANDOM` 和 `RTC`，代码还要求调用方提供 CA、`security_ready`、单调时钟、SNI 和零证书校验错误。不能通过简单开启 `/dev/urandom` 或绕过 `security_ready` 来宣布 TLS 可用。

## 已识别的合并边界

- VoiceLink 的原生 ASR/TTS 构建必须继续传入四个 `K7VOICE_NATIVE_*` 开关、经过 SHA-256 固定的 `speech-runtime-gated.arm64.o` 和生成的 TTS 资产目录。仅修改 defconfig 不会把离线运行库链接进去。
- `FS_ROMFS=y` 与 `EXAMPLES_K7VOICE_STAGED_ASSETS=y` 必须保留。当前正式 defconfig 中 `FS_ROMFS` 先出现一次 `not set`、末尾再置 `y`，最终值有效但会产生重复设置警告；候选检查器按最后一次赋值解析并明确记录这一点。
- 云侧 `k7cloud` 依赖 `EXAMPLES_K7RADIO_IP`、TCP、socket options、DNS client 和 mbedTLS；spoken 配置已满足网络与无线前置条件，fragment 只补云侧差异。
- 下半段 `0x60000000..0x80000000` 是 512 MiB ASR/TTS 共享 allocator。上半段 `0x80000000..0xa0000000` 保存 encoder、decoder 与 TTS ROMFS；三个已审计区域互不重叠。
- 当前 OTG 单包距离 `0x07000000` 下载上限仅剩 915,584 字节。combined 固件增加 DNS/mbedTLS 后很可能触碰这个上限，所以正式构建必须先量 `nuttx.bin`，超限时重新审计包布局，不能直接放宽检查。
- `k7voice` 和 `k7cloud` 使用独立命令入口及独立栈；当前没有已知入口符号重名。最终 ELF 仍须对 `combined-build-contract.json` 中 13 个强符号逐一检查“恰好一次”。
- mbedTLS 的输入/输出 record buffer 各配置为 16 KiB。它使用系统堆，而语音 ORT 使用专用模型池；内存地址不冲突，但云请求、Base64/JSON、证书链和音频缓冲仍需在 combined 镜像上做系统堆峰值门禁。

## 推荐实施顺序

1. 先完成当前 gated 离线 TTS→ASR→TTS 真机验收，冻结实际通过的运行库和模型布局。
2. 用 spoken defconfig 为基线应用 `combined-linkonly.fragment`，保留 `combined-build-contract.json` 的 CMake hash 门禁，在全新独立构建目录编译。
3. 检查最终 `.config`、13 个强符号唯一性、异常表、`nuttx.bin` 增量和 RAM-only 包上限。此时仍不运行网络请求。
4. 独立完成 DHCP DNS、租约 generation、硬件熵、可信时间和最小 CA，再打开真实 DNS/TLS 诊断。所有失败路径必须保持 fail-closed。

运行静态检查：

```text
python work-in-progress/spoken-cloud-profile-audit-20260913/verify_combined_profile.py
```

结果写入 `verification.json`。`status=pass` 只表示候选与当前仓库证据一致，不表示 combined 固件已构建、上板或能访问 MiMo。
