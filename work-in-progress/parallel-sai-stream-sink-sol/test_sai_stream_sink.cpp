#include "sai_stream_sink.h"

#include <cstdlib>
#include <cstdio>
#include <vector>

struct Fake {
  uint64_t now{};
  unsigned fifo{};
  bool owner{};
  bool owner_held{};
  bool cancel{};
  unsigned cancel_after_words{~0u};
  bool consume{true};
  int fail_prepare{}, fail_start{}, fail_amp{}, fail_stop{}, fail_codec{}, fail_platform{};
  unsigned acquire_calls{}, release_calls{}, prepare_calls{}, start_calls{}, amp_on_calls{};
  unsigned amp_off_calls{}, stop_calls{}, codec_stop_calls{}, platform_calls{}, words{};
};

static uint64_t now_us(void *p) { auto& f = *static_cast<Fake*>(p); return ++f.now; }
static int cancelled(void *p) { auto& f=*static_cast<Fake*>(p); return f.cancel || f.words>=f.cancel_after_words; }
static int acquire(void *p) { auto& f=*static_cast<Fake*>(p); ++f.acquire_calls; if(f.owner||f.owner_held)return -1; f.owner=true; return 0; }
static void release(void *p,int held) { auto& f=*static_cast<Fake*>(p); ++f.release_calls; f.owner=false; f.owner_held=held!=0; }
static int prepare(void *p,uint64_t) { auto& f=*static_cast<Fake*>(p); ++f.prepare_calls; return f.fail_prepare; }
static int fifo(void *p,unsigned *n) { auto& f=*static_cast<Fake*>(p); if(f.consume&&f.start_calls&&f.fifo>=2)f.fifo-=2; *n=f.fifo; return 0; }
static int word(void *p,uint32_t) { auto& f=*static_cast<Fake*>(p); ++f.words; ++f.fifo; return 0; }
static int start(void *p) { auto& f=*static_cast<Fake*>(p); ++f.start_calls; return f.fail_start; }
static int amp_on(void *p) { auto& f=*static_cast<Fake*>(p); ++f.amp_on_calls; return f.fail_amp; }
static int amp_off(void *p) { ++static_cast<Fake*>(p)->amp_off_calls; return 0; }
static int stop(void *p,uint64_t) { auto& f=*static_cast<Fake*>(p); ++f.stop_calls; return f.fail_stop; }
static int codec_stop(void *p,uint64_t) { auto& f=*static_cast<Fake*>(p); ++f.codec_stop_calls; return f.fail_codec; }
static int platform(void *p,uint64_t) { auto& f=*static_cast<Fake*>(p); ++f.platform_calls; return f.fail_platform; }

static ss_ops ops(Fake& f) {
  return {&f,now_us,cancelled,acquire,release,prepare,fifo,word,start,amp_on,
          amp_off,stop,codec_stop,platform};
}
static ss_sink sink(Fake& f) { ss_sink s{}; auto o=ops(f); if(ss_init(&s,&o)) std::abort(); return s; }
static std::vector<int32_t> samples(unsigned frames) { return std::vector<int32_t>(2*frames,0x12340000); }

static int failures;
#define CHECK(x) do { if(!(x)){std::printf("FAIL %s:%d %s\n",__FILE__,__LINE__,#x);++failures;} } while(0)

static void continuous_and_short_write() {
  Fake f; f.consume=false; auto s=sink(f); auto pcm=samples(40);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  ptrdiff_t a=ss_write(&s,pcm.data(),40,10000);
  CHECK(a>0 && a<40);
  f.consume=true;
  unsigned total=(unsigned)a;
  while(total<40){auto n=ss_write(&s,pcm.data()+2*total,40-total,10000);CHECK(n>0);total+=(unsigned)n;}
  CHECK(ss_end(&s,10000)==SS_OK);
  CHECK(total==40 && f.prepare_calls==1 && f.start_calls==1 && f.amp_on_calls==1);
  CHECK(f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1 && f.release_calls==1);
}

static void small_stream_starts_on_drain() {
  Fake f; auto s=sink(f); auto pcm=samples(3);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_write(&s,pcm.data(),3,10000)==3 && f.start_calls==0);
  CHECK(ss_end(&s,10000)==SS_OK && f.start_calls==1 && f.amp_on_calls==1);
}

static void busy_with_capture_owner() {
  Fake f; f.owner=true; auto s=sink(f);
  CHECK(ss_begin(&s,16000,2,10000)==SS_BUSY);
  CHECK(f.prepare_calls==0 && f.release_calls==0);
}

static void cancel_cleans_everything() {
  Fake f; auto s=sink(f); auto pcm=samples(8);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  f.cancel=true;
  CHECK(ss_write(&s,pcm.data(),8,10000)==SS_CANCELLED);
  CHECK(!f.owner && f.amp_off_calls==1 && f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1);
  CHECK(ss_abort(&s,10000)==SS_OK && f.release_calls==1);
}

static void mid_write_cancel_is_not_a_short_success() {
  Fake f; f.cancel_after_words=4; auto s=sink(f); auto pcm=samples(8);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_write(&s,pcm.data(),8,10000)==SS_CANCELLED);
  CHECK(s.state==SS_IDLE && !f.owner && f.words==4 && f.release_calls==1);
}

static void start_failure_cleans() {
  Fake f; f.fail_start=1; auto s=sink(f); auto pcm=samples(8);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_write(&s,pcm.data(),8,10000)==SS_IO);
  CHECK(!f.owner && f.amp_off_calls==1 && f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1);
}

static void amp_failure_cleans() {
  Fake f; f.fail_amp=1; auto s=sink(f); auto pcm=samples(8);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_write(&s,pcm.data(),8,10000)==SS_IO);
  CHECK(!f.owner && f.start_calls==1 && f.amp_on_calls==1 && f.amp_off_calls==1 && f.stop_calls==1);
}

static void drain_timeout_cleans() {
  Fake f; f.consume=false; auto s=sink(f); auto pcm=samples(8);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_write(&s,pcm.data(),8,10000)==8);
  CHECK(ss_drain(&s,10000)==SS_TIMEOUT);
  CHECK(!f.owner && s.state==SS_IDLE && f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1);
}

static void cleanup_failure_is_held_and_complete() {
  Fake f; f.fail_stop=1; f.fail_codec=1; f.fail_platform=1; auto s=sink(f);
  CHECK(ss_begin(&s,16000,2,10000)==SS_OK);
  CHECK(ss_abort(&s,10000)==SS_CLEANUP);
  CHECK(s.state==SS_FAULT && s.held && !f.owner && f.owner_held);
  CHECK(f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1 && f.release_calls==1);
  CHECK(ss_begin(&s,16000,2,10000)==SS_INVALID);
}

static void prepare_failure_cleans() {
  Fake f; f.fail_prepare=1; auto s=sink(f);
  CHECK(ss_begin(&s,16000,2,10000)==SS_IO);
  CHECK(!f.owner && f.amp_off_calls==1 && f.stop_calls==1 && f.codec_stop_calls==1 && f.platform_calls==1 && f.release_calls==1);
}

int main() {
  continuous_and_short_write(); small_stream_starts_on_drain();
  busy_with_capture_owner(); cancel_cleans_everything(); mid_write_cancel_is_not_a_short_success(); start_failure_cleans();
  amp_failure_cleans(); drain_timeout_cleans(); cleanup_failure_is_held_and_complete(); prepare_failure_cleans();
  if(failures)return 1;
  std::puts("PASS 10/10: continuous short-write, short drain, capture busy, cancel cleanup, mid-write cancel, start cleanup, amp cleanup, drain timeout, cleanup hold, prepare cleanup");
  return 0;
}
