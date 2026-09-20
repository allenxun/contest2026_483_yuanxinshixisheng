/* SPDX-License-Identifier: Apache-2.0
 * Control diagnostic: single CPU5 cold, or complete preheat then CPU4/5.
 * Derived from concurrent-probe-v1; no peripheral or model access.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#ifdef __NuttX__
#include <nuttx/config.h>
#endif
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <sched.h>
#include <time.h>

#ifndef K7EH_FAIL_CREATE
#define K7EH_FAIL_CREATE (-1)
#endif
#if !defined(K7EH_HOST_TEST) && (K7EH_FAIL_CREATE != -1 || defined(K7EH_SLOW_READY) || defined(K7EH_BAD_COUNT))
#error Host fault injection must not enter target builds
#endif

namespace {
constexpr unsigned workers = 2;
constexpr uint64_t timeout_ns = 5000000000ULL;
constexpr uint64_t grace_ns = 2000000000ULL;
static_assert(std::atomic<unsigned>::is_always_lock_free,
              "probe coordination requires lock-free unsigned atomics");
struct Slot {
  unsigned id = 0;
  unsigned rounds = 0;
  unsigned caught = 0;
  unsigned cleaned = 0;
  unsigned errors = 0;
  unsigned cpu_mismatches = 0;
  int cpu = -1;
  int requested_cpu = -1;
  uint64_t first_begin = 0;
  uint64_t first_end = 0;
  std::atomic<unsigned> ready{0};
  std::atomic<unsigned> done{0};
};
Slot slots[workers];
pthread_t threads[workers];
std::atomic<unsigned> attempted{0};
std::atomic<unsigned> stop{0};
std::atomic<unsigned> permit{0};

uint64_t now_ns() noexcept
{
  timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) return 0;
  return uint64_t(t.tv_sec) * 1000000000ULL + uint64_t(t.tv_nsec);
}

bool pause_ms(unsigned ms = 1) noexcept
{
  timespec t{time_t(ms / 1000), long(ms % 1000) * 1000000L};
  while (nanosleep(&t, &t) != 0) {
    if (errno != EINTR) return false;
  }
  return true;
}

struct Payload { unsigned worker; unsigned round; };
struct Guard {
  Slot &slot;
  ~Guard() noexcept { ++slot.cleaned; }
};

__attribute__((noinline)) void leaf(Slot &s, unsigned round)
{
  Guard guard{s};
  throw Payload{s.id, round};
}
__attribute__((noinline)) void middle(Slot &s, unsigned round)
{
  Guard guard{s};
  leaf(s, round);
}
__attribute__((noinline)) void outer(Slot &s, unsigned round)
{
  Guard guard{s};
  middle(s, round);
}

void one_throw(Slot &s, unsigned round) noexcept
{
  const unsigned before = s.cleaned;
  try { outer(s, round); ++s.errors; }
  catch (const Payload &p) {
    ++s.caught;
    if (p.worker != s.id || p.round != round) ++s.errors;
  }
  catch (...) { ++s.errors; }
  if (s.cleaned - before != 3) ++s.errors;
}

void *worker(void *arg) noexcept
{
  Slot &s = *static_cast<Slot *>(arg);
#ifdef K7EH_SLOW_READY
  if (s.id == 1) (void)pause_ms(100);
#endif
  for (unsigned round = 0; round < s.rounds && !stop.load(); ++round) {
    s.ready.store(round + 1);
    while (permit.load() < round + 1 && !stop.load()) {
      if (!pause_ms()) { ++s.errors; stop.store(1); }
    }
    if (stop.load()) break;
#ifdef __NuttX__
    s.cpu = sched_getcpu();
    if (s.cpu != s.requested_cpu) ++s.cpu_mismatches;
#endif
    if (round == 0) s.first_begin = now_ns();
    one_throw(s, round);
    if (round == 0) s.first_end = now_ns();
#ifdef __NuttX__
    if (sched_getcpu() != s.requested_cpu) ++s.cpu_mismatches;
#endif
  }
#ifdef K7EH_BAD_COUNT
  if (s.id == 1) ++s.cleaned;
#endif
  s.done.store(1);
  return nullptr;
}

bool reached(unsigned count, unsigned round, bool finished, uint64_t duration)
{
  const uint64_t start = now_ns();
  if (!start) return false;
  for (;;) {
    bool all = true;
    for (unsigned i = 0; i < count; ++i)
      all &= finished ? slots[i].done.load() != 0 : slots[i].ready.load() >= round;
    if (all) return true;
    const uint64_t now = now_ns();
    if (!now || now < start || now - start >= duration || !pause_ms()) return false;
  }
}

[[noreturn]] void preserve_owner(const char *reason)
{
  std::printf("K7EHCONTROL REBOOT_REQUIRED reason=%s owner_retained=1\n", reason);
  std::fflush(stdout);
  /* Never return from this task with outstanding pthread ownership.  A
   * broken unwinder cannot be safely cancelled. External watchdog required.
   */
  for (;;) (void)pause_ms(1000);
}

int create(unsigned i)
{
  if (int(i) == K7EH_FAIL_CREATE) return EAGAIN;
  pthread_attr_t attr;
  int rc = pthread_attr_init(&attr);
  if (rc) return rc;
  rc = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_JOINABLE);
#ifdef __NuttX__
  if (!rc) rc = pthread_attr_setstacksize(&attr, 16384);
  cpu_set_t cpus;
  CPU_ZERO(&cpus);
  CPU_SET(slots[i].requested_cpu, &cpus);
  if (!rc) rc = pthread_attr_setaffinity_np(&attr, sizeof(cpus), &cpus);
#else
  if (!rc) rc = pthread_attr_setstacksize(&attr, 65536);
#endif
  if (!rc) rc = pthread_create(&threads[i], &attr, worker, &slots[i]);
  const int destroy_rc = pthread_attr_destroy(&attr);
  if (destroy_rc) {
    /* Creation success must still be reported as success to preserve ownership. */
    std::printf("K7EHCONTROL attr_destroy_error=%d\n", destroy_rc);
    stop.store(1);
  }
  return rc;
}
} // namespace

extern "C" int k7ehcontrol_main(int argc, char **argv)
{
  if (argc != 2 || (std::strcmp(argv[1], "single") && std::strcmp(argv[1], "warm1"))) {
    std::puts("usage: k7ehcontrol single|warm1 (fresh boot each; single CPU5, warm1 CPU4/5)");
    return 1;
  }
  if (attempted.exchange(1)) { std::puts("K7EHCONTROL already attempted; reboot required"); return 2; }
  const bool warm = !std::strcmp(argv[1], "warm1");
  const unsigned rounds = 1;
  const unsigned active = warm ? workers : 1;
  std::printf("K7EHCONTROL begin mode=%s rounds=%u workers=%u main_prethrow=%u\n", argv[1], rounds, active, unsigned(warm));
  if (warm) {
    Slot preheat;
    preheat.id = 99;
    one_throw(preheat, 0);
    if (preheat.errors || preheat.caught != 1 || preheat.cleaned != 3) {
      std::puts("K7EHCONTROL PREHEAT_FAIL code=22 workers_created=0");
      return 22;
    }
    std::puts("K7EHCONTROL PREHEAT_PASS caught=1 cleaned=3 workers_created=0");
    std::fflush(stdout);
  }
  unsigned created = 0;
  int result = 0;
  for (unsigned i = 0; i < active; ++i) {
    slots[i].id = i;
    slots[i].requested_cpu = warm ? int(i + 4) : 5;
    slots[i].rounds = rounds;
    const int rc = create(i);
    if (rc) {
      std::printf("K7EHCONTROL create_failed index=%u rc=%d\n", i, rc);
      result = 20;
      break;
    }
    ++created;
  }
  if (created == active && !stop.load()) {
    const uint64_t begin = now_ns();
    for (unsigned r = 1; r <= rounds && !result; ++r) {
#ifdef K7EH_SLOW_READY
      const uint64_t limit = 20000000ULL;
#else
      const uint64_t limit = timeout_ns;
#endif
      const uint64_t now = now_ns();
      if (!begin || !now || now < begin || now - begin >= limit ||
          !reached(active, r, false, limit - (now - begin))) {
        result = 21;
        break;
      }
      permit.store(r);
    }
    if (!result && !reached(created, 0, true, timeout_ns)) result = 21;
  } else if (!result) result = 23;
  if (result) stop.store(1);
  if (!reached(created, 0, true, grace_ns)) preserve_owner("worker_not_finished");
  for (unsigned i = 0; i < created; ++i) {
    const int rc = pthread_join(threads[i], nullptr);
    if (rc) preserve_owner("join_failed");
  }
  for (unsigned i = 0; i < created; ++i) {
    const Slot &s = slots[i];
    std::printf("K7EHCONTROL worker=%u caught=%u cleaned=%u errors=%u cpu=%d requested_cpu=%d cpu_mismatch=%u first_begin=%llu first_end=%llu\n",
                i, s.caught, s.cleaned, s.errors, s.cpu, s.requested_cpu, s.cpu_mismatches,
                (unsigned long long)s.first_begin, (unsigned long long)s.first_end);
    if (!result && (s.caught != rounds || s.cleaned != rounds * 3 || s.errors || s.cpu_mismatches)) result = 22;
  }
  if (stop.load() && !result) result = 23;
  std::printf("K7EHCONTROL result=%s code=%d created=%u joined=%u mode=%s concurrency_proven=0\n",
              result ? "FAIL" : "PASS", result, created, created, argv[1]);
  return result;
}

#ifdef K7EH_HOST_TEST
int main(int argc, char **argv)
{
  if (argc == 2 && !std::strcmp(argv[1], "repeat")) {
    char cold[] = "single";
    char *args[] = {argv[0], cold};
    if (k7ehcontrol_main(2, args)) return 99;
    return k7ehcontrol_main(2, args);
  }
  return k7ehcontrol_main(argc, argv);
}
#endif
