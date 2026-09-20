# 整机语音控制基础

2026-09-15 增量：command_session.py 已把最终识别事件连接到 DeviceController，旧录音会话结果拒绝，启动任务异步执行，后续停止事件可继续处理。普通聊天返回 chat 给上层，未伪造后端回答。serial_owner.py 提供单读者和短写锁，取消写入时仍等待底层线程完成，避免停止命令与未写完的启动命令字节交错；char_interval=.004 可沿用现有 NSH 字符节奏。串口必须配置有限读写超时。仍未绑定生产硬件，也未替换运行中的语音桥。

当前是可测试的控制基础，未接入运行中的语音桥、云台、相机或真实报告端点。不要直接把ASR输出拼接成NSH命令。

- voice_intents.py：只路由完整final，按会话/句子ID去重，固定命令精确匹配；普通文本交聊天，否定句不触发动作。
- voice_prompts.zh-CN.json：各真实阶段的语音提示。
- report_speech.py：ReportNarrator(synthesize, play, stop_audio)。run(events, request_id, report_id)消费规范化事件；stop()取消本轮并调用真实播放器停止。synthesize返回16k单声道S16LE PCM，play必须等实际播放完成，stop_audio须能停止实际播放器。当前开发桥没有硬件中途停播合同，所以不能用空回调宣称已集成。

事件是对接层内部拟定格式，尚非18085实际合同：start/text_delta/done/error，携带requestId/reportId/seq，seq从0递增，text_delta.text为新增文字。网络适配器待后端确认；不能猜接口名或把已有JSON报告当SSE。仅接收本次指定报告。

两个容量为2的队列分别连接收文、合成、播放，最多并行一段合成和一段播放；句子最长64字符，报告最长100000字符，每段PCM最大960000字节。报告流整体300秒超时。无句末时按长度分割，目前没有首句闲置计时截断；真正音频边下载边播放仍待板端接口改造。

停止、失败会取消所有子任务并使generation失效，晚到合成不能送播放器。正在播放的取消依赖实际播放器适配器，不保证当前板子已经具备即时停播。

验证：python -m unittest host.whole_device.test_report_speech host.whole_device.test_voice_intents
共8项：首句早于全文完成、乱序/错报告拒绝、迟到合成取消、停止后新会话、断流、分句界限、意图/重复/否定。

controller.py已实现语音任务状态：start(intent)调度启动/采集，stop()优先取消任务并停止音频及跟踪。ports须提供announce、start_tracking、stop_tracking、stop_audio、capture_views；启动/停止返回True必须来自真实检查，不能虚构。capture_views按视角和阶段提供真实事件。控制器不上传或假称聊天可用，后端延期不阻塞此软件实现。当前仍缺生产级串口代理和真机ports，不能启动此类就宣称可以语音运动。7项控制器测试通过，总36项语音相关回归通过。

2026-09-15 板端候选：voicecam 1..1800 延用 v1.3-xcenter 已校准范围与复位前提，单次UVC启动后保持采集；默认hold，voicemode track/photo按worker应用后输出结果，halt只停未来目标更新。仍保留每boot一次采集保护，30分钟结束后不可声称可重开。native_motion.py仅用于已正确初始化的voicecam，不自动启动/复位/采用坐标。此轮三个模块已ARM64独立编译，O0/O2真实模式代码回归通过，46项Python回归通过；尚未整包链接或RAM加载。动态TTS、实际拍照事件及运行桥尚未接完。

后续覆盖：voice-mode独立整包已成功，证据evidence/voice-mode-20260915/verification.json，尚未上板。串口事件订阅与溢出/关闭处理已测试，Python总48项通过。

photo_capture.py接现有FrameCache和板端POSE/PHOTO/PHOTOQ：等待模式应用，核对epoch/顺序/角度质量，按q保存对应USB帧，fsync完成后才photoack，板端done确认后发saved。生产保存和语音消费分离，最多9个阶段事件，不因TTS等待错过确认。native_ports.py已组合Motion/PhotoCapture，真实speech.say/stop适配仍必需；没有空播音成功回调。四项新增测试含三图实际临时文件、缺帧、非法角度、慢播报不阻塞ACK，总52项回归通过。测试图片为人工协议fixture，非真机拍摄验收。

阶段TTS与停播候选：NativeSpeech实现say/stop，可传给NativePorts。tts-prompt按固定英文key取25条中文提示，生成表由tools/generate_board_voice_prompts.py维护；K7S1P阶段协议不受echo-test文字替换。后台播放启动握手先于停播状态确认；停止取消网络及PIO播放，只有busy=0且正常结束或清理成功的ECANCELED才通过。开始状态不明时仍发停止，但不宣称已停。PIO取消不绕过关功放/SAI停止及codec/platform/I2C恢复，失败保留故障。七个模块ARM64临时编译通过，PIO三场景O0/O2模拟寄存器回归通过，Python59项通过。运行桥仍是旧进程，候选没有RAM加载。

最新完整候选是voice-stage-20260915（5cc67bd2…），包含voice-mode及阶段播报/停播，已整包构建并归档，未上板。下一步统一ASR与USB运行入口，更新桥和一次RAM部署后再做真机闭环。

最新架构约束：本目录是测试和参考工具，不是最终产品必需的电脑运行时。实际控制正在迁入app/k7agent/cloud与app/k7host，见docs/整机板端整合接续_20260915.md。
