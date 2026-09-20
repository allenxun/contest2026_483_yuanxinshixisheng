/* HOST TEST ONLY. Same frozen API declarations, redirected address range. */
#include "../../../input/nuttx/mm/k7_model_arena.h"
uintptr_t kap_mock_base(void);
#undef K7_MODEL_ARENA_BASE
#undef K7_MODEL_ARENA_SIZE
#define K7_MODEL_ARENA_BASE ((uint64_t)kap_mock_base())
#define K7_MODEL_ARENA_SIZE UINT64_C(1048576)
