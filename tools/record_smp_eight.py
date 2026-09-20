"""Record actual eight-core evidence without replacing failed attempts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/smp-eight-20260910'
passed = json.loads((E / 'diagnostic-attempt04.json').read_text())
reset = json.loads((E / 'software-reset.json').read_text())
assert passed['passed'] and reset['uboot_prompt']
out = E / 'cpu-acceptance.json'
assert not out.exists()
report = dict(
    revision=E.name, diagnostic='diagnostic-attempt04.json',
    firmware_sha256=hashlib.sha256((R / 'artifacts' / E.name / 'nuttx.bin').read_bytes()).hexdigest(),
    cpu_count=8, a53_count=4, a72_count=4, samples_per_cpu=10000,
    shared_counter=80000, mismatch=0, sleep_errors=0,
    software_reset_passed=True, peripheral_smp_tested=False,
    long_term_tested=False, emmc_written=False,
    failed_attempts=['diagnostic.json', 'diagnostic-attempt02.json', 'diagnostic-attempt03.json'],
    failure_cause='Host scripts used 1800000 baud; immutable target config specifies 1500000. Corrected rate passed without reloading firmware.',
    prevention='New console_baud helper checks immutable config hash and derives the rate; all four diagnostic build configs returned 1500000. No additional board test was run for this host-only helper change.',
)
out.write_text(json.dumps(report, indent=2) + '\n')
m = json.loads((R / 'project-manifest.json').read_text(encoding='utf-8-sig'))
m['updated_at'] = datetime.now(timezone.utc).isoformat()
m['current_device'] = dict(state='U-Boot RAM recovery of emmc-vfs in progress after eight-core diagnostic and software reset passed', emmc_written=False, wifi_connected=False)
m['pending_firmware'] = dict(revision='emmc-vfs-20260910', state='recovering known verified single-core image; radio not started yet')
m['smp_diagnostics']['eight_core'] = 'evidence/smp-eight-20260910/cpu-acceptance.json'
m['cpu_plan'].update(smp_verified=True, verified_diagnostic_cpus=8, peripheral_smp_verified=False)
(R / 'project-manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
p = R / 'README.md'
s = p.read_text(encoding='utf-8-sig')
start = s.index('**当前板端')
end = s.index('\n\n', start)
s = s[:start] + '**当前板端正在恢复单核无线/eMMC镜像。** 独立 SMP 两核、四核、跨簇五核及八核诊断均已真机通过，软件复位已验证。八核每核10000次采样、零核编号错位、共享计数80000；见 `evidence/smp-eight-20260910/cpu-acceptance.json`。尚未完成外设多核并发和八核长稳验收。' + s[end:]
s = s.replace('当前双核诊断期间无线暂停', '当前恢复镜像期间无线暂停')
s = s.replace('最新独立诊断已验证两颗A53，未启用全部4GiB/八核', '最新独立诊断已验证四颗A53加四颗A72；未验证全部4GiB或八核外设并发')
p.write_text(s, encoding='utf-8')
p = R / 'docs/八核CPU接入与任务分配_20260910.md'
s = p.read_text(encoding='utf-8-sig')
start = s.index('2026-09-10 最新增量')
end = s.index('\n\n', start)
s = s[:start] + '''2026-09-10 最新增量：独立两核、四核、跨簇五核、八核均已真机通过固定核线程、共享原子计数和定时休眠诊断。八核4颗A53/4颗A72，各10000采样、零核编号错位、零休眠错误，共享计数80000，MPIDR与GIC目标映射符合预期；随后软件复位返回U-Boot。证据：`evidence/smp-eight-20260910/cpu-acceptance.json`。当前恢复单核无线/eMMC基线，外设SMP、长稳、频率性能及热稳定性仍未验收。

失败记录保留：首个两核最小配置缺BOARDCTL_RESET，后续修正版已补齐并验证；八核前三次主机脚本错误使用1800000波特率，命令乱码未执行。改为产物.config规定的1500000后，同一次启动直接通过。新增主机工具从已校验哈希的固件配置读取波特率，避免数字批量替换污染串口参数。''' + s[end:]
s = s.replace('本轮仅完成拓扑和配置核对、负载规划，未开启SMP或声称八核启动成功。', '上述最初规划之后已完成独立八核诊断；外设集成仍按第4、5步继续。')
p.write_text(s, encoding='utf-8')
p = R / 'docs/代码日志对应表.md'
with p.open('a', encoding='utf-8') as f:
    f.write('\n2026-09-10 SMP增量：app/k7smp、ARM64 CPU启动返回值及RK3576 MPIDR映射、独立2/4/5/8核配置均有独立构建和真机证据。八核最终证据见 evidence/smp-eight-20260910/cpu-acceptance.json；三次主机串口参数错误和首版缺reboot均保留。不将单核无线或主机语音结果计算为八核外设验收。归属当前主会话，日志须刷新后以manifest与官方校验为准。\n')
print('Recorded eight-core acceptance and current recovery state')
