#pragma once

#define SR_CAPACITY 4096
#include "shared_runtime.hpp"

namespace sr_shared {

// One process-wide allocator and ledger serve both ASR and TTS sessions.
Runtime &shared_model_runtime();

}  // namespace sr_shared
