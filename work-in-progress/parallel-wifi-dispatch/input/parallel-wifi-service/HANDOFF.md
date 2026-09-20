# BLE/VoiceLink 共享 Wi-Fi 事务服务交接

主机候选完成；未改正式网络服务，也未重新生成上一份 parallel-voicelink 交付。

- 实际会话 ID：`01a0892e-2964-7ec3-bd76-9ab4937980cb`（CODEX_THREAD_ID）。会话cwd为 `E:\openvela`，本轮测试cwd及唯一输出为 `E:\openvela\VelaVision\work-in-progress\parallel-wifi-service`。
- 未操作硬件、串口、BLE控制器、Ubuntu/SDK、固件或存储设备；未提交/推送，未改中央日志或manifest。
- 输入9个文件及哈希在 evidence/inputs.json，包含正式worker/协议源码与上一交付接口。两次实际测试都确认输入与快照未变。

交付：CONTRACT.md先行接口设计；include/wifi_broker.h和src/wifi_broker.c为固定容量C11核心；tests/test_broker.c含确定性模拟backend与故障注入；include/voicelink_adapter.hpp和tests/test_adapter.cpp为C++17适配示例及测试；INTEGRATION.md给出正式文件/函数/行号对应的精确替换建议，未应用。

核心区分 RECEIVED/CONNECTING/IP_READY 和 CANCELLED/TIMEOUT/FAILED，并独立保持 QUEUED/RUNNING/DRAINING/OWNED 射频状态。单射频争用返回busy；取消后未退出/离线继续占用；迟到成功不改变终态。成功连接保留owner，普通cancel不拆连接。请求ID在拒绝时也递增，耗尽永久id0；每事务完成事件有递增序号，隔离过期与乱序。

## 复现与证据

```powershell
Set-Location -LiteralPath 'E:\openvela\VelaVision\work-in-progress\parallel-wifi-service'
python -u run_tests.py
```

Python 3.6+标准库、PATH中的MinGW gcc/g++即可。核心独立以 `gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror` 编译，再用 g++ C++17链接adapter测试；没有把C源码当C++编译。所有子进程有60秒上限，输出、失败/超时退出码及源码前后哈希保存到新的时间戳目录。

最新结果：`evidence/run-20260910T031114079516Z/result.json`，passed=true。C核心/适配编译和两个可执行测试均退出0；broker共10,826条断言（包含5,000步固定种子交错事件），不是10,826个独立场景。此前首轮135条断言的通过证据保留在 `evidence/run-20260910T031034243645Z/`。这两轮没有构建或测试失败，不补造失败记录。

覆盖：双客户端/同客户端争用；拒绝ID与耗尽；错owner/旧id/旧sequence；取消/超时底层未退出及迟到成功；清理后重试；queued启动失败及taken后启动失败语义；复制和清除密码；认证/DHCP/IP/退出条件不全；时钟回退、接近UINT64_MAX、恰好超时边界；成功后所有权与显式release；外部旧连接保护；有界history淘汰不影响活动事务。适配器验证接收/忙/成功IP转换、非本事务取消无效、成功后cancel不拆连接、未实现scan明确失败。

## 尚需主会话完成

1. 核对输入哈希，审查INTEGRATION.md，在正式应用引入服务任务、消息队列/互斥、可信owner及外部id映射。候选C结构仅允许服务任务串行调用，不是已经线程安全的多生产者服务。
2. 从prov_wifi_connect移除隐式停止旧网络路径，将所有联网/扫描入口纳入同一所有权；实装独立worker、认证/DHCP绑定、实际停止请求与退出栅栏。IP worker成功后仍运行，不能用DHCP通知释放射频。
3. 单独审计SDK、编译、安排有界真机验证。没有实际Wi-Fi成功/线程取消/长稳或固件构建结论；未跑sanitizer或真实多线程压力测试。
4. 本会话已由主会话登记中央日志源（接收文档有记录），继续统一采集并运行原版官方校验器。本轮不改中央日志，不自行声称此轮新增消息已全部采集。
