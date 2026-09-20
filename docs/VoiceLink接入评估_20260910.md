# VoiceLink 接入 VelaVision 核对与步骤

2026-09-10，检查用户提供的 E:/openvela/语音模块/openvela-voicelink。该目录作为输入材料，未执行其集成/烧录脚本。本轮未修改正在运行的无线固件。

## 结论

可以作为语音交互组件接入，当前尚不是可直接上板运行的完整语音模块。核心是唤醒词文本匹配、语音选网、密码字符解析和配网状态机；不是通用AI Agent。识别结果今后可进入k7agent任务入口，执行结果通过TTS播报。

## 已核实

- src/core.cpp、parsers.cpp和ports.hpp可复用，ASR/TTS/Wi-Fi已有抽象接口。本机从源码重新编译并执行5组主机测试全部通过；没有用别的机器留下的build目录作为验证证据。
- CMake主机分支只构建core/parsers，测试通过不覆盖speech_engine_k7.cpp、board_hooks_k7.c。原build缓存引用C:/Users/Admin路径，不能直接复用。
- board_hooks_k7.c使用wapi；当前skw_netdev.c未注册无线ioctl处理，真实WPA2/DHCP在k7radio内完成。voicelink当前connect仅以associate调用返回值报告成功，未等待DHCP/IP，不能直接替换已验证的配网路径。
- 当前固件CONFIG_HAVE_CXX、CONFIG_I2S、CONFIG_DRIVERS_AUDIO、CONFIG_AUDIO均未启用。语音代码假设ES8388和/dev/audio/pcm/inp0、outp0，这些不是已有K7驱动的验证证据；须对照实际板版原理图、I2S与codec驱动确认。
- 模型已存在：encoder.int8.onnx 165462184字节，decoder.int8.onnx 71664561字节，TTS model.onnx 30482262字节，合计约255.2 MiB（另有词表等）。CONFIG_RAM_SIZE=132120576即126 MiB。磁盘模型大小不等于峰值RAM，但不能假设当前内存足够；需要测推理峰值、扩展合法DDR映射并避开固件/DTB/保留区，或另选较小模型。
- 未找到随包提供的sherpa-onnx/onnxruntime头文件、目标静态库或nuttx-toolchain.cmake。CMake未配置这些库的显式链接，不能按清单直接宣称NuttX构建成功。
- 对照当前官方C API：构造函数是SherpaOnnxCreateOfflineTts/SherpaOnnxCreateOnlineRecognizer，当前代码使用不同名称；生成音频samples为float*，代码直接当int16_t*使用。需固定依赖版本，修正API、float转PCM16、流式解码循环、音频ioctl错误处理与资源释放。对比的是当前官方版本，不推断所有历史版本。
- 代码明确provider=cpu，因此当前方案没有RK3576 NPU加速；固定矩阵INT8成功不能代替ONNX语音运行时。

## 统一项目中的安排（拟定，尚未复制/启用）

app/voicelink/ 保存语音状态机、解析器和端口适配；port/audio/ 保存板端录放音适配；app/k7radio/提供统一Wi-Fi接口；app/k7agent/接收识别后的普通任务文本。模型通过独立清单与哈希管理，不把build目录和所有浮点/INT8模型一起塞入固件。

调用关系：麦克风→音频采集→ASR→语音路由；配网意图→现有Wi-Fi服务，机器人任务→Agent→已有Skill/Tool；真实执行结果→TTS→喇叭。

密码路径留在本地配网状态机，不作为普通任务发送给语言模型或日志。

## 分阶段实施与验收

1. 导入可复用源码到统一仓库，保留来源/作者/许可信息和哈希，默认关闭APP_VOICELINK；通过tools/sync_sdk.py审计同步。原集成脚本有删除已有应用目录、直接追加SDK配置的行为，不符合当前同步流程，不能直接运行。
2. 把k7radio现有扫描/认证/DHCP封装为共享服务API。不是调用当前static函数或执行带密码的shell命令。BLE和语音共用锁/队列，保留事务ID、状态和超时，只有真实IP就绪才成功；在线扫描返回明确不支持，开放网络在实现前返回不支持。避免两套管理器同时控制模组。
3. 独立录放音验证：板版codec和I2S确认→录制可验证PCM→播放固定音频。此步成功前，不把ASR失败误判成模型问题。
4. 固定sherpa-onnx和ONNX Runtime版本、目标工具链及依赖，修正API与采样格式，验证NuttX链接、模型存储、内存布局。先用固定wav识别和固定文本合成，记录时延、峰值内存，再接麦克风。当前模型完整离线运行是主要工程风险。
5. 语音配网联调：真实扫描→播报→选网→密码→WPA2/DHCP→成功/失败播报；测试BLE并发忙碌、取消、超时，避免泄露密码。
6. 接入Agent：增加普通任务文本路由，先“报告状态”，再拍照等能力；Agent部署仍需选定实际模型/服务，VoiceLink本身不提供任务推理。云台按独立授权和验收推进。

优先完成第2、3步，分别复用已经打通的联网能力和解决麦克风/喇叭基础；不应先把全部模型塞入当前126 MiB配置。此次仅核对方案和主机测试，未完成语音上板。

## 证据与来源

本机复测在 evidence/voicelink-review-20260910/，review.json记录核心源码哈希和范围。

官方API核对：https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/sherpa-onnx/c-api/c-api.h （2026-09-10读取）。本地关键文件：原模块src/board_hooks_k7.c、src/speech_engine_k7.cpp、CMakeLists.txt、docs/ENGINEER_CHECKLIST.md；统一项目app/k7radio/skw_netdev.c、prov_wifi.inc、artifacts/wifi-arp-20260909/.config。


## 用户确认的硬件资源

实板为4GB DDR / 32GB eMMC。126MiB仅是现有BSP窗口，应优先扩大经核实的可用内存、接入模型存储，而不是将其当成硬件上限。详见DDR与eMMC资源接入_20260910.md；当前未执行扩容或eMMC写入。
