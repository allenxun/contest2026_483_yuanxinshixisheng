# 原生 llama 编译与 NEON 验收

主线已有实际 ARM64/NuttX 编译和链接结果，尚未运行语言模型。最新已验收 `graph-core-20260910` 的零权重真实 ggml 图；当前设备切换状态见 project-manifest。完整 llama ELF 尚未上板。

## 真机范围

串口在前次加载中消失；原失败日志及哈希保留在 `evidence/neon-file64-20260910/interruption.json`。COM8恢复后确认U-Boot，使用 `uart_load_neon_file64.py --resume-preserved-snapshot` 保留原快照。逐块与完整镜像/固件CRC、DTB签名、NSH启动门禁通过。未写eMMC或STM32。

- 8个idle任务及服务CPU0亲和性通过。
- C++构造、主线程异常RAII、对齐分配、线程/条件变量通过；off_t实测64位。尚未读取模型普通文件。
- CPU4/5各两线程，5.047秒，D8–D15低64位上下文诊断通过，四线程共142331批、错误0。只覆盖该寄存器范围；不是全部SIMD状态、并发异常或LLM结果验证。
- Windows BLE真实密码提交→WPA2/DHCP→IP10.3.0.214和状态回包通过，30秒保持通过；网关5/5含首包。测试客户端主动断开。
- A-MSDU拒收在网关测试前已为1、测试后仍为1；成功交付1组2子帧。不推断原因，不宣称严格零异常或长期稳定。

验收及原始证据：`evidence/neon-file64-20260910/acceptance.json`。

## 原生编译与链接

固定 llama.cpp b5046/74d4f5b041ad837153b0e90fc864b8290e01d8d5，沿用已核对静态注册及checked线程池候选。使用当前SDK真实aarch64-none-elf GCC13.4.0、NuttX头文件和libc++17.0.6；没有采用Windows编译产物。

第一轮39个编译单元中29通过：`evidence/llama-native-compile/20260910T071153Z/`。主要缺口为libc++宽字符/locale未启用，以及第三方局部UNUSED宏与NuttX同名宏冲突。C编译模板同时继承了应用的-Werror，暴露上游未定义特性宏和未使用静态函数告警。

独立 `cxx-locale-20260910` 打开CXX_WCHAR、CXX_MINI_LOCALIZATION，SDK差异审计及完整固件编译通过。第二轮只在独立派生源码中把局部UNUSED命名为GGML_LOCAL_UNUSED；对第三方保留undef/unused-function告警但不升级为错误。没有修改冻结vendor或全局关闭告警。39/39对象通过，证据 `evidence/llama-native-compile/20260910T071713Z/`，含命令、日志、源哈希和派生说明。

`check_llama_native_link.py` 使用现有NuttX真实链接命令及运行库，单独输出ELF；首版门禁误拼checked池创建符号，并把未定义U符号算作存在；不能据此宣称五个入口均定义。原结果保留。修正为要求T/t定义后，v2模型加载、context创建、decode、tokenize及checked池创建/销毁/预算共七入口全部通过，链接退出0；证据 `evidence/llama-native-link-20260910-v2/`，ELF SHA256 c9e2737ce1ab14d696272602954067cf26f12fb04cea221e25e059c2aa62200b。链接使用内存7424KiB，超过现有诊断加载器6MiB门限；不得把这份ELF直接交给现有加载流程。还需核对PT_LOAD、MMU/堆边界、独立构建来源和完整异常表。

这只是链接门禁：没有应用入口注册、真实张量图执行、权重加载、内存峰值或token性能结果。GCC的single线程运行库风险仍由独立并发异常探针检查，不能因链接成功忽略。

## 并行接续

原六份候选已交付。本轮再次分派三个独立子目录：C++并发异常 `concurrent-probe-v1`、模型流式SHA256 `integrity-v1`、checked池亲和性 `affinity-v1`。主会话独占SDK、串口和正式集成，不让代理修改冻结输入或硬件。

后续按内存布局/零权重图→并发异常和真实池→只读模型文件/哈希→模型输出/Tool真实事件→语音顺序接入。密码始终由规则解析，不送模型；没有设备ACK的动作不报告完成。

日志仍为 `logs/maomaojiang01/` 的真实会话导出。格式验证不等于完整子代理原始记录已单独采集，未取得的子代理UUID不编造。首次配置生成脚本误以为defconfig显式记录默认locale选项，断言失败后改为追加真实Kconfig设置；失败工具输出保留在原始会话。


## 后续真实图和异常对照（本轮新增）

`graph-core-20260910` 实际加载 SHA256 6b68dbff8afcd866f8d6e806885f209bd71dcf6e8cd8379b3bd40d768d8ea27b，驻留6443008字节。独立8MiB门禁核对PT_LOAD、堆起点和保留区；原6MiB门禁保留。2/4配置线程各完成64×64乘法4096项，checksum=-10、错误0；辅助线程1/1和3/3创建/退出，资源计数归零。两组总观察约0.828秒不是token性能。未采集物理CPU分布，不能称四核推理。证据 evidence/graph-core-20260910/runtime.json。

同镜像BLE真实凭据→WPA2/DHCP/IP、30秒保持和网关5/5通过。普通堆总125677568字节，快照free125595968；拒绝累计1→1，成功交付1组2子帧。历史AMSDU rejected标签实际覆盖所有数据接收拒绝；另一次flags=0x76样本是非A-MSDU，PN顺序拒绝两个分支仍缺现场PN/floor/pending证据。不要把标签等同于已定位A-MSDU根因。

`cxx-eh-20260910` 的双worker首次异常在0.047秒内异常终止，无worker结果和joined完成。确切返回PC核对后，abort位于uw_init_context_1，不能误标为Phase2。现有single-thread libgcc存在FDE列表初始化发布和register-size表初始化两处可行并发窗口，但未证明现场命中哪一支。libc++abi使用pthread TLS，不能归为单全局eh_globals。失败原始证据位于 evidence/cxx-eh-20260910/cold/，随后neon基线无线已恢复再切换graph。

新增独立 `eh-control-20260910`，只做新启动CPU5单worker一次与另一次新启动main完整预热后CPU4/5各一次。273FDE、首初始化注册、实际TU宏及源码哈希已核对；测试结果以 evidence/eh-control-20260910/ 为准。预热成功也不是通用并发安全修复。

app/k7agent/tool_api已迁入有界JSON类型化请求候选并通过真实ARM64编译；未注册设备后端或实现自然语言推理。模型池审计发现权重、KV、scheduler、scratch、output与元数据分属多条分配路径，不能只改一个malloc或ggml_init。普通模型文件、同句柄校验接入及完整分配预算仍是后续门禁。
