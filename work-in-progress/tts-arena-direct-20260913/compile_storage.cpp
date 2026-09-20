#include "native_tts_storage.hpp"

// Compile-only gate: construction is intentionally not executed on the host.
static_assert(K7_TTS_ROM_ADDRESS + K7_TTS_MODEL_OFFSET ==
                  UINT64_C(0x96000730),
              "unexpected direct model address");
static_assert(K7_TTS_MODEL_BYTES == UINT32_C(31190816),
              "unexpected direct model length");

int main() { return 0; }
