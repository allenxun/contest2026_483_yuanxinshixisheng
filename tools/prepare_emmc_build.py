"""Create a separate build runner from the existing audited staging flow."""
from pathlib import Path
import json,re
R=Path(__file__).resolve().parents[1]
rev='emmc-readonly-20260910'
paths=['tools/sync_sdk.py','tools/build_emmc_readonly.sh',
       'evidence/build/model-arena-20260910/verification.json',
       'board/kickpi_k7/configs/velavision_emmc_readonly_local/defconfig',
       'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c']
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7emmc').iterdir()) if p.is_file()]
report=json.loads((R/'evidence/build/model-arena-20260910/verification.json').read_text())
old={p:report['sources'].get(p) for p in paths}
old['tools/sync_sdk.py']=(R/'private/emmc-prior-sync-sha.txt').read_text(encoding='utf-8-sig').strip()
(R/'private/emmc-readonly-original-hashes.json').write_text(json.dumps(old),encoding='utf-8')
shell=(R/'tools/build_model_arena.sh').read_text().replace('velavision_model_arena','velavision_emmc_readonly')
(R/'tools/build_emmc_readonly.sh').write_text(shell,encoding='utf-8',newline='\n')
script=(R/'tools/build_model_arena_vm.py').read_text()
script=script.replace('model-arena','emmc-readonly').replace('model_arena','emmc_readonly')
script=re.sub(r'^paths=.*$',lambda _: 'paths='+repr(paths),script,flags=re.M)
# The generated report still validates the model arena plus the new command.
script=script.replace("assert 'CONFIG_RK3576_MODEL_ARENA=y' in (B/'.config').read_text()",
                      "assert 'CONFIG_EXAMPLES_K7EMMC=y' in (B/'.config').read_text()")
(R/'tools/build_emmc_readonly_vm.py').write_text(script,encoding='utf-8',newline='\n')
print('Prepared independent eMMC build runner; no SDK or hardware accessed')
