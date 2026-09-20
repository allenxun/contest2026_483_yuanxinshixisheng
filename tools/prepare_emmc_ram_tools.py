"""Prepare version-specific RAM tools; does not access the board."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for old,new in [('verify_model_arena_image.py','verify_emmc_readonly_image.py'),
                ('reboot_model_arena_ram.py','reboot_emmc_readonly_ram.py'),
                ('start_model_arena_radio.py','start_emmc_readonly_radio.py')]:
    text=(R/'tools'/old).read_text().replace('model-arena','emmc-readonly').replace('model_arena','emmc_readonly')
    (R/'tools'/new).write_text(text,encoding='utf-8',newline='\n')
text=(R/'tools/uart_load_model_arena.py').read_text()
text=text.replace('model-arena','emmc-readonly').replace('model_arena','emmc_readonly')
text=text.replace('wifi-arp-20260909','model-arena-20260910')
(R/'tools/uart_load_emmc_readonly.py').write_text(text,encoding='utf-8',newline='\n')
print('Prepared CRC-gated RAM tools using immutable model-arena blocks')
