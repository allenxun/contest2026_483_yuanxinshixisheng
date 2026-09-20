# Storage acceptance v2

本版本只更新源码绑定与解析回归证据，未更改解析器逻辑、C代理候选、正式源码或设备。冻结输入为 parallel-neon-probe-medium/storage-probe-review-v1/candidate.c，字节与SHA256见input.json和delivery.json；旧v1交付保留原样。

## 候选契约核对

仅list_usb_nodes实现改变，成功输出仍是零到多条node、一条nodes计数、最后main打印的command=list result=0 mount_attempted=0。读取、readonly/reads/repeated摘要和close后的最终result合同保持不变。

候选在每次readdir前清errno，NULL且errno非零保存负错误；closedir失败在此前成功时记录负errno或-EIO；两者通过return rc到main最终result。因此即便出现nodes=0或已输出部分node，解析器也必须看最后result，不能接受错误路径。

visited统计所有目录条目，包括不匹配sdX的条目。循环顶部visited==256直接-E2BIG，因此最多调用readdir成功取得256条后即失败；**恰256条也保守失败，即使下一次将EOF**，最多255条再EOF才可正常成功。该上限不在输出中直接报告，解析器不能数node条目来替代visited，而依赖绑定源码及非零最终result拒绝。主机原结果中1000条目录模拟在256条停止，输出node=/dev/sda、nodes=1、result=-7；本版本确认该看似完整节点列表不会通过。

## 使用与外部证据

```powershell
python -B accept_storage.py --before before.bin --start start.bin --after after.bin --read read.bin --node /dev/sda --scope target --identity identity.json --output acceptance.json
python -B freeze.py
```

四份原始阶段必须有正确命令回显、唯一成功尾记录和结束nsh>提示符；前后节点差集要求指定节点是唯一新增节点。read必须readonly=1、reads=2、repeated=1，且最终result=0（含close结果）。错误/重复/截断/混入多轮/外部哈希失配均拒绝。

identity.json须明确scope=target、evidence_origin=device-capture、reviewer/identity_reviewed=true、run_id、ordered_phases=[before,start,after,read]，绑定四份capture_sha256、node、VID/PID、实际firmware_sha256及本版本source_sha256；enumeration_evidence/build_evidence各含本地path和sha256，必须存在且一致。完整字段示例在synthetic/identity.json，但该目录仅模拟，不能改标签就作为真实USB身份。

v1的source hash a3a13309f71306a16490a3a2410138b2219638cf76041f2826fea88a5a04d9a4在v2明确拒绝。主会话正式集成后须核对正式源码字节等于本版本候选；若再次变化，不能冒用这个绑定。

## 验证和边界

41案例+2CLI检查全部通过。保留v1的37案例，新增3个C候选host输出片段（open失败、read/close失败、256上限）和旧源码绑定拒绝。candidate-host.stdout.frozen是C代理真实主机mock执行原输出，原样保留；测试给片段添加的命令回显/提示符与其余阶段明确为合成。没有把host mock当作真机，没有重跑C测试或重复C源码实现审查。

没有nonce/boot ID，故解析器无法独立证明日志新鲜性或物理USB身份，也不能从read摘要独立复算两份扇区字节。passed仅代表输出合同和外部已审阅证据的绑定检查通过；相关independently_proven字段始终false。目标编译/加载/实际身份与采集由主会话负责。
