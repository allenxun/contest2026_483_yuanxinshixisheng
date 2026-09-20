# K7 codec C 事务层候选交接

2026-09-10；会话 `01a0892e-2964-7ec3-bd76-9ab4937980cb`，cwd `E:\openvela`。唯一开发输出为本目录 `E:\openvela\VelaVision\work-in-progress\parallel-k7-codec`。主会话按约定主动读取此交接，不再询问已有授权或派发新任务。

本阶段已完成可移植C11事务引擎及主机验证；**完整硬件录音序列未确认，默认ES8388计划返回KC_NOT_READY并且零设备访问**。这是明确的资料缺项，不是板端驱动完成。

变更清单：

- `include/codec_txn.h`、`src/codec_txn.c`：固定容量、零动态内存；7-bit I2C接口、独立TX/RX长度、读回掩码白名单、延时/clock-ready/控制端口；上电/初始化/录音路径准备/ready/停止/错误状态；单事务、不可复用ID、配置快照、重入拒绝、取消与绝对deadline、部分初始化后清理确认与恢复门禁。
- `tests/test_codec.c`：真正链接执行候选C代码的模拟I2C/控制/时钟端口，非Python行为替身；测试所有访问失败、短/长/分布错误长度、迟到返回、调用前超时、delay预算/提前返回、读回失败、不支持配置、重入、取消、时钟倒退、部分初始化重试、清理失败/迟到确认、旧ID、ID耗尽及硬件计划拒绝。
- `CONTRACT.md`：目标端口最小移植点、串行服务线程契约、阻塞调用及清理所有权。`PROVENANCE.md`：逐类配置的来源、参考与待核实项、读回条件及不能盲移植的原因。
- `input/`：上项已固定的14个官方blob，本轮再次逐个SHA核对；另复制三份前项交接/结论，共17个输入文件。没有复制模型/私密配置/构建全集。`candidate.patch`仅含本轮新增候选/测试/脚本，不含官方blob。

最终真实编译与测试证据 `evidence/run-20260910T045004718979Z/`：GCC 12.2.0，C11、Wall/Wextra/Werror/Wconversion/Wshadow/pedantic，O0/O2分别编译执行成功，**各2270个检查、0失败**。freestanding编译成功；nm -u仅memcpy/memset，未引用malloc/calloc/realloc/free。未执行目标ARM编译、SDK构建或板端测试。

复现命令：

```powershell
& 'C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 'E:\openvela\VelaVision\work-in-progress\parallel-k7-codec\scripts\run_tests.py'
```

每次运行建立新UTC时间戳目录；results.json保存每条真实argv、exit、timeout和30秒上界，stdout/stderr原始字节、源码SHA、编译对象和测试二进制同目录。早期两轮分别1956/2252个检查通过，保留原证据；最终增加错误阶段/原错误与清理错误隔离等检查。厂商官网PDF取回超时的实际失败留在本会话工具记录，未根据第三方镜像补数值。

关键审核结论：默认参考仅含可追溯的CONTROL1 reset两次write，没有可用的硬件readback白名单或完整capture步骤；Linux probe多次write不验错、mute为no-op，且0x35写入与regmap.max_register=0x34矛盾。16kHz/MCLK4.096MHz/BCLK512kHz为待测请求profile，未证明目标slot/codec通路已匹配。所有模拟寄存器计划明确SIM_ONLY，不能搭配HARDWARE端口运行；TARGET_REVIEWED审核标志须由可信集成者根据真实证据填写，不能仅改位绕过缺项。

主会话仍需：厂家完整手册/勘误与可读掩码，实板codec身份及电源/时钟/模拟输入实测，I2C3有界事务适配器，SAI/DMA停机与所有权确认，录音初始化/停止/错误恢复具体计划，之后才可安排有界录音验收。核心检测deadline无法抢占阻塞下层；下层必须保证超时落实且返回后不再使用栈buffer。一个物理codec只用一个串行owner/context；本层防重入不是SMP锁。

没有访问板子/COM8/蓝牙/USB/执行机构或SDK/VM，没有使能功放、修改正式源码/旧交付/中央日志、提交或推送。前项Kconfig并发变更仍保持unchanged=false，本轮未回滚。日志归属同仓logs/maomaojiang01；请主会话按上述真实会话ID核对采集和原版官方校验，本轮没有手写JSONL。输入最终复核和交付SHA见evidence/delivery.json。
