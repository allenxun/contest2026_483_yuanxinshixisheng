"""Create source/version/log cross references without claiming nonexistent commits."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    inventory=[]
    for folder in ('app','board','port','patches','host','mcu','frontend','legacy','work-in-progress','skills','tools'):
        for p in sorted((ROOT/folder).rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts: continue
            inventory.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    source_id=hashlib.sha256(''.join(f"{f['path']}\0{f['sha256']}\n" for f in inventory).encode()).hexdigest()
    dump(ROOT/'evidence/source-files.json',dict(algorithm='sha256',source_set_sha256=source_id,files=inventory))
    manifest=json.loads((ROOT/'logs/maomaojiang01/manifest.json').read_text(encoding='utf-8'))
    groups=[
        ('BSP / USB / 平台','board/kickpi_k7; port/new/nuttx; port/tracked/nuttx',['rk3576_boot.c','usbhost_xhci_rk3576','rk3576_lowputc','kickpi_k7']),
        ('人脸 / 姿态 / 三视角拍照','app/k7host; host/vision',['k7host','k7_pose','photo_controller','photo-direction']),
        ('云台 / STM32','app/gimbal; mcu/stm32-v1.3',['gimbal','stm32','user_bluetooth.c','bsp_pwm']),
        ('NPU','app/k7npu',['k7npu','rawrepeat','rk3576_npu']),
        ('Wi-Fi / BLE / 前端','app/k7radio; frontend; work-in-progress/wifi-link',['k7radio','prov_service','vela-provision','skw_wifi']),
        ('旧 PC / 仪器模型','legacy/pc-delivery',['pc_demo','device_model','仪器','rknn']),
        ('统一构建 / 日志','tools; logs/maomaojiang01',['velavision_integrated','统一','validate-log.py','export_project_logs']),
    ]
    events={s['session_id']:[json.loads(line) for line in (ROOT/s['file_path']).read_text(encoding='utf-8').splitlines()] for s in manifest['sessions']}
    serialized={sid:[json.dumps(e,ensure_ascii=False).lower() for e in rows] for sid,rows in events.items()}
    mappings=[]
    for name, paths, needles in groups:
        matches=[]
        for s in manifest['sessions']:
            indices=[i for i,text in enumerate(serialized[s['session_id']]) if any(n.lower() in text for n in needles)]
            if indices:
                rows=events[s['session_id']]
                matches.append(dict(session_id=s['session_id'],file_path=s['file_path'],matching_events=len(indices),
                                    first_seq=rows[indices[0]]['seq'],last_seq=rows[indices[-1]]['seq'],
                                    example_anchors=[dict(seq=rows[i]['seq'],ts=rows[i]['ts'],source_line=rows[i]['metadata']['source_line']) for i in indices[:3]]))
        mappings.append(dict(module=name,source_locations=paths,search_terms=needles,log_references=matches))
    dump(ROOT/'evidence/code-log-map.json',dict(source_set_sha256=source_id,modules=mappings,
         interpretation='Actual text/path references and source snapshot hashes; not proof of per-event authorship or historical commits.'))
    old=manifest['sessions'][0]; current=manifest['sessions'][1]
    report=['# 代码、日志与验证对应表\n',
            '统一仓库：`E:\\openvela\\VelaVision`；日志归属：`logs/maomaojiang01/`。\n',
            '## 日志覆盖\n',
            f"- 旧主会话：{old['event_count']} 条，{old['started_at']} 至 {old['last_event_at']}。\n",
            f"- 当前主会话：{current['event_count']} 条，{current['started_at']} 至 {current['last_event_at']}。\n",
            '- 两个会话各自 seq 从 0 连续递增，不串改日期或把两个会话改成一个会话。\n',
            '- 当前快照不含导出之后的新增消息；运行更新脚本可刷新。未重复合并子任务继承历史，未恢复内部推理。\n',
            '\n## 代码到日志索引\n',
            '下表是对真实日志中的路径/名称引用检索，不是补造逐次 Git 提交或宣称每条引用都代表代码修改。详细锚点在 `evidence/code-log-map.json`。\n',
            '| 模块 | 源码位置 | 旧会话引用数 | 当前会话引用数 |\n| --- | --- | ---: | ---: |\n']
    for m in mappings:
        counts={x['session_id']:x['matching_events'] for x in m['log_references']}
        report.append(f"| {m['module']} | `{m['source_locations']}` | {counts.get(old['session_id'],0)} | {counts.get(current['session_id'],0)} |\n")
    report+=['\n## 版本与验证证据\n',
             '- `evidence/source-files.json`：本仓源码/模型/脚本的逐文件 SHA-256，识别当前实际代码。\n',
             '- `evidence/sdk-inventory.json`：来自 VM 的文件路径、SDK Git 基线及最初取回哈希。\n',
             '- `evidence/accepted-source-comparison.json`：80 项旧验收源码与统一目录全部一致。\n',
             '- `evidence/build/integrated-build.json`：同一 ELF 中四个应用入口、配置和固件哈希；仅编译验证。\n',
             '- `evidence/log-snapshots.json`：两个原始会话快照哈希/截止时间、事件数量、脱敏与排除项。\n',
             '- 每条 JSONL 的 `metadata.source_line` 与 `source_record_sha256`：定位原始会话记录；`seq` 定位交付日志。\n',
             '- `evidence/official-log-validation.json` 与 `.txt`：未修改官方校验器的实际运行结果。\n',
             '\n历史没有逐次提交，不能证明不存在的 commit 对应。今后从此统一仓库产生代码提交，并同步同仓日志和版本清单。文件/格式核对通过，不代替联合硬件验收。\n']
    (ROOT/'docs/代码日志对应表.md').write_text(''.join(report),encoding='utf-8')
    build=json.loads((ROOT/'evidence/build/integrated-build.json').read_text(encoding='utf-8'))
    dump(ROOT/'project-manifest.json',dict(version='VelaVision-integrated-20260909.1',
         updated_at=datetime.now(timezone.utc).isoformat(),source_set_sha256=source_id,
         source_file_count=len(inventory),sdk=json.loads((ROOT/'evidence/sdk-inventory.json').read_text(encoding='utf-8'))['repositories'],
         integrated_build=build,logs=[{k:s[k] for k in ('session_id','file_path','event_count','sha256')} for s in manifest['sessions']],
         official_format_validation='evidence/official-log-validation.json',hardware_joint_validation=False,remote_submission=False))
    print(json.dumps(dict(source_files=len(inventory),source_set_sha256=source_id,sessions=len(manifest['sessions']),
                          log_events=sum(s['event_count'] for s in manifest['sessions']),modules=len(mappings)),ensure_ascii=False))

if __name__=='__main__':main()
