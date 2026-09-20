"""Seed the user-requested audio worktree from uncommitted formal inputs."""
from pathlib import Path
import hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parents[1]
D=R.parent/'worktrees/VelaVision-audio-noise'
assert subprocess.check_output(['git','branch','--show-current'],cwd=D,text=True).strip()=='audio-noise-20260911'
assert not (D/'audio-input-manifest.json').exists()
paths=[]
for folder in ['app/k7sound','app/k7audio','app/k7audiohw']:
 paths.extend(p for p in (R/folder).rglob('*') if p.is_file())
paths.extend([R/'docs/音频零样本定位_20260911.md',R/'evidence/audio-rx2-20260910/runtime-results.json'])
paths.extend((R/'evidence/audio-rx2-20260910').glob('k7sound-loopback-*.bin'))
rows=[]
for p in paths:
 rel=p.relative_to(R);target=D/rel
 assert not target.exists(),target
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 digest=hashlib.sha256(p.read_bytes()).hexdigest();assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
 rows.append(dict(path=rel.as_posix(),sha256=digest))
(D/'audio-input-manifest.json').write_text(json.dumps(dict(source=str(R),source_branch='dev-ai-contest-2026',source_state='uncommitted working-tree snapshot; not represented by HEAD',files=rows),indent=2))
(D/'AGENTS.md').write_text('''# 音频杂声独立分支

此 worktree 为 audio-noise-20260911，仅用于音频候选和主机验证。
实际输入来自 audio-input-manifest.json 的主项目未提交源码快照；HEAD仍是原始脚手架，禁止声称源码已提交。
允许修改 app/k7sound、work-in-progress/audio-noise、本目录的音频交接文档。
不访问 COM8、板子、蓝牙、SDK/Ubuntu、U盘或执行机构，不刷写，不提交或推送，不改主项目。
不复制凭据或模型，不修改本 worktree 脚手架 logs 示例，不运行中央采集器。
结果由主会话评审并在语音主线允许的时机统一上板。实测、编译与模拟必须区分。
主线在 E:/openvela/VelaVision，AI日志统一归属该项目 logs/maomaojiang01。
''',encoding='utf-8')
(D/'音频分支接续.md').write_text('''# 音频分支接续

主线优先纯板端 VoiceLink 配网；音频分支只做候选，不占用设备。
当前复制的录放音源码包含默认/编号/RX2/guard静音诊断。
已验收证据为RX2两种模式对照：8062/4061us，零字194/131，有效不同编号62/125。
guard镜像已在RAM启动，但尚未运行guard静音实验，不能声称边界问题已解决。
后续同源路由候选位于主项目 work-in-progress/parallel-neon-probe-medium/audio-rx2-path-v1，使用前固定哈希。
本目录是独立Git worktree；复制源码保持未提交状态，未向远程提交。
''',encoding='utf-8')
print('Audio branch seeded:',len(rows),'files; no commit or device access')
