import hashlib
import json
import pathlib
import struct
import zlib

HERE = pathlib.Path(__file__).resolve().parent
IMAGE = HERE / "k7tts.romfs"
ASSETS = HERE / "romfs-root"

ARENA_BEGIN = 0x60000000
ARENA_END = 0x80000000
ENCODER_BEGIN = 0x80000000
ENCODER_BYTES = 166_189_616
DECODER_BEGIN = 0x90000000
DECODER_BYTES = 72_024_848
ROMFS_BEGIN = 0x96000000
ROMFS_WINDOW_END = 0x98000000
MMU_WINDOW_END = 0xA0000000
SECTOR_BYTES = 512


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


data = IMAGE.read_bytes()
assert data[:8] == b"-rom1fs-"
logical_bytes = struct.unpack(">I", data[8:12])[0]
assert len(data) % SECTOR_BYTES == 0
assert ROMFS_BEGIN + len(data) <= ROMFS_WINDOW_END
assert ARENA_END <= ENCODER_BEGIN
assert ENCODER_BEGIN + ENCODER_BYTES <= DECODER_BEGIN
assert DECODER_BEGIN + DECODER_BYTES <= ROMFS_BEGIN
assert ROMFS_WINDOW_END <= MMU_WINDOW_END
for name in ("vits.ort", "tokens.txt", "lexicon.txt"):
    assert name.encode() + b"\0" in data

result = {
    "status": "pass",
    "image": {
        "path": str(IMAGE),
        "bytes_registered": len(data),
        "romfs_superblock_bytes": logical_bytes,
        "sector_bytes": SECTOR_BYTES,
        "nsectors": len(data) // SECTOR_BYTES,
        "sha256": sha256(IMAGE),
        "crc32": f"{zlib.crc32(data) & 0xffffffff:08x}",
        "volume": "K7TTS",
    },
    "assets": {
        name: {
            "bytes": (ASSETS / name).stat().st_size,
            "sha256": sha256(ASSETS / name),
            "mode_in_image": "0444",
        }
        for name in ("vits.ort", "tokens.txt", "lexicon.txt")
    },
    "layout": {
        "model_heap": [f"0x{ARENA_BEGIN:08x}", f"0x{ARENA_END:08x}"],
        "asr_encoder_source": [
            f"0x{ENCODER_BEGIN:08x}",
            f"0x{ENCODER_BEGIN + ENCODER_BYTES:08x}",
        ],
        "asr_decoder_source": [
            f"0x{DECODER_BEGIN:08x}",
            f"0x{DECODER_BEGIN + DECODER_BYTES:08x}",
        ],
        "tts_romfs": [f"0x{ROMFS_BEGIN:08x}", f"0x{ROMFS_BEGIN + len(data):08x}"],
        "tts_window_end": f"0x{ROMFS_WINDOW_END:08x}",
        "window_slack_bytes": ROMFS_WINDOW_END - ROMFS_BEGIN - len(data),
        "mmu_window_end": f"0x{MMU_WINDOW_END:08x}",
    },
    "generator": {
        "path": "/home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/genromfs",
        "version": "0.5.2",
        "sha256": "309c843dda9046ae6685f338a015c06337a748e1d60556523d627f83d018cc5c",
        "command": "genromfs -f k7tts.romfs -d romfs-root -V K7TTS",
        "repeat_image_identical": True,
    },
    "host_verified": True,
    "arm64_compiled_with_romfs": False,
    "board_tested": False,
}
(HERE / "romfs-audit.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
