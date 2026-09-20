# k7storage 输出验收候选

仅本地主机解析；未执行设备、SDK、USB或COM8操作。k7storage_main.frozen.c 保存本任务开始时的正式源码原始字节，input.json 保存路径/长度/SHA256。若C代理后来修改list错误处理或有界枚举，应先核对新源码输出合同，再出新的源码绑定版本；不能让新固件冒用本次旧源码hash。

## 输入和用法

需要四份按顺序采集的原始串口片段：启动前 `k7storage list`、`k7storage start`、启动后 `k7storage list`、`k7storage read /dev/sdX`。每份以该命令的回显开始、以最终 `nsh>` 提示符结束；支持前缀nsh>的回显、CRLF及ANSI CSI。采集器应分别保留各阶段，不能手工删掉错误行再作为成功证据。包含其他命令/多轮调用的日志应拒绝，而非自动挑出一个看起来成功的摘要。

```powershell
python -B accept_storage.py --before before.bin --start start.bin --after after.bin --read read.bin --node /dev/sda --scope target --identity identity.json --output acceptance.json
python -B test_acceptance.py
```

退出0表示输出合同与外部声明绑定检查满足；1表示拒绝。`--scope` 必须显式 synthetic 或 target。synthetic目录是37组测试所用的完整合成基准与身份文件，不能作为真机模板直接标成target运行。

外部identity.json必须由主会话核对身份和构建后提供，字段如下（synthetic/identity.json展示结构）：

- scope=target、evidence_origin=device-capture、非空run_id、reviewer、identity_reviewed=true。
- node为本次指定节点，vid/pid是4位小写十六进制；firmware_sha256为实际加载镜像hash，source_sha256严格等于input.json中的冻结源码hash。
- ordered_phases必须是before/start/after/read；capture_sha256字典绑定这四份输入原始字节的SHA256。
- enumeration_evidence和build_evidence各有path、sha256；path相对身份文件目录或绝对路径，所引本地文件必须存在、非空且hash匹配。前者由主会话证明此新节点确属本次指定USB设备，后者关联冻结源码与实际加载固件。解析器只检查绑定，不理解任意格式的外部证据内容。

## 验收合同

阶段结果必须完整且唯一，command正确、result=0、mount_attempted=0。前后list的node/count匹配且无重复；指定节点先前不存在，之后是唯一新增节点，旧节点未消失，避免并发设备变化造成歧义。start没有额外USB_STORAGE记录。read只有一个summary及一个final，要求目标node、合法扇区尺寸、正容量不超过READ CAPACITY10支持范围、readonly=1/lba=0/reads=2/repeated=1及8位CRC32。boot_signature/exfat_oem只验布尔格式，**不要求FAT签名**，不由此宣称可挂载。

冻结源码在两次read各返回1并memcmp一致后才输出repeated=1；该摘要早于close_blockdriver。因此必须再看到最终command=read result=0和终端完成，close失败不能误报通过。本协议不输出两份扇区原始字节，解析器不能独立复算CRC或memcmp；它验收绑定源码所声明的合同。

缺失/重复记录、错计数、额外字段或协议记录、截断USB标志、混入旧调用、错误返回、常见fault/abort/panic/error诊断和无效UTF8均拒绝。任意无结构串口背景文字不等于故障，但可能影响真实采集完整性；对串口丢字且恰好仍构成另一条合法文本，协议本身没有可验证校验链。

## 边界与测试

没有nonce/boot ID，所以无法区别同样内容的旧日志重放。身份文件中的阶段顺序和run_id是外部审阅声明，不是解析器读出的启动事实。输出始终明确 physical_identity_independently_proven=false、boot_freshness_independently_proven=false、target_test_performed_by_parser=false；passed不能改写成独立物理身份认证。

37组合成验收样例和2次CLI运行通过，test-results.json保留每组输入文本/身份声明/预期/实际错误及CLI原始输出。覆盖缺终结、缺提示符、关闭失败、只读/两读/一致性/尺寸错误、重复/多轮/截断、非新节点、模糊新增、fault和身份hash失配；synthetic输入不能以target作用域通过。没有真实串口验收结果。后续主会话需对实际固件与新源码hash完成审查后，提供完整原始阶段和外部身份记录。
