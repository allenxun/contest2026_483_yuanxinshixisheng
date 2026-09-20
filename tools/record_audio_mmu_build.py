"""Record build checkpoint only; never claim a completed RAM load."""
from pathlib import Path
import datetime
import json
R=Path(__file__).resolve().parents[1]
p=R/'project-manifest.json'
m=json.loads(p.read_text(encoding='utf-8'))
m['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
m['pending_firmware']={'revision':'audio-mmu-20260910','status':'RAM_LOADING',
 'sha256':'886137227992f07ff1a32ff3662d4de2c799d1baa6fa15238bbba75cfbed2638',
 'build_verified':True,'hardware_tested':False}
m['current_device']={'state':'U-Boot RAM load in progress; wireless offline',
 'last_loaded_revision':'audio-marker-20260910','audio_noise_fixed':False}
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=R/'README.md';s=p.read_text(encoding='utf-8')
a=s.index('**夜间接续：**');b=s.index('\n',a)
s=s[:a]+'**2026-09-11 接续：**编号静音回环确认数据在推进，但仍有周期性零样本；RX 路由单变量试验未消除。只读 MMU 探针已编译、通过 ELF 审计与当前地址绑定，正在独立 RAM 加载，无线暂离线。尚未宣称杂声修复或语音配网完成。详见 [夜间交付](docs/夜间工作交付_20260911.md)。'+s[b:]
p.write_text(s,encoding='utf-8')
with (R/'docs/代码日志对应表.md').open('a',encoding='utf-8') as f:
 f.write('\n2026-09-11 MMU 诊断接入：app/k7sound 新增只读 CPU0 MMU worker 和有界页表解析，tools/observe_audio_mmu.py 绑定当前 ELF 与 SDK 哈希；audio-mmu-20260910 编译、ELF 异常表/布局/二进制核对通过。构建证据 evidence/build/audio-mmu-20260910，SDK 固定输入 evidence/audio-mmu-input-20260911。此记录时 RAM 加载中，尚无真机 MMU 结果；无线离线。首轮验证先于审计文件生成而失败，审计生成后验证通过。没有刷写、播放或启动执行机构。\n')
print('MMU build/loading checkpoint recorded')
