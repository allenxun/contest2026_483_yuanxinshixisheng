/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <nuttx/mm/mm.h>
#include <nuttx/mm/k7_model_arena.h>
#include <nuttx/mutex.h>
#include <errno.h>

static mutex_t g_initialize_lock = NXMUTEX_INITIALIZER;
static struct mm_heap_s *g_model_heap;

int k7_model_arena_initialize(void)
{
  int ret = nxmutex_lock(&g_initialize_lock);
  if (ret < 0) return ret;
  if (g_model_heap == NULL)
    {
      struct mm_heap_s *heap = mm_initialize("k7-model",
        (void *)(uintptr_t)K7_MODEL_ARENA_BASE, K7_MODEL_ARENA_SIZE);
      __atomic_store_n(&g_model_heap, heap, __ATOMIC_RELEASE);
    }
  ret = g_model_heap ? 0 : -ENOMEM;
  nxmutex_unlock(&g_initialize_lock);
  return ret;
}

void *k7_model_alloc(size_t bytes)
{
  struct mm_heap_s *heap = __atomic_load_n(&g_model_heap, __ATOMIC_ACQUIRE);
  return heap && bytes ? mm_memalign(heap, 64, bytes) : NULL;
}

void k7_model_free(void *memory)
{
  struct mm_heap_s *heap = __atomic_load_n(&g_model_heap, __ATOMIC_ACQUIRE);
  if (heap && memory) mm_free(heap, memory);
}

size_t k7_model_available(void)
{
  struct mm_heap_s *heap = __atomic_load_n(&g_model_heap, __ATOMIC_ACQUIRE);
  return heap ? mm_mallinfo(heap).fordblks : 0;
}
