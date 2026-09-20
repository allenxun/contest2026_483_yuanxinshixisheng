#include "shared_runtime.hpp"
extern "C" {
#include "k7_model_arena.h"
}
sr::Port sr_target_port(void*ctx,void(*lock)(void*),void(*unlock)(void*)) {
 return {ctx,lock,unlock,k7_model_alloc,k7_model_free,
 static_cast<uintptr_t>(K7_MODEL_ARENA_BASE),
 static_cast<uintptr_t>(K7_MODEL_ARENA_BASE+K7_MODEL_ARENA_SIZE)};
}
