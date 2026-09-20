# ret=-13 只读审计

结论：**当前样本不是解析器意义上的A-MSDU子帧。可定位到两种PN顺序拒绝条件，但缺证据不能确定是哪一种，更不能据此认定硬件故障或攻击。** 未修改正式源码、统计、安全检查；未访问设备/SDK。所有结论以inputs.json固定源码为依据，需主代理确认实测镜像对应这些源码，不能以当前源码哈希替代实际固件追溯。

## 已能判定的内容

`skw_packet.c`只处理SDIO槽外层编码/解码，不拥有本条-13决策。真实路径是`wifi_ip_service.inc:fw_wifi_net_slot`→`skw_wifi_amsdu.h:skw_amsdu_receive`→`skw_wifi_data.h:skw_data_inspect`；交付回调为`skw_netdev.c:skw_netdev_rx`。

日志`meta=6a04 flags=76 offset=74 index=1 seq=7 lastbyte=01 wire=120 length=98 parsed=0`在这版源码中的含义：

- flags以`%02x`输出，为0x76；`0x76 & 0x08 == 0`，故`v.amsdu=false`。first/last位虽均置位，不改变非聚合分支选择；index=1/seq=7也不自动把帧变成聚合子帧。
- meta为0x6a04，TID=6、multicast=false、instance=0、peer=0，相关元数据准入位通过。不能从seq=7推知PN，更不能推知已收过同一包。
- parsed=0是失败后的第二次inspect成功；inspect验证描述符、界限、地址、非零PN等，但**不比较已提交PN下限/pending状态**，因此“parsed成功”与“顺序拒绝”并不矛盾。在单owner及原始slot未变的正常调用约束下，它排除首次inspect失败分支。
- `offset=74`是描述符字段，不是直接Ethernet偏移。PN_REUSE模式下Ethernet偏移=74-52=22，22+98=120；非复用模式应为26，26+98>120而无法inspect成功。由此可推导此快照使用复用模式（仍建议直接采集pn_reuse避免依赖推导），实际PN取d[12..15]四字节。

## 当前样本的两种剩余分支

| 条件 | 位置/效果 | 缺失证据 |
|---|---|---|
| `v.pn <= replay.unicast[6]` | 最前方floor检查返回-EACCES；不提交该帧 | incoming PN、当时floor |
| `pending[0][6].active && v.pn < pending[0][6].pn`，且已经通过floor检查 | 非A-MSDU分支返回-EACCES；保留pending | pending active/PN及incoming PN |

真实skw_netdev_rx只会返回0、-EMSGSIZE、-ENOTCONN、-ENOSPC，不返回-EACCES，因此在固定实现下不是下游交付返回-13。抽象的skw_amsdu_receive函数允许任意deliver回调返回错误，不能把这个排除结论泛化到其他回调。

其他-EACCES分支确实存在：inspect的meta/地址/PN合法性、真正A-MSDU的pending PN/sequence不匹配、相对index重复bitmap；但根据parsed=0及amsdu=false，不是本样本正常调用路径。真正A-MSDU内的超时、orphan、index/first/last矛盾通常返回-EPROTO，也不能仅凭-13认定丢子帧。

额外静态事实：250ms pending清理在非A-MSDU分支**之后**。因此第二种拒绝也可能遇到超过250ms的pending；当前日志没pending年龄，不能宣称本次由这个条件导致。暂不建议放松PN或清空状态：不同pending/已提交PN之间有安全顺序语义，修复需完整前驱序列证据。

## 两份现场证据不应合并成同一轮异常

- cxx-eh recovery gateway：窗口前complete/subframes/rejected=0/0/0，后1/2/1；窗口内有本条-13日志，ping5/5。
- neon-file64 gateway：窗口前0/0/1，后1/2/1；**窗口内rejected没有增加，也没有-13日志**。其1次拒绝发生在起始快照以前；此文件不能证明是同一返回码或同一条件。
- 名为`WIFI AMSDU ... rejected`的rejected实际变量是`g_wifi_ip_rejects`，统计所有`skw_amsdu_receive`的非零返回（排除-EPROTONOSUPPORT），含非A-MSDU/解析/交付错误；不是“聚合帧拒绝数”专用计数。
- complete/subframes在完整组提交floor之后、调用deliver之前增加；本身不证明每个子帧成功交付，unsupported子帧也计入subframes。当前网关5/5证明有限请求得到回复，不证明零接收异常，更不能将拒绝对象指定为这些ICMP回复。

## 最小下一次采集建议（本交付未实施）

保留统计不变。在真实接收single-owner路径、任何state修改之前，使用固定容量内存环记录少量前驱与失败记录，避免每包同步串口打印。记录：单调时间/递增接收序号、实际n/wire/pn_reuse、instance/peer/TID/mc、incoming PN、提交floor、pending active/PN/sequence/bitmap/first_index/last_seen/last_index/started_ms、解析ret、明确branch reason、交付ret。建议容量32、最多保留2个失败窗口、溢出计数；保留上一成功提交事件便于区分重复/乱序/状态处理。

为真实回放还需失败slot以及相关前驱完整原始字节、确切长度和状态初值；若只允许更小证据，描述符+必要Ethernet头可定位分支，但不能重建payload/证明网络包身份。采用定长有上限捕获（现有slot最大1536），记录截断标记。原始网络包可能含业务内容，留本地受控证据并按既有脱敏规则导出；不要把未知payload用0填充后称为现场回放。需关联实际镜像哈希、源码哈希、会话/密钥代次（只记代次不记密钥）。

## 已执行的软件验证

`run.py`锁定并校验inputs.json，编译运行原tests/wifi/test_amsdu.c和本目录replay_synthetic.c，真实头文件直接来自只读正式源码，无替代解析器。每个子进程15秒上限。合成用例覆盖两种剩余分支、pending超过250ms时非聚合路径、完整2子帧后非聚合floor拒绝；PN/地址/载荷全为明确合成值，**不是本次现场帧重建**。原始输出、命令和退出码在host-results.json和编号stdout/stderr，输出哈希在hashes.json。
