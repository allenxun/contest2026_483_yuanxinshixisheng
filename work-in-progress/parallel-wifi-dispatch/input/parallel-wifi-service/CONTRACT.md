# 单射频事务契约（先行设计）

本候选只有主机模拟证据。核心为固定容量 C11，不执行连接、线程启动、通知或断开操作。所有入口由同一服务任务串行调用，或由宿主用短临界区保护；不得从并发线程无锁调用。worker 在临界区外工作，通过带 owner/id 的消息返回。凭据只经 take_job 单次转移到 worker 自有缓冲，双方各自清零。

| 射频状态 | 进入 | 退出 |
| --- | --- | --- |
| EXTERNAL | 初始化时尚未证明离线/无工作者 | 宿主明确报告旧系统已离线且无底层执行者后 FREE；不主动停止旧网络 |
| FREE | 无底层操作、无已拥有连接 | begin 接受后 QUEUED |
| QUEUED | 已复制凭据，尚无 worker | take_job→RUNNING；取消/超时/启动失败→FREE |
| RUNNING | 唯一 worker 获得工作 | 认证+DHCP+有效IP+worker退出→OWNED；失败且退出/离线→FREE；取消/超时/失败但仍活动→DRAINING |
| DRAINING | 上层结果已终结，底层尚未确认静止/离线 | 匹配 worker 报告退出且链路离线才 FREE；迟到成功不变成成功 |
| OWNED | 成功连接持续拥有射频 | cancel 不断开；显式 release(owner,id)→DRAINING，真实链路丢失/底层清理确认→FREE |

竞争 begin 一律 busy，包括原 owner 的重复提交；绝不覆盖活动请求。BLE断链不是 broker 事件，不取消已接受配网。扫描不在本轮实现：正式扫描也必须接入同一所有权入口，不能绕过 broker。

每次 begin（包括 busy、参数拒绝和不支持）消耗一个非零 uint64 ID，直到 UINT64_MAX；耗尽永久返回 id=0/EXHAUSTED，不回绕、不复用。id=0 的错误与旧 VoiceLink 接口“总是非零”有不可避免的耗尽边界：适配器返回 Failed，控制器现有零ID保护进入 Error。服务不可在仍可能接收旧消息时重新 init。

结果按 (可信请求者token, id) 查询，外部 BLE 请求 id 不直接充当服务 ID。token由集成层分配，不能信任客户端自报。活动请求单独保存；终态/拒绝仅保留最近8项，淘汰返回 UNKNOWN，不返回其他事务状态。poll 无副作用。成功结果保留拥有者；显式 release 才请求清理。

所有带时钟入口先检查绝对单调 uint64 毫秒时间；回退（包括计数器回绕）视为时钟故障：当前未完成事务终结并安全 draining，永久拒绝新请求，需维护恢复。timeout必须>0；使用 now-start 避免 deadline 加法溢出；恰好期限超时优先于同刻成功。

worker completion 是终结/清理消息，不是每阶段广播。running期间有效成功必须同时声明认证、DHCP、有效单播IPv4、link_up及worker_exited；否则 Failed。quiescent/退出但仍在线的失败仍 draining，不能释放射频。cancel/timeout之后的迟到消息仅可确认清理，不能修改已报告结果。取走的worker密码副本必须在任何退出路径 wb_job_clear；取消不在worker仍读缓冲时强行擦除其内存。不能宣称已实现底层抢占/真实取消。

完成消息带每事务严格递增的非零 sequence，同一个发布器串行编号（不回绕）。重复、旧序号以及未 take_job 前的完成消息被忽略。now 使用服务接收时的单调时间，不能把 worker 旧事件的产生时间传进时钟检查。

`worker_exited` 是受信任宿主确认的执行结束栅栏，不能在线程最后一条语句前随意发布。成功且 link_up=true 时，表示连接操作已结束并把持续链路维护移交给 OWNED；此时维护线程可以继续存在，射频仍被占用。失败/取消清理且 link_up=false 时，必须确认所有能触碰该射频的旧工作及链路维护均已停止，再置 worker_exited。broker 无法检查线程真实退出，集成层必须用完成握手/外部监督证明；不能仅凭“发出停止请求”设为真。

`wb_start_failed` 仅用于尚未 take_job 的调度/启动失败；take_job 已把状态转到 RUNNING 后若线程启动失败，宿主应擦除 job 并报告 failed/exited/offline 完成消息。worker应在使用密码结束后立即清除，不必等长连接结束；取消时仍使用密码的线程由其自身安全清除。指针参数必须有效，job输出不能别名 broker内部存储；结构字段不供业务直接修改，next_id仅测试注入耗尽边界。
