"""Prepare isolated GPT build and version-specific RAM verification tools."""
from pathlib import Path
import json,re
R=Path(__file__).resolve().parents[1]
paths=['tools/sync_sdk.py','tools/build_emmc_gpt.sh',
       'evidence/build/model-arena-20260910/verification.json',
       'evidence/build/emmc-readonly-20260910/verification.json',
       'board/kickpi_k7/configs/velavision_emmc_gpt_local/defconfig',
       'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c']
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7emmc').iterdir()) if p.is_file()]
report=json.loads((R/'evidence/build/emmc-readonly-20260910/verification.json').read_text())
old={p:report['sources'].get(p) for p in paths}
old['tools/sync_sdk.py']=(R/'private/emmc-gpt-prior-sync-sha.txt').read_text(encoding='utf-8-sig').strip()
(R/'private/emmc-gpt-original-hashes.json').write_text(json.dumps(old),encoding='utf-8')
shell=(R/'tools/build_emmc_readonly.sh').read_text().replace('emmc_readonly','emmc_gpt')
(R/'tools/build_emmc_gpt.sh').write_text(shell,encoding='utf-8',newline='\n')
script=(R/'tools/build_emmc_readonly_vm.py').read_text().replace('emmc-readonly','emmc-gpt').replace('emmc_readonly','emmc_gpt')
script=re.sub(r'^paths=.*$',lambda _: 'paths='+repr(paths),script,flags=re.M)
(R/'tools/build_emmc_gpt_vm.py').write_text(script,encoding='utf-8',newline='\n')
for oldname,newname in [('verify_emmc_readonly_image.py','verify_emmc_gpt_image.py'),
                        ('reboot_emmc_readonly_ram.py','reboot_emmc_gpt_ram.py'),
                        ('start_emmc_readonly_radio.py','start_emmc_gpt_radio.py')]:
    s=(R/'tools'/oldname).read_text().replace('emmc-readonly','emmc-gpt').replace('emmc_readonly','emmc_gpt')
    (R/'tools'/newname).write_text(s,encoding='utf-8',newline='\n')
s=(R/'tools/uart_load_emmc_readonly.py').read_text().replace('emmc-readonly','emmc-gpt').replace('emmc_readonly','emmc_gpt')
s=s.replace('model-arena-20260910','emmc-readonly-20260910')
(R/'tools/uart_load_emmc_gpt.py').write_text(s,encoding='utf-8',newline='\n')
s=(R/'tools/check_emmc_board.py').read_text().replace('emmc-readonly','emmc-gpt')
s=s.replace("('probe' if a.probe else 'status')","('gpt' if a.probe else 'status')")
s=s.replace('time.monotonic()+12','time.monotonic()+16')
(R/'tools/check_emmc_gpt_board.py').write_text(s,encoding='utf-8',newline='\n')
print('Prepared GPT build/RAM scripts; no board or SDK accessed')
