# 主机语音编排候选接口

本目录是统一仓库中的待集成候选，不是新的产品入口。C++17 主机实现；未编译进 openvela，未接麦克风、喇叭、云服务或部署 Agent。

`Machine` 仅由单一协调线程调用。`take()` 最多交付一个 Command；每条命令带不复用的 transaction 和同事务 operation 序号。只有匹配二者及 kind 的工作结果能推进状态。容量为一，没有排队；忙时 start 返回 false，不更改当前事务。事务 ID 用尽拒绝新请求。文本上限默认 8192 字节，WAV demo 上限 2 MB/60 秒/16 kHz，输出 PCM 上限 2 MB。

状态顺序：Idle → Listening（读 WAV，并非录音）→ Recognizing → Handling → Speaking → Idle。错误/取消/截止进入 Cancelling；清理失败或尚未确认继续保持，不能直接转 Idle。取消完成返回 Idle/Cancelled；其他故障完成转 Error，显式 resetError 才能重新开始。单调时钟回退为不可重置 ClockError。总时限默认 90 秒，阶段 30 秒，等于时限时超时先于结果；释放等待没有冒充完成的“强制超时”。

资源策略可配置为 ReleaseBeforeTask（默认）或 ReleaseBeforeTts。前者 ASR 结束后先释放再调用 TaskPort，后者允许 ASR 在 Handling 期间保留，以便评估不同任务端口策略；两者在创建 TTS 前都必须完成 Release，并在事务结束释放全部资源。每笔事务 ASR/TTS 各创建一次，不按音频块加载。SpeechSession 已移除同时创建两模型的 init，新增互斥 initAsr/initTts，内部 close 返回后才调用下一个 create。模型持有在工作线程，禁止与外部线程调用 C API 交叉。

`TaskPort::handle(transaction, transcript, stop)` 是工作线程上的阻塞边界；返回回复文字，异常代表失败。`close()` 是同步资源清理/后端退出确认，必须 noexcept，允许阻塞；真实网络/Agent 适配器不得仅发送取消请求就让 close 返回。不可中断同步 C API 的 deadline 只用于标记取消，不能抢占 Create/Generate/Decode。demo 使用 async 工作线程，协调线程每 2 ms 检查状态；唯一跨线程字段是 atomic stop，结果通过 future 同步。析构先置 stop、等待线程退出，再关闭资源，因此可能阻塞；外层主机测试进程有 60 秒上界。量产需要板端 watchdog/工作线程恢复设计，不能异步 free 正在使用的模型。

默认 ExampleTask 无语义解析，只对非空识别结果返回固定中文句子；替换为 Agent 时实现 TaskPort、保留事务编号、文本容量和取消语义，显式确定网络/模型资源预算，另行授权服务和凭据。本实现没有部署 LLM，不做任务理解准确率宣称。

MockWifiTask 仅模拟后端，以固定测试凭据和文档示例 IP 运行 broker。只有认证、DHCP、有效 IP、worker_exited、link_up 的成功组合才得到 IP_READY；取消后 DRAINING 一直保留无线所有权，直到 worker_exited 且 link_up=false。测试覆盖晚到成功仍不释放。mock 的 close 人工提供模拟退出确认，不能直接替换为真实驱动确认。

版本固定 sherpa-onnx 1.12.14（26aa2fa9）/官方 Windows x64 C API、ORT 1.17.1、CPU 单线程。模型为已核对的 bilingual streaming Paraformer int8 与 aishell3 VITS；300 ms 尾部静音仅用于该 Paraformer profile，16 kHz 显式输入，无前置静音；1024 decode 预算/512 帧块，不在 InputFinished 后 feed。TTS 模型实际 8 kHz mono PCM16，不能按 16 kHz 播放。原版本官方实现依据见只读 tuning 交接。

WAV demo 支持本机 Windows 原生窄路径约定，不是通用 Unicode 路径适配器。生成结果仅在事务 Success 且全部释放后写文件；写失败返回错误，可能留下不完整 WAV，调用方必须依据进程退出码验收。不得将存在文件本身作为成功证据。事件来源是可信本地 worker，Machine 不防御伪造 released=true 的不可信端口。
