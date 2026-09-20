"""Prepare isolated read-only block driver build with prior-source hash gates."""
from pathlib import Path
import json,re
R=Path(__file__).resolve().parents[1]
paths=['tools/sync_sdk.py','tools/build_emmc_block.sh',
       'evidence/build/model-arena-20260910/verification.json',
       'evidence/build/emmc-readonly-20260910/verification.json',
       'evidence/build/emmc-gpt-20260910/verification.json',
       'board/kickpi_k7/configs/velavision_emmc_block_local/defconfig',
       'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c']
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7emmc').iterdir()) if p.is_file()]
report=json.loads((R/'evidence/build/emmc-gpt-20260910/verification.json').read_text())
old={p:report['sources'].get(p) for p in paths}
old['tools/sync_sdk.py']=(R/'private/emmc-block-prior-sync-sha.txt').read_text(encoding='utf-8-sig').strip()
(R/'private/emmc-block-original-hashes.json').write_text(json.dumps(old),encoding='utf-8')
shell=(R/'tools/build_emmc_gpt.sh').read_text().replace('emmc_gpt','emmc_block')
(R/'tools/build_emmc_block.sh').write_text(shell,encoding='utf-8',newline='\n')
script=(R/'tools/build_emmc_gpt_vm.py').read_text().replace('emmc-gpt','emmc-block').replace('emmc_gpt','emmc_block')
script=re.sub(r'^paths=.*$',lambda _: 'paths='+repr(paths),script,flags=re.M)
(R/'tools/build_emmc_block_vm.py').write_text(script,encoding='utf-8',newline='\n')
for oldname,newname in [('verify_emmc_gpt_image.py','verify_emmc_block_image.py'),
                        ('reboot_emmc_gpt_ram.py','reboot_emmc_block_ram.py'),
                        ('start_emmc_gpt_radio.py','start_emmc_block_radio.py')]:
    s=(R/'tools'/oldname).read_text().replace('emmc-gpt','emmc-block').replace('emmc_gpt','emmc_block')
    (R/'tools'/newname).write_text(s,encoding='utf-8',newline='\n')
s=(R/'tools/uart_load_emmc_gpt.py').read_text().replace('emmc-gpt','emmc-block').replace('emmc_gpt','emmc_block')
s=s.replace('emmc-readonly-20260910','emmc-gpt-20260910')
(R/'tools/uart_load_emmc_block.py').write_text(s,encoding='utf-8',newline='\n')
s=(R/'tools/check_emmc_gpt_board.py').read_text().replace('emmc-gpt','emmc-block')
s=s.replace("p.add_argument('--probe',action='store_true');","p.add_argument('--probe',action='store_true');p.add_argument('--blockcheck',action='store_true');")
s=s.replace("('gpt' if a.probe else 'status')","('blockcheck' if a.blockcheck else 'register' if a.probe else 'status')")
(R/'tools/check_emmc_block_board.py').write_text(s,encoding='utf-8',newline='\n')
print('Prepared block build/RAM scripts')
