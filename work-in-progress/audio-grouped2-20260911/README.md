# audio-grouped2-20260911

Corrected RK3576 I2S RX diagnostic. The controller exposes four FIFO banks and
each eight-word read group represents one 32 kHz time slot. Two consecutive
groups are reconstructed as one 16 kHz stereo frame without deleting zero
samples or mirroring one channel.

Host validation is inherited from the exact source hashes recorded in
`host-result.json`. `package.py` creates a RAM-only OTG payload containing the
preserved first 96 MiB of the ASR encoder followed by the new firmware.
`windows_ram_test.ps1` verifies every retained model segment and the firmware
CRC before booting. No command writes eMMC.

Hardware acceptance requires 3200 frames to take about 200 ms,
`grouped words=51200`, intact cleanup fields, and a subsequent microphone/ASR
test before this capture path is used by VoiceLink.
