# K7 TTS ROMFS candidate audit

## Result

The three locked TTS assets fit in the proposed 32 MiB staging window. The
actual SDK-generated image is `k7tts.romfs`, 33,235,968 bytes, SHA-256
`8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f`,
and IEEE CRC-32 `0x9efc1996`. Two independent invocations of the same SDK
binary produced byte-identical images.

The ROMFS superblock records 33,235,632 logical bytes. `genromfs` pads the
file to 33,235,968 bytes, which is an exact multiple of 512. Registration
must use the padded file size: 64,914 sectors of 512 bytes. The superblock
logical size must not replace the registered or staged byte count.

`file(1)` identified the output as ROMFS version 1 and `genromfs -v` listed:

| Image path | Bytes | Mode |
| --- | ---: | ---: |
| `/vits.ort` | 31,190,816 | 0444 |
| `/tokens.txt` | 1,671 | 0444 |
| `/lexicon.txt` | 2,042,943 | 0444 |

After mounting at `/mnt/k7tts`, the existing Sherpa file readers can use
`/mnt/k7tts/vits.ort`, `/mnt/k7tts/tokens.txt`, and
`/mnt/k7tts/lexicon.txt`. This removes the invalid `k7ram:` and `/tmp`
assumptions without changing Sherpa internals.

## Exact generator and contract

The SDK already contains `genromfs`; no package installation is needed:

```text
/home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/genromfs
version: 0.5.2
sha256: 309c843dda9046ae6685f338a015c06337a748e1d60556523d627f83d018cc5c
```

The reproducible command, after setting the source directory and files to
0755/0444 respectively, is:

```sh
genromfs -f k7tts.romfs -d romfs-root -V K7TTS
```

`k7tts_assets_generated.h` contains the build contract:

```c
#define K7_TTS_ROM_ADDRESS UINT64_C(0x96000000)
#define K7_TTS_ROM_BYTES UINT32_C(33235968)
#define K7_TTS_ROM_CRC32 UINT32_C(0x9efc1996)
```

## NuttX configuration and API

The exact SDK Kconfig dependency is `CONFIG_FS_ROMFS=y`; it depends on
`!CONFIG_DISABLE_MOUNTPOINT`. The current board config already has
mountpoints enabled. `ramdisk.c` is compiled whenever mountpoints are
enabled; `CONFIG_DRVR_MKRD` only adds the heap-allocating `mkrd()` helper and
is not required by `romdisk_register()`.

The exact SDK declaration is:

```c
int ramdisk_register(int minor, uint8_t *buffer, uint32_t nsectors,
                     uint16_t sectsize, uint8_t rdflags);
#define romdisk_register(m,b,n,s) ramdisk_register(m,(uint8_t *)b,n,s,0)
```

Flags zero make the disk read-only. A suitable sequence is
`romdisk_register(9, (const void *)0x96000000, 64914, 512)` followed by
`mount("/dev/ram9", "/mnt/k7tts", "romfs", MS_RDONLY, NULL)`. The
mountpoint and its parent must exist first. The current config has
`CONFIG_DEFAULT_SMALL=n`, so enabling ROMFS also defaults
`CONFIG_FS_ROMFS_CACHE_NODE=y`; with only the root and three files this is a
small metadata cost and does not copy file contents.

## Audited memory layout

The staged-assets configuration reduces the model allocator to
`[0x60000000,0x80000000)` while retaining the already audited MMU window
`[0x60000000,0xa0000000)`. This is required: the former 1 GiB arena allocator
covered every ASR/TTS source staging address and could overwrite them.

| Owner | Half-open address range |
| --- | --- |
| model allocator | `0x60000000..0x80000000` |
| ASR encoder source | `0x80000000..0x89e7da30` |
| ASR decoder source | `0x90000000..0x944b0310` |
| TTS ROMFS image | `0x96000000..0x97fb2400` |
| reserved TTS window | `0x96000000..0x98000000` |

The decoder-to-ROMFS gap is `0x1b4fcf0` bytes. The 32 MiB TTS window leaves
318,464 bytes after the actual image. The layout assertions in
`romfs_audit.py` pass. This is a static address and artifact audit, not proof
that a transfer preserved bytes; the firmware must compare CRC-32 before
registration.

## Dynamic SSID boundary

The supplied Chinese VITS lexicon has no ASCII word entries. Host runs with
`Lansee`, `Lansee_vistor`, and `Lansee_auto` log every lowercase word and
underscore as OOV and ignore them. The calls still return a very short PCM
tail, so success/nonzero PCM is not evidence that the SSID was spoken.

For this model, the caller must convert supported ASCII characters to
Chinese spoken character names before synthesis, and give `_` a Chinese
name such as `下划线`. The tested example `Lansee` -> `艾勒艾恩艾丝伊伊`
produced substantial speech without an ASCII OOV. This conversion should be
bounded to the accepted SSID alphabet; punctuation must also be converted or
omitted. Full arbitrary Unicode SSIDs are not covered by this candidate.

## Remaining proof

- The Ubuntu project copy observed during this audit still had the older
  1 GiB arena/MMU sources. The local guarded sources must be synchronized
  before the new configuration is built.
- Build and final-link proof must include `CONFIG_FS_ROMFS=y`, the generated
  header, and the current combined ASR/TTS runtime. Earlier ARM64 object and
  demand-link evidence predates ROMFS integration.
- Board proof must separately verify staged CRC, mount, opening all three
  files, model initialization, real speech, and ASR/TTS peak arena usage.
  The existing ASR peak of 468,101,988 bytes leaves about 68.8 MB in the
  512 MiB arena; ROMFS avoids storing source bytes in that heap, but Sherpa
  may allocate a model-read buffer and ORT session memory concurrently.
- No board operation was performed by this subtask.
