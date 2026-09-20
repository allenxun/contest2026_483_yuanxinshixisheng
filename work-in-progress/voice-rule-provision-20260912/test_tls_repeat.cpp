#include <cstdio>

extern "C" int k7_tls_selftest();

int main() {
  for (unsigned turn = 0; turn < 20; ++turn) {
    if (k7_tls_selftest()) {
      std::printf("tls_repeat_failure=%u\n", turn);
      return 1;
    }
  }
  std::puts("tls_repeat_checks=20 failures=0");
  return 0;
}
