#include "native_asr_model_storage.fixed.hpp"

static_assert(K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE ==
                  UINT64_C(0x80000000),
              "ASR compiled allocator end must preserve staged encoder");
static_assert(k7_asr::ModelStorage::encoder_size == 166189616u,
              "unexpected ASR encoder size");
static_assert(k7_asr::ModelStorage::decoder_size == 72024848u,
              "unexpected ASR decoder size");

int main() { return 0; }
