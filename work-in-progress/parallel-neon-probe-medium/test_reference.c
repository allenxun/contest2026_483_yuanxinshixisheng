#include <stdio.h>
#include <string.h>
#include "probe.h"
int main(void)
{
  unsigned cases = 0;
  for (unsigned id = 0; id < 4; ++id)
    for (unsigned steps = 0; steps <= 32; ++steps) {
      float values[16];
      uint32_t words[16];
      probe_input(id, words);
      memcpy(values, words, sizeof(values));
      for (unsigned k = 0; k < 16; ++k)
        if (values[k] != (float)(id * 256 + k)) return 4;
      for (unsigned j = 0; j < steps; ++j)
        for (unsigned k = 0; k < 16; ++k) values[k] += 1.0f;
      memcpy(words, values, sizeof(words));
      if (!probe_match(id, steps, words)) return 1;
      for (unsigned k = 0; k < 16; ++k) {
        values[k] += 1.0f;
        memcpy(words, values, sizeof(words));
        if (probe_match(id, steps, words)) return 2;
        values[k] -= 1.0f;
      }
      if (probe_match(id, 33, words)) return 3;
      ++cases;
    }
  printf("reference PASS cases=%u lane_corruptions=%u invalid_steps=%u\n", cases, cases * 16, cases);
  return 0;
}
