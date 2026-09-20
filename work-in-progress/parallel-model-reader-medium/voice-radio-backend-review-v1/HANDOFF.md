# voice-radio-backend-v1 完整 include / 生命周期自审

发现3项需在SDK集成前修正。冻结旧目录不变，本目录 review-fix.patch 只修改原候选的 prov_service.inc、radio_backend.inc、radio_backend_state.inc；应先应用 v1 candidate.patch，再应用本增量。三个对应完整文件也在本目录，输入哈希记录的是旧冻结候选，不是当前Git HEAD。

## 1. shared静态声明导致Werror失败

prov_service.inc声明g_prov_ap_count未条件保护，但其所有读写均在 !SHARED 的旧扫描collector/旧PROV_SCAN分支。SHARED启用时它成为未使用static变量，GCC Wall/Werror实际报 unused-variable。修复将该计数声明移入g_prov_aps已有的 !CONFIG_EXAMPLES_K7RADIO_SHARED guard，不标unused、不关闭警告。unused-before.c 是精确声明编译接缝，预期编译失败已保留；after分别shared开/关编译成功。未声称这替代完整NuttX翻译单元编译。

## 2. pthread_join错误仍可能有活worker，不能覆写其结果

旧reaper遇pthread_join失败后写rb_result=rc；operation线程退出时也写rb_result=ret，两者没有成功join形成的先后保证，reaper的锁也不被worker使用。修复使用独立reaper-owned rb_join_error，不碰活worker拥有的rb_result。此时仍held，也不擦除worker可能正在读取的job密码，不假装join成功。测试用实际operation线程停在受控等待点，注入join错误：旧版会覆写worker结果31337，新版保持结果并只记录join_error，之后允许worker继续。它是确定性所有权复现，不是TSAN报告，也不模拟真实pthread错误频率。

## 3. 终态可见之前需完成backend槽交接

旧版先ws_post/wd_post发布清理完成，再清rb_queued。pump可以立即处理完成、释放旧radio并接受新扫描；此时rb_enqueue却因旧槽rb_queued=true返回忙，新合法扫描被记Failed。修复先构建完全本地的终态事件，再清backend槽，最后发布事件，发布后reaper不再读写旧job共享字段。radio仍由dispatcher持有，直到它消费该事件；因此槽提前清理不会允许RF并发执行。连接的IP_READY不清槽，只在最终离线clean事件清槽。

确定性测试在实际reaper发布回调中插入pump/下一扫描：旧版稳定出现VS_FAILED=4，新版下一轮VS_PENDING=0且held=1，O0/O2均成立。未以概率循环代替复现。正常扫描/连接失败及CLOSE失败、无RX排空、STOP失败保持held的4场景回归也均通过。

## include/声明核对

- k7radio_main.c先声明skw_bss/global radio状态，再在IP+SHARED下include radio_backend_state.inc；state定义使用到的基本类型和skw_bss已经可见。
- wifi_assoc_probe.inc中fw_wifi_ip_session的static前置声明与wifi_ip_service.inc定义一致；rb_ip_entry在fw_wifi_ip_worker定义之后；rb_thread原型与后置radio_backend.inc定义一致。
- radio_backend.inc在assoc/IP实现之后、prov_service.inc之前，因此prov_wifi.inc经prov_service引入时能看到rb_ready/dispatcher及API。未发现新的static/extern冲突。
- wifi_dispatch.c/wifi_scan.c/wifi_broker.c是独立翻译单元；不能用unity include拼成一个文件，其各自private lock/begin命名不是跨对象链接冲突。
- SHARED关闭保留旧kthread维护worker与旧BLE扫描；本补丁将计数guard与已有数组guard保持一致。
- 已观察到原候选宏fw_wifi_command→raw跨度包含fw_wifi_wpa_command回调，因此该回调不走rb_note。当前正式skw_wpa_transport只通过它发12/13/15，cleanup另有rb_keys实际结果记录，当前不影响OPEN/SCAN/CLOSE事实。若回调后续扩展CLOSE/OPEN类命令，应先收窄宏作用域；这里没有扩大本次修复范围。

## ABI、凭据及剩余风险

v1的wd_dispatch增加scan指针，ws_done增加error；core头、对象及所有调用方必须一致重编，禁止复用旧静态库/旧struct尺寸。review只增加main私有rb_join_error，没有再次改变外部C ABI。本目录主机测试头/对象一致；完整目标编译仍待做。

队列复制凭据后，BLE req立即擦密码；dispatcher取出队列时擦原槽；backend成功join operation后通过volatile wb_job_clear擦密码/SSID，仅保留owner/id以匹配维护连接事件；最终交接再次擦job。完成事件和scan快照不含密码。join失败时仍活worker的借用不能提前擦除，保持held等待受控恢复，不宣称所有故障都即刻清除每个内存副本。WPA supplicant维护期副本沿原实现生命周期，不把本审查当全库密码清理审计。

仍须目标确认pthread join/属性/栈/调度、sem/mutex有效对象的实际失败策略、永久服务启动中途失败的受控恢复、真实DMA/RX/firmware关闭后晚到行为、CLI禁止旁路完整性及真实BLE epoch/IP验收。nxsem_post目前正常有效单槽预期不失败，失败分支仍未全面注入；初始startup失败保持gated不是自动回滚。没有访问SDK/COM8/设备、没有改正式/中央日志。

运行run_tests.py，每进程15秒限制；O0/O2编译严格Wall/Wextra/Werror/Wpedantic。test-output.txt保留原版与修正版、预期编译失败及普通路径回归。测试radio操作是显式mock，pthread/reaper代码真实编译执行。
