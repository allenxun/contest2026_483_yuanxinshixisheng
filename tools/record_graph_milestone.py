"""Update traceability with graph success, cold EH failure and corrected link gate."""
import json
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'docs/原生llama编译与NEON验收_20260910.md';s=p.read_text(encoding='utf-8')
s=s.replace('当前板端是 `neon-file64-20260910`；`cxx-locale-20260910` 及单独链接的 llama ELF 均未上板。','最新已验收 `graph-core-20260910` 的零权重真实 ggml 图；当前设备切换状态见 project-manifest。完整 llama ELF 尚未上板。')
old='强制保留模型加载、context创建、decode、tokenize和checked池创建入口，五个符号均存在，链接退出0。证据 `evidence/llama-native-link-20260910/`。'
new='首版门禁误拼checked池创建符号，并把未定义U符号算作存在；不能据此宣称五个入口均定义。原结果保留。修正为要求T/t定义后，v2模型加载、context创建、decode、tokenize及checked池创建/销毁/预算共七入口全部通过，链接退出0；证据 `evidence/llama-native-link-20260910-v2/`，ELF SHA256 c9e2737ce1ab14d696272602954e7402d577accc7def133be294a70dc54218a9。'
# Actual v2 digest is taken from the frozen report, not the narrative template.
r=json.loads((R/'evidence/llama-native-link-20260910-v2/result.json').read_text())
new=new.replace('c9e2737ce1ab14d696272602954e7402d577accc7def133be294a70dc54218a9','c9e2737ce1ab14d696272602954067cf26f12fb04cea221e25e059c2aa62200b')
assert old in s;s=s.replace(old,new)
s+='''

## 后续真实图和异常对照（本轮新增）

`graph-core-20260910` 实际加载 SHA256 6b68dbff8afcd866f8d6e806885f209bd71dcf6e8cd8379b3bd40d768d8ea27b，驻留6443008字节。独立8MiB门禁核对PT_LOAD、堆起点和保留区；原6MiB门禁保留。2/4配置线程各完成64×64乘法4096项，checksum=-10、错误0；辅助线程1/1和3/3创建/退出，资源计数归零。两组总观察约0.828秒不是token性能。未采集物理CPU分布，不能称四核推理。证据 evidence/graph-core-20260910/runtime.json。

同镜像BLE真实凭据→WPA2/DHCP/IP、30秒保持和网关5/5通过。普通堆总125677568字节，快照free125595968；拒绝累计1→1，成功交付1组2子帧。历史AMSDU rejected标签实际覆盖所有数据接收拒绝；另一次flags=0x76样本是非A-MSDU，PN顺序拒绝两个分支仍缺现场PN/floor/pending证据。不要把标签等同于已定位A-MSDU根因。

`cxx-eh-20260910` 的双worker首次异常在0.047秒内异常终止，无worker结果和joined完成。确切返回PC核对后，abort位于uw_init_context_1，不能误标为Phase2。现有single-thread libgcc存在FDE列表初始化发布和register-size表初始化两处可行并发窗口，但未证明现场命中哪一支。libc++abi使用pthread TLS，不能归为单全局eh_globals。失败原始证据位于 evidence/cxx-eh-20260910/cold/，随后neon基线无线已恢复再切换graph。

新增独立 `eh-control-20260910`，只做新启动CPU5单worker一次与另一次新启动main完整预热后CPU4/5各一次。273FDE、首初始化注册、实际TU宏及源码哈希已核对；测试结果以 evidence/eh-control-20260910/ 为准。预热成功也不是通用并发安全修复。

app/k7agent/tool_api已迁入有界JSON类型化请求候选并通过真实ARM64编译；未注册设备后端或实现自然语言推理。模型池审计发现权重、KV、scheduler、scratch、output与元数据分属多条分配路径，不能只改一个malloc或ggml_init。普通模型文件、同句柄校验接入及完整分配预算仍是后续门禁。
'''
p.write_text(s,encoding='utf-8')
for name,addition in [
 ('docs/代码日志对应表.md','新增app/k7eh与app/k7ehcontrol保存冷并发异常失败和独立对照；app/k7graph真实2/4线程零权重图与无线回归通过；app/k7agent/tool_api仅目标编译通过。链接v1拼错符号门禁已在v2纠正，原失败/错误记录保留。tools/observe_graph_core.py、observe_eh_control.py、record_graph_acceptance.py对应本主会话，最终日志须重新官方校验。'),
 ('docs/并行开发责任与验收矩阵_20260910.md','第三轮layout/graph/tool-json已交付，graph经主会话目标编译和真机通过，tool-json仅目标编译。后续A负责冷失败静态分析、控制ELF审查及threaded-unwind计划；B负责model-arena-plan/buft；C负责接收PN拒绝审计/诊断候选。全部隔离目录；只有主会话接入SDK和COM8，候选通过不等于目标集成。'),
 ('docs/最终目标进度与下一阶段_20260910.md','最新增量：CPU真实ggml 2/4线程零权重图已通过，无线回归通过；完整模型未加载。首次双线程C++异常失败使线程运行库成为明确阻塞，正在进行single/warm1独立对照。模型池和PN拒绝诊断由代理并行准备，尚未上板。')]:
 p=R/name
 with p.open('a',encoding='utf-8') as f:f.write('\n\n2026-09-10追加：'+addition+'\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
m['current_device']=dict(running_revision=None,state='RAM loading eh-control-20260910 after verified graph baseline',wifi_connected=False,ble_service_running=False,evidence_directory='evidence/eh-control-20260910')
m['updated_at']=datetime.now(timezone.utc).isoformat();p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Milestone, corrected link gate and current loading state recorded')
