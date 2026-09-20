from pathlib import Path
here=Path(__file__).resolve().parent
prior=here.parent/'voice-ui-connect-20260913'
for name in ('load_prefix.py','package_prefix.py','transfer_and_boot.py','audit_package.py','prepare_resync.py'):
    text=(prior/name).read_text()
    text=text.replace('velavision_voice_ui_connect_20260913','velavision_spoken_tts_20260913')
    text=text.replace('voice-ui-connect-prefix.bin','spoken-tts-prefix.bin')
    if name=='load_prefix.py':
        marker='    if MODE == "stage-decoder":'
        assert marker in text
        text=text.replace(marker,'''    if MODE == "stage-rom":
        with open_port() as port:
            port.write(b"\\x03\\r")
            port.flush()
            output = read(port, 5, rb"(?:^|\\n)=>\\s*$")
            if not re.search(rb"(?:^|\\n)=>\\s*$", output):
                raise RuntimeError("U-Boot prompt missing")
            check_crc(port, 0x40c00800, 33235968, "9efc1996")
            copy_nonoverlap(port, 0x40c00800, 0x96000000, 33235968)
            check_crc(port, 0x96000000, 33235968, "9efc1996")
            reset_to_uboot(port)
            check_crc(port, 0x96000000, 33235968, "9efc1996")
            check_crc(port, 0x86000000, 0x3e7da30, "b5f7ae2d")
            check_crc(port, 0x90000000, 0x44b0310, "2af64aa7")
            enter_fastboot(port)
    elif MODE == "stage-decoder":''')
        marker='            copy_nonoverlap(port, 0x40C00800, 0x80000000, 0x6000000)'
        assert marker in text
        text=text.replace(marker,'            check_crc(port, 0x96000000, 33235968, "9efc1996")\n'+marker)
    (here/name).write_text(text)
