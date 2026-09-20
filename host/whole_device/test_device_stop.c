#include <assert.h>
#include "../../app/k7agent/cloud/src/board_speech_bridge.c"
uint64_t k7sound_clock_us(void){return 1;}
int k7_photo_native_copy(uint32_t epoch,unsigned side,struct k7_photo_record *r,void *data,size_t cap)
{(void)epoch;(void)side;(void)r;(void)data;(void)cap;return -ENODEV;}
static int holds,plays;
static atomic_int photo_available;
int k7sound_capture_stream_cued(unsigned n,pio_sample_sink sink,void *arg)
{(void)n;(void)sink;(void)arg;return -ENOSYS;}
void k7_pipeline_halt(void){holds++;}
int k7_pipeline_voice_mode(unsigned mode){(void)mode;return 0;}
int k7_pipeline_voice_mode_status(unsigned mode){(void)mode;return 0;}
int k7_photo_native_status(uint32_t *epoch,unsigned *done)
{if(!atomic_load(&photo_available))return -ENODEV;*epoch=1;*done=0;return 0;}
int k7sound_capture_stream(unsigned n,pio_sample_sink sink,void *arg)
{(void)n;(void)sink;(void)arg;return -ENOSYS;}
int k7sound_speak_mono16_cancel(const int16_t *p,unsigned n,int (*cancel)(void *),void *arg)
{(void)p;(void)n;(void)cancel;(void)arg;plays++;return 0;}
int main(void)
{
  unsigned old=atomic_load(&device_epoch);
  assert(!k7cloud_device_stop());
  assert(holds==1 && old!=atomic_load(&device_epoch));
  /* Stale late TTS rejected before connection and cannot reset cancellation. */
  assert(board_speech("tracking_ready","invalid-ip",&old)==-ECANCELED);
  assert(atomic_load(&tts_cancelled) && plays==0);
  assert(!pthread_mutex_trylock(&audio_owner));pthread_mutex_unlock(&audio_owner);
  assert(device_round("invalid-ip",old)==-ECANCELED);
  assert(!atomic_load(&device_busy));
  int pair[2];assert(!socketpair(AF_UNIX,SOCK_STREAM,0,pair));
  tts_fd=pair[0];assert(!k7cloud_device_stop());
  char byte;assert(recv(pair[1],&byte,1,0)==0);
  close(pair[0]);close(pair[1]);tts_fd=-1;
  assert(k7cloud_device_loop("invalid-ip",0)==-EINVAL);
  atomic_store(&device_loop_busy,true);
  assert(k7cloud_device_loop("invalid-ip",1)==-EBUSY);
  assert(k7cloud_device_once("invalid-ip")==-EBUSY);
  assert(k7cloud_chat_loop("invalid-ip",1)==-EBUSY);
  atomic_store(&device_loop_busy,false);
  assert(k7cloud_chat_loop("invalid-ip",0)==-EINVAL);
  assert(k7cloud_chat_loop("invalid-ip",1)==-EINVAL);
  assert(!atomic_load(&device_busy) && !atomic_load(&device_loop_busy));
  /* Loop failure joins its observer before stack context/flags are released. */
  assert(k7cloud_device_loop("invalid-ip",1)==-EINVAL);
  assert(!atomic_load(&device_busy) && !atomic_load(&device_loop_busy));
  /* A pending stage cannot steal the command's capture/confirmation audio. */
  struct photo_worker w={.ip="invalid-ip",.epoch=atomic_load(&device_epoch)};
  atomic_init(&w.stop,false);atomic_init(&w.pending,false);atomic_init(&w.result,0);
  atomic_store(&photo_available,1);atomic_store(&device_busy,true);
  pthread_t watch;assert(!pthread_create(&watch,NULL,photo_watch,&w));
  for(unsigned i=0;i<100 && !atomic_load(&w.pending);i++)usleep(1000);
  assert(atomic_load(&w.pending));
  assert(w.state.epoch==0 && atomic_load(&w.result)==0);
  atomic_store(&w.stop,true);pthread_join(watch,NULL);
  assert(!atomic_load(&w.pending));
  atomic_store(&device_busy,false);
  /* A stage playback failure stops the session, and exposes its real error. */
  struct photo_worker failed={.ip="invalid-ip",.epoch=atomic_load(&device_epoch)};
  atomic_init(&failed.stop,false);atomic_init(&failed.pending,false);atomic_init(&failed.result,0);
  unsigned before_failure=atomic_load(&device_epoch);
  assert(!pthread_create(&watch,NULL,photo_watch,&failed));
  pthread_join(watch,NULL);
  assert(atomic_load(&failed.result)==-EINVAL);
  assert(atomic_load(&device_epoch)!=before_failure);
  assert(!atomic_load(&failed.pending));
  atomic_store(&photo_available,0);
  atomic_store(&tts_cancelled,false);
  assert(!socketpair(AF_UNIX,SOCK_STREAM,0,pair));
  unsigned char response[]={ 'W',0,0,0,0,'D',0,0,0,4,0,0,0,0 };
  assert(send(pair[1],response,sizeof(response),0)==sizeof(response));
  assert(!tts(pair[0],"reply",2) && plays==1);
  close(pair[0]);close(pair[1]);
  assert(!socketpair(AF_UNIX,SOCK_STREAM,0,pair));
  unsigned char silence[]={'N',0,0,0,0};
  assert(send(pair[1],silence,sizeof(silence),0)==sizeof(silence));
  assert(!tts(pair[0],"reply",2) && plays==1);
  close(pair[0]);close(pair[1]);
  assert(!socketpair(AF_UNIX,SOCK_STREAM,0,pair));
  assert(send(pair[1],silence,sizeof(silence),0)==sizeof(silence));
  assert(tts(pair[0],"ordinary",0)==-EINVAL && plays==1);
  close(pair[0]);close(pair[1]);
  puts("native device cancellation guards PASS; no audio or hardware");
}
