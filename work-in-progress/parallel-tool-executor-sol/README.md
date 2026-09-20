# MiMo 本地工具执行层候选（sol）

这是一个隔离的 C++17 主机候选，只在本目录实现并验证。它不接网络 API、模型、正式源码、SDK、VM、设备、串口、相机或无线硬件。`FakeExecutionPort` 是确定性的主机假端口，它实现与未来板端适配器相同的 `start/poll/cancel` 接口，但其结果仅证明执行层状态机可工作，不能作为设备结果。

## 边界

模型输出只允许以下三种、固定字段顺序的 JSON。根对象不能带请求 ID、事务 ID、状态、结果或成功声明；可信调用方通过 `Executor::submit(trusted_request_id, model_json, now_ms)` 单独注入非零请求 ID，执行器分配生命周期内不复用的事务 ID。

```json
{"version":1,"tool":"photo.capture","args":{"camera":0},"timeout_ms":1000}
{"version":1,"tool":"device.status","args":{},"timeout_ms":1000}
{"version":1,"tool":"network.scan","args":{"limit":5},"timeout_ms":1000}
```

输入最多 256 字节，版本必须为 1，超时为 1..30000 ms，camera 为 0..2，scan limit 为 1..8。字段缺失、重复、换序、未知工具、未知参数、前导零、溢出、转义字符串、非 ASCII、尾随内容均拒绝。`password`、`passphrase` 和 `psk` 字段在解析最前端返回 `SensitiveField`；本组件没有凭据类型、凭据句柄、联网工具或原文日志接口。上游 prompt 也必须禁止提供密码，因为执行器只能阻止密码继续流入，不能撤销模型已经看见的内容。

`Accepted` 只表示执行端口接受了调用。成功只能来自随后 `ExecutionPort::poll()` 返回的类型化 `PortResult::Succeeded`，且结果经过定长数组、NUL、数量和电量范围检查。模型 JSON 中加入 `success:true` 会因 schema 不匹配被拒绝。取消和到期都会调用真实端口的 cancel；终态后迟到 poll 不再读取端口。未来硬件适配器仍须自行证明底层停止/清理栅栏，不能把本地 `Cancelled` 当作相机或无线已经静默。

响应写入固定 192 字节缓冲。超限时丢弃部分响应并返回固定 `response_too_large` 错误，不输出截断 JSON。SSID 和 asset ID 只从执行端口结果生成，模型不能供应。执行失败只返回稳定错误类，不回显模型原文、端口私有错误文本或凭据。

## 复现

在本目录运行：

```powershell
python run_tests.py
```

脚本用工作区系统 `g++`，以 C++17、`-Wall -Wextra -Werror -pedantic` 分别构建 O0/O2，并各运行同一组测试。每轮命令、退出码、耗时、二进制哈希和原始 stdout/stderr 保存在 `evidence/<UTC>/`。初次 Python 3.6 runner 兼容失败和首轮账本测试失败均保留，不冒充通过结果。

当前限制：固定账本最多保留 8 个请求且没有回收 API；适合集成前的有界候选和单会话探针，正式接入前应由可信会话层定义终态确认、释放和跨重启防重放策略。本候选不支持并发线程调用，调用方须串行化 `submit/poll/cancel/response`。
