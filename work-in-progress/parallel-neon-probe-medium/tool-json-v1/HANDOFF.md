# 有界 JSON → Request 候选 v1

仅本目录新增，未修改旧候选、dispatcher、broker、正式源码或日志。未接触SDK/VM/硬件/模型。源码为 tool_json.hpp/.cpp，C++17，依赖固定哈希的 parallel-robot-tools/include/dispatcher.hpp。不重写状态机、不自动submit、不构造DeviceEvent、不调用网络或执行机构。真实主机编译/测试及原始输出在host-results.json与编号stdout/stderr；输入输出SHA256在hashes.json。

## 模型唯一可成功请求的 schema

```json
{"version":1,"tool":"Capabilities","args":{},"ttl_ms":1000}
```

```json
{"version":1,"tool":"WifiStatus","args":{},"ttl_ms":1000}
```

根对象必须恰有version/tool/args/ttl_ms四个字段，可任意顺序；version整数恰为1；ttl_ms整数1..30000；只允许标准JSON空白SP/TAB/CR/LF。最多256输入字节（包含空白），非空；对象最多两层，无递归。键和值中的标识符字符串最多32字节，ASCII字母或下划线、非空；大小写敏感。此为**严格JSON子集**：所有字符串转义（包括合法Unicode转义）、非ASCII、BOM、负零、前导零、浮点/指数、注释均拒绝；不宣称完整RFC JSON实现。字符串中的未转义控制字节、NUL和非法字节均拒绝。

重复字段/未知字段/缺字段/错误类型/溢出/截断/尾随非空白（含第二个JSON对象和NUL）均拒绝。无字段忽略或“最后一个覆盖前一个”。第5根字段或第3参数字段可以报告Syntax/Schema而非Duplicate，但同样拒绝，错误类别不是安全决策条件。整数逐位检查uint64溢出，再按业务域检查；目标坐标在转int之前校验范围。

模型prompt只列上面两种工具。为保留原dispatcher契约，识别但不返回可执行Request：GimbalTarget仅允许args恰为整数x/y，范围x[-800,800]、y[-120,1030]，原validate返回Disabled；Photo/WifiScan/WifiConnect仅允许空args，原validate返回Unsupported。未知工具名返回UnknownTool/Unsupported。没有password、ssid或任何凭据字段，WifiConnect名称识别不代表可配网，不接收配网参数。

## 可信边界与接入

`parse(input, trustedOwner)`只在语法/schema及原robot::validate全部通过后返回optional Request。trustedOwner由会话/调用方可信路由注入，非零；模型不能提供owner、id、state、payload、DeviceEvent或完成标记，所有这些key均未知拒绝。Request类型根本没有id；id由原Dispatcher::submit内部生成，不能由模型或解析器指定。

调用方先检查`result.request`存在，再在原串行owner/单调时钟契约下调用Dispatcher::submit。只读查询被接纳不是设备已执行；take之后仍是Accepted。真实Started/Completed及WiFi状态仅允许未来可信适配层注入。解析器不给模型构造事件的API，没有静态假WiFi状态。

所有失败返回空request，validation保留Disabled/Unsupported/Invalid；ParseError区分主要语法错误。调用方不能仅凭parse==None执行，因为Disabled/Unsupported与TTL/owner验证失败也可能parse==None。无需异常或动态分配：string_view只引用调用方输入，解析期间须保持内容不变；返回Request不保留输入指针。无共享可变状态，可并行解析，dispatcher仍要求串行调用。输入缓冲可读性属于调用者契约，不能传悬空视图。

## 复用评估与内存界限

只读核对本仓app/k7radio/cJSON.c/.h并锁定哈希。cJSON使用动态树节点、全局allocator hooks及通用数值转换；复用后仍需额外限制深度/节点/整数原始拼写、检测重复key。对固定四字段/两层小schema，新增无递归、无堆、单遍扫描适配器更小且不改变无线侧全局hooks。未复制或改写cJSON，不依赖新第三方JSON库。

输入最多256字节，词法扫描线性；根循环最多4次、args循环最多2次，每个整数字节先检查溢出。只用固定标量/string_view/variant/optional；无递归、容器、文件、线程或I/O。测试在一次有效解析周围拦截global new确认无分配，源码审核也无分配路径；不将整测试程序的std::string构造算作解析器内存。

## 主机测试与边界

运行`python run_host_tests.py`，锁定输入变更即拒绝；G++ C++17 O0/O2、Wall/Wextra/Werror/pedantic，单命令30秒上限。覆盖两种允许工具、24种字段排列、禁用/不支持、未知/重复字段、凭据/owner/id/事件注入、类型/范围/溢出、各截断点、0..255单字节替换、256/257字节边界、原Dispatcher接纳后未伪造完成状态。测试实际解析器及原dispatcher头文件，不代表模型按schema输出、NuttX编译通过或设备适配完成。没有连接实际模型或取得任何凭据。
