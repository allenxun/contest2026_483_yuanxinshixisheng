#!/usr/bin/env python3
"""Render compact progress snapshots. Never reads OpenCode conversations or credentials."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / 'panels'
PACKAGES = {
 'A': ('工程基础与公共契约', 'A-foundation.md', 'Java/Python 工程、14 表迁移、公共契约、认证/幂等/媒体基础、异步任务运行时'),
 'B': ('身份、设备与通知', 'B-identity-devices.md', '身份与查看授权、设备绑定、通知目标与异常推送'),
 'C': ('方案执行与次数记录', 'C-care.md', '方案查询、执行准入、暂停/恢复/结束、次数去重与累计'),
 'D': ('测肤与方案生成', 'D-assessments.md', '测肤 API、图片处理、人脸归档、算法与大模型异步任务'),
 'E': ('全程验收与联调', 'E-acceptance.md', '94 场景追踪、27 API 回链、基础验收、并行模块验收及端到端联调'),
}
PHASES = {'running':'实施中', 'waiting_dependency':'等待依赖', 'waiting_for_A_acceptance':'等待 A 验收通过', 'completed':'已提交完成报告，待协调确认', 'complete':'已提交完成报告，待协调确认', 'failed':'执行失败', 'blocked':'存在阻塞', 'idle':'空闲，待核对交付', 'accepted':'验收通过'}
def read(path):
 try: return json.loads(path.read_text())
 except FileNotFoundError: return {}
 except (ValueError, OSError): return {'phase':'状态读取失败，请巡检核对'}
def fmt(value):
 if value is None or value == '' or value == []: return '尚无记录'
 if isinstance(value, (dict,list)): value=json.dumps(value,ensure_ascii=False)
 return str(value).replace('|','\\|').replace('\n',' / ')

def main():
 registry=read(ROOT/'.coordination/registry.json')
 now=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S +08:00')
 OUT.mkdir(exist_ok=True)
 rows=[]
 for key,(title,card,scope) in PACKAGES.items():
  registered=registry.get(key,{})
  status=read(ROOT/f'.coordination/{key}/status.json')
  phase=status.get('phase') or registered.get('status') or '尚无状态'
  label=PHASES.get(phase,phase)
  waiting=phase=='waiting_for_A_acceptance'
  blocker=status.get('blocker') or ('A 尚未完成验收与集成，按计划等待' if waiting else '最近状态未报告阻塞；不代表已完成验收')
  next_action=status.get('nextAction',status.get('next_action')) or ('A 验收并合入 dev 后，创建独立任务和工作树' if waiting else '由监督任务补充下一步')
  tests=status.get('tests')
  lines=[f'# {key} · {title}', '', '[返回总览](README.md) · [任务书](../'+card+')', '', f'> 面板生成时间：{now}。这是状态快照，不是实时日志；以“最近进展时间”判断信息新旧。', '', '## 当前进度', '', '| 项目 | 当前信息 |','|---|---|',f'| 阶段 | {fmt(label)} |',f'| 最近进展时间 | {fmt(status.get("lastProgressAt",status.get("last_progress_at")))} |',f'| 最近报告提交（不等于验收通过） | {fmt(status.get("commit"))} |',f'| 分支 | {fmt(status.get("branch",registered.get("branch")))} |',f'| 阻塞 / 等待条件 | {fmt(blocker)} |',f'| 下一步 | {fmt(next_action)} |', '', '## 本包范围','',scope,'','## 已完成与验收证据','']
  completed=status.get('completedItems',status.get('completed_items',[]))
  if completed:
   lines += ['- '+fmt(x) for x in completed]
  elif waiting:
   lines += ['尚未启动实施。']
  else:
   lines += ['以以下已报告测试和交付记录为准；尚未报告的子任务不推断为完成。']
  if isinstance(tests,list):
   lines += ['', '| 检查 | 退出码 | 通过 | 失败 | 跳过 | 待依赖 |','|---|---|---|---|---|---|']
   for t in tests:
    if isinstance(t,dict): lines += ['| '+' | '.join(fmt(t.get(x)) for x in ['command','exitCode','passed','failed','skipped','dependencyPending'])+' |']
  elif tests: lines += ['',fmt(tests)]
  else: lines += ['', '测试结果：尚未报告。']
  lines += ['', '业务验收结论仅由 E 的验收证据和总协调确认；框架自检通过不代表业务场景通过。', '', '## 更新方式', '', '监督任务写入本项目 `.coordination/'+key+'/status.json` 的精简状态；总协调刷新本面板。允许补充 `completedItems` 数组，仅填写已验证事项。面板不读取会话全文、审批密码或业务源码。','']
  (OUT/f'{key}.md').write_text('\n'.join(lines))
  rows.append(f'| [{key} · {title}]({key}.md) | {fmt(label)} | {fmt(blocker)} |')
 (OUT/'README.md').write_text('\n'.join(['# MVP 任务进度总览','',f'最近刷新：{now}','', '执行顺序：A 完成并通过 E 验收 → 集成 dev → B/C/D 并行 → E 持续验收。','', '不使用估算百分比；“实施中”“等待依赖”和“验收通过”分别展示，避免把自检当交付。','', '| 工作包 | 当前阶段 | 阻塞 / 等待条件 |','|---|---|---|',*rows,'','## 刷新规则','','总协调每次半小时巡检后，以及收到完成或阻塞报告时，运行：','','```bash','python3 backend/doc/tasks/update-panels.py','```','','脚本只读取 `.coordination/registry.json` 和各包 `status.json`，不会调用模型或 OpenCode。巡检依赖电脑与任务正常运行；时间未更新时应视为旧快照。','','首次面板纳入 Git；后续快照按里程碑提交，避免每次巡检产生一个提交。托管文档站点是发布快照，不会自动同步这些本地任务面板。','']))

if __name__=='__main__': main()
