# 最小 PN 拒绝记录补丁（未应用）

`pn-diagnostic.patch`基于父审计inputs.json锁定的正式源码；候选副本为skw_wifi_amsdu.h、wifi_ip_service.inc和新增skw_wifi_pn_diag.h。只写本目录，旧交付冻结不变。没有SDK/设备/无线操作，未改正式接收行为或计数器。主代理独占审查和集成。

新增`skw_amsdu_receive_diag(..., struct skw_pn_diag*)`，原`skw_amsdu_receive`包装为diag=NULL以保持旧调用接口。仅四个本地-EACCES返回分支增加可选纯记录：FLOOR、PENDING_NEWER、PENDING_TUPLE、DUPLICATE_INDEX。记录调用返回原-EACCES，读取receiver状态但不修改receiver、floor或payload；原inspect/EPROTO/其他回调错误路径不变。service候选传入独立static recorder，原rejected计数和已有日志完全保留。

每条记录保存：reason、单调时间、incoming PN/floor、TID/mc/amsdu/first/last、incoming sequence/原始index、pending active/PN/sequence/bitmap/first_index/last_index/last_seen、age及age_valid。duplicate分支原代码已把index转相对值，记录时加回first_index。pending inactive不输出陈旧字段；now早于started则age_valid=false、age=0，避免无符号下溢。不记录密钥、地址、原始帧或任何载荷。

固定16条，只保留前16个符合采样限频的PN拒绝，不滚动覆盖；首次可记录，随后最多每1000ms一条，倒退时间不绕过限频。seen/suppressed/full均UINT_MAX饱和，不回绕。计数满后只增加full；无堆分配、无递归、无新锁、无接收路径printf或I/O。采样共享四种reason，故高频一种原因可能挡住另一种；suppressed/full明确标记证据不完整。不会自动复位或每次重连清零，因此跨连接留存证据不能误作单连接统计。

**记录器仅由现有single RX owner读写。** 本版不新增异步status命令、导出线程或公开实时指针。g_wifi_pn_diag保持service静态，不对其他任务暴露；若未来需要串口导出，应在同RX owner处理显式snapshot请求，复制固定数组后再输出，或暂停该owner后只读。不得从另一个任务直接遍历，避免数据竞争；本补丁尚未接入此快照请求通路，因此这是可审查的采集候选，不是现成设备取证命令。运行记录额外应由主代理关联连接代次/pn_reuse/实际镜像哈希，记录器不保存密钥。

## 复现与验证

运行`python run.py`：首先验证父inputs.json中全部9项冻结输入，再生成候选/补丁；每个编译/测试15秒上限。原tests/wifi/test_amsdu.c对候选包装接口执行；差分测试另一个翻译单元直接包含固定正式原头文件，每个步骤比较原/新返回值、deliver计数以及完整assembly/replay内存状态。覆盖四种记录原因、250ms以上pending非聚合拒绝、1000ms限频边界、时钟倒退、16条满、UINT_MAX饱和、unsupported诊断分支以及3000步确定混合序列。记录完整原始stdout/stderr、命令、退出码和哈希。所有输入帧都是合成，不是现场payload回放。

行为一致是上述实际输入集合的结果及窄补丁静态审核结论，不是形式证明或并发性能验收。新增记录有固定时间/内存开销，不宣称零开销。待主代理核对NuttX编译、service接线、实际镜像、记录器内存预算、真实RX节奏及同owner快照导出。没有修改或放松PN拒绝、安全floor、超时清理、统计口径，也没有声称解决本轮无线异常根因。
