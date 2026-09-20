#pragma once
#include "k7tts_assets_generated.h"
#include <nuttx/drivers/ramdisk.h>
#include <nuttx/mm/k7_model_arena.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <pthread.h>

static int mount_tts_assets() {
  static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
  static bool mounted = false;
  const int locked = pthread_mutex_trylock(&lock);
  if (locked) return -locked;
  struct Unlock { pthread_mutex_t* p; ~Unlock(){pthread_mutex_unlock(p);} } unlock{&lock};
  if (mounted) return 0;
  const int arena_result = k7_model_arena_initialize();
  if (arena_result < 0) return arena_result;
  static_assert(K7_TTS_ROM_ADDRESS >= K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE,
                "TTS resources overlap model allocator");
  static_assert(K7_TTS_ROM_ADDRESS >= UINT64_C(0x944b0310), "TTS overlaps ASR decoder");
  static_assert(K7_TTS_ROM_BYTES && K7_TTS_ROM_BYTES % 512 == 0, "sector alignment");
  static_assert(K7_TTS_ROM_ADDRESS + K7_TTS_ROM_BYTES <=
                K7_MODEL_ARENA_BASE + K7_MODEL_WINDOW_SIZE, "unmapped resources");
  const auto* bytes = reinterpret_cast<const std::uint8_t*>(K7_TTS_ROM_ADDRESS);
  if (std::memcmp(bytes, "-rom1fs-", 8)) return -ENODATA;
  std::uint32_t crc = 0xffffffffu;
  for (std::size_t i=0;i<K7_TTS_ROM_BYTES;++i) {
    crc ^= bytes[i];
    for (unsigned bit=0;bit<8;++bit) crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
  }
  if ((crc ^ 0xffffffffu) != K7_TTS_ROM_CRC32) return -EIO;
  if (mkdir("/mnt", 0755) && errno != EEXIST) return -errno;
  if (mkdir("/mnt/k7tts", 0755) && errno != EEXIST) return -errno;
  int ret = romdisk_register(9, bytes, K7_TTS_ROM_BYTES / 512, 512);
  if (ret < 0) return ret;
  if (mount("/dev/ram9", "/mnt/k7tts", "romfs", MS_RDONLY, nullptr)) {
    ret = -errno;
    ramdisk_unregister(9);
    return ret;
  }
  mounted = true;
  return 0;
}
