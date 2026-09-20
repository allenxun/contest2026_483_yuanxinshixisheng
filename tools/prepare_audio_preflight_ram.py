"""Derive version-scoped RAM tools; no board access until explicit execution."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
NAMES = ['verify_usb_readonly_image.py', 'reboot_usb_readonly_ram.py',
         'uart_load_usb_readonly.py', 'check_usb_readonly_affinity.py',
         'start_usb_readonly_radio.py', 'collect_usb_readonly_compile.py']


def main():
    for name in NAMES:
        text = (ROOT / 'tools' / name).read_text()
        text = text.replace('usb-readonly', 'audio-preflight').replace('usb_readonly', 'audio_preflight')
        if name == 'uart_load_usb_readonly.py':
            text = text.replace('arena-provider-20260910', 'usb-readonly-20260910')
        if name == 'verify_usb_readonly_image.py':
            text = text.replace("['CONFIG_USBHOST_MSC=y',", "['CONFIG_EXAMPLES_K7AUDIO=y','CONFIG_USBHOST_MSC=y',")
        if name == 'collect_usb_readonly_compile.py':
            text = text.replace('/home/swl/openvela/cmake_out/velavision_audio_preflight_20260910', '/dev/shm/velavision_audio_preflight_20260910')
            text = text.replace("['usbhost_storage.c','rk3576_usbhost.c','k7storage_main.c']", "['k7audio_main.c','audio_preflight.c']")
            text = text.replace("storage-compile.json", "audio-compile.json")
            text = text.replace('assert len(rows)==3', 'assert len(rows)==2')
            text = text.replace("['__NuttX__ 1',", "['CONFIG_EXAMPLES_K7AUDIO 1','__NuttX__ 1',")
            text = text.replace('3 actual target storage units verified, MSC read-only on, FAT off',
                                '2 actual target audio preflight units verified, no host mocks')
        if name == 'reboot_usb_readonly_ram.py':
            text = text.replace("(out/'reboot.bin').write_bytes(buf)", "\n with (out/'reboot.bin').open('xb') as log:log.write(buf)")
        target = ROOT / 'tools' / name.replace('usb_readonly', 'audio_preflight')
        if target.exists():
            assert target.read_text() == text
        else:
            target.write_text(text, newline='\n')
    print('RAM helpers prepared; previous block-reuse source is verified USB image')


if __name__ == '__main__':
    main()
