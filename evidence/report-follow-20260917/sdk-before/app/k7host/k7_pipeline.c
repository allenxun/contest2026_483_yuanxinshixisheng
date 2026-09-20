/* SPDX-License-Identifier: Apache-2.0 */
/* Bounded camera-to-decoder queue. No hardware or DMA buffers are owned here. */
#ifdef __NuttX__
#include <nuttx/config.h>
#endif
#include "k7_pipeline.h"
#include <math.h>
#include "k7_jpeg.h"
#include <pthread.h>
#include <sched.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdio.h>
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
#include <stdatomic.h>
#include "../gimbal/gimbal_link.h"
#include "k7_preview.h"
#include "k7_photo.h"
static atomic_bool g_track_halt;
static pthread_mutex_t g_voice_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_voice_active;
static atomic_uint g_voice_mode;
static unsigned int g_voice_revision;
static unsigned int g_voice_applied_revision;
static unsigned int g_voice_applied_mode;
static int g_voice_applied_result;
int k7_pipeline_voice_mode_status(unsigned int mode)
{
  pthread_mutex_lock(&g_voice_lock);
  int ret = !g_voice_active ? -ENODEV :
    mode != atomic_load(&g_voice_mode) ? -ECANCELED :
    g_voice_applied_revision != g_voice_revision ? -EAGAIN :
    g_voice_applied_result ? g_voice_applied_result :
    g_voice_applied_mode != mode ? -EIO : 0;
  pthread_mutex_unlock(&g_voice_lock);
  return ret;
}
void k7_pipeline_halt(void)
{
  pthread_mutex_lock(&g_voice_lock);
  atomic_store(&g_track_halt, true);
  atomic_store(&g_voice_mode, 0);
  g_voice_revision++;
  pthread_mutex_unlock(&g_voice_lock);
}
int k7_pipeline_voice_mode(unsigned int mode)
{
  if (mode > 2) return -EINVAL;
  pthread_mutex_lock(&g_voice_lock);
  int ret = g_voice_active ? 0 : -ENODEV;
  if (!ret)
    {
      if ((mode == 2 && k7_photo_needs_restart()) ||
          mode != atomic_load(&g_voice_mode) ||
          (mode && atomic_load(&g_track_halt))) g_voice_revision++;
      atomic_store(&g_voice_mode, mode);
      /* Worker alone releases hold after resetting stale filter history. */
      if (!mode) atomic_store(&g_track_halt, true);
    }
  pthread_mutex_unlock(&g_voice_lock);
  return ret;
}
#endif

#define K7_PIPE_SLOTS 8
enum slot_state_e { SLOT_FREE, SLOT_WRITING, SLOT_PENDING, SLOT_DECODING };
struct slot_s
{
  enum slot_state_e state;
  uint8_t *data;
  size_t bytes;
  unsigned int sequence;
  uint64_t published_us;
};
struct k7_pipeline_s
{
  pthread_mutex_t lock;
  pthread_cond_t ready;
  pthread_t thread;
  struct slot_s slots[K7_PIPE_SLOTS];
  uint8_t *storage;
  uint8_t *rgb;
  size_t stride, rgb_capacity;
  unsigned int scale, delay_ms, pending;
  bool stopping;
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  bool tracking;
  bool voice_control;
  unsigned int applied_mode;
  unsigned int applied_revision;
  struct k7_photo_s *photo;
  struct k7_preview_queue_s *preview;
  atomic_bool motion_done;
  int gimbal_fd;
  struct k7_track_s controller;
#endif
  uint64_t started_us;
  struct k7_pipeline_stats_s stats;
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
  struct k7_yunet_s *yunet;
#endif
};

static uint64_t monotonic_us(void)
{
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
static void voice_mode_apply(struct k7_pipeline_s *p)
{
  if (!p->voice_control) return;
  pthread_mutex_lock(&g_voice_lock);
  unsigned int mode = atomic_load(&g_voice_mode);
  if (g_voice_revision != p->applied_revision)
    {
      struct k7_track_config_s config = p->controller.config;
      int ret = p->stats.track_error;
      if (!ret) ret = k7_track_init(&p->controller, &config,
                                    p->controller.sent_x, p->controller.sent_y);
      if (ret < 0) { p->stats.track_error = ret; mode = 0; }
      if (mode == 2) k7_photo_reset();
      atomic_store(&g_track_halt, mode == 0 || p->stats.track_error != 0);
      p->applied_mode = mode;
      p->applied_revision = g_voice_revision;
      g_voice_applied_revision = g_voice_revision;
      g_voice_applied_mode = mode;
      g_voice_applied_result = ret;
      printf("VOICE MODE applied=%u result=%d\n", mode, ret);
    }
  pthread_mutex_unlock(&g_voice_lock);
}

static void track_observation(struct k7_pipeline_s *p,
                              const struct k7_faces_s *faces,
                              unsigned int sequence, uint64_t sample, struct k7_track_result_s *saved)
{
  struct k7_track_result_s r;
  int old_x = p->controller.sent_x, old_y = p->controller.sent_y;
  bool halt = atomic_load(&g_track_halt) ||
              atomic_load(&p->motion_done) || p->stats.track_error;
  uint64_t now = monotonic_us();
  k7_track_step(&p->controller, faces, now, sample, halt, &r);
  p->stats.track_observations++;
  p->stats.track_states[r.state]++;
  if (r.update)
    {
      p->stats.track_updates++;
      unsigned int step = abs(r.x-old_x) > abs(r.y-old_y) ?
                          abs(r.x-old_x) : abs(r.y-old_y);
      if (step > p->stats.track_max_step) p->stats.track_max_step = step;
      if (p->gimbal_fd >= 0)
        {
          /* Recheck after inference. An in-flight UART pair cannot be recalled. */
          if (atomic_load(&g_track_halt) || atomic_load(&p->motion_done))
            { p->controller.sent_x=old_x; p->controller.sent_y=old_y; }
          else
            {
              int ret = gimbal_link_send(p->gimbal_fd, r.x, r.y);
              if (ret < 0)
                {
                  p->stats.track_errors++; p->stats.track_error=ret;
                  p->controller.sent_x=old_x; p->controller.sent_y=old_y;
                }
              else p->stats.track_tx++;
            }
        }
    }
  *saved=r;
  p->stats.track_x=p->controller.sent_x;
  p->stats.track_y=p->controller.sent_y;
  /* A separate short box record lets calibration distinguish complete
   * faces from clipped detections. It is tied to the same sequence.
   */
  if (r.has_face)
    {
      printf("TRACK BOX q=%u x=%.1f y=%.1f w=%.1f h=%.1f edge=%u\n",
             sequence,r.box.x,r.box.y,r.box.width,r.box.height,r.edges);
      struct timespec pace={0,1000000};
      nanosleep(&pace,NULL);
    }
  /* One short record per inference, useful for direction/calibration evidence. */
  printf("TRACK q=%u s=%d dx=%.1f dy=%.1f x=%d y=%d tx=%u age=%u\n",
         sequence, r.state, r.dx, r.dy, p->stats.track_x, p->stats.track_y,
         p->stats.track_tx, (unsigned int)(now-sample));
}
#endif

static void *decode_worker(void *arg)
{
  struct k7_pipeline_s *p = arg;
  for (;;)
    {
      struct k7_jpeg_result_s result;
      int chosen = -1;
      bool latest = false;
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
      latest = p->yunet != NULL;
#endif
      pthread_mutex_lock(&p->lock);
      while (!p->pending && !p->stopping)
        pthread_cond_wait(&p->ready, &p->lock);
      if (!p->pending && p->stopping)
        {
          pthread_mutex_unlock(&p->lock);
          break;
        }

      for (unsigned int i = 0; i < K7_PIPE_SLOTS; i++)
        if (p->slots[i].state == SLOT_PENDING &&
            (chosen < 0 ||
             (latest ? p->slots[i].sequence > p->slots[chosen].sequence :
                       p->slots[i].sequence < p->slots[chosen].sequence)))
          chosen = i;
      /* Tracking needs recent observations. Discard older pending frames
       * when selecting an inference input; never touch WRITING/DECODING.
       * JPEG-only mode preserves its original FIFO behavior.
       */
      if (latest)
        for (unsigned int i = 0; i < K7_PIPE_SLOTS; i++)
          if ((int)i != chosen && p->slots[i].state == SLOT_PENDING)
            {
              p->slots[i].state = SLOT_FREE;
              p->pending--;
              p->stats.dropped++;
            }
      struct slot_s *slot = &p->slots[chosen];
      slot->state = SLOT_DECODING;
      p->pending--;
      pthread_mutex_unlock(&p->lock);

      /* The slot remains exclusively owned by this worker until FREE.
       * Neither the JPEG copy nor decode runs under the queue mutex.
       * Optional delay is only for reproducible backpressure testing.
       */
      if (p->delay_ms)
        {
          struct timespec delay = {0, (long)p->delay_ms * 1000000};
          while (nanosleep(&delay, &delay) < 0 && errno == EINTR) {}
        }
      int ret = k7_jpeg_decode(slot->data, slot->bytes, p->scale,
                               p->rgb, p->rgb_capacity, &result);
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
      struct k7_faces_s faces = {0};
      int face_ret = 0;
      if (ret == 0 && p->yunet)
        face_ret = k7_yunet_detect(p->yunet, p->rgb, result.bytes, &faces);
#endif
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
      if (p->tracking)
        {
          voice_mode_apply(p);
          struct k7_track_result_s observed;
          track_observation(p, ret == 0 && face_ret == 0 ? &faces : NULL,
                            slot->sequence, slot->published_us, &observed);
          if(p->photo && (!p->voice_control || atomic_load(&g_voice_mode)==2))
            {
              k7_photo_process(p->photo,slot->data,slot->bytes,slot->sequence,
                slot->published_us,&observed,faces.count,atomic_load(&g_track_halt)||atomic_load(&p->motion_done));
              uint32_t completed_epoch=0;unsigned completed_views=0;
              if(p->voice_control && !k7_photo_native_status(&completed_epoch,&completed_views) && completed_views==7)
                {
                  /* Preserve the immutable RAM set; prevent future pose/target work.
                   * Applied hold is confirmed separately before upload admission. */
                  k7_pipeline_halt();
                  printf("PHOTO complete e=%u views=7 hold_requested=1 upload_started=0\n",completed_epoch);
                }
            }
          /* Submit a private RGB copy; output never runs in this worker. */
          if (p->preview && ret == 0)
            k7_preview_queue_submit(p->preview,p->rgb,result.bytes,slot->sequence);
        }
#endif
      uint64_t age = monotonic_us() - slot->published_us;

      pthread_mutex_lock(&p->lock);
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
      p->stats.last_face_count = 0;
      memset(&p->stats.primary, 0, sizeof(p->stats.primary));
      if (ret == 0 && p->yunet)
        {
          if (face_ret < 0) p->stats.face_failures++;
          else
            {
              p->stats.face_inferences++;
              p->stats.inference_us += faces.usec;
              if (faces.usec > p->stats.max_inference_us)
                p->stats.max_inference_us = faces.usec;
              p->stats.last_face_count = faces.count;
              if (faces.count) p->stats.face_frames++;
              float best = -1;
              for (unsigned int i = 0; i < faces.count; i++)
                {
                  struct k7_face_s *f = &faces.face[i];
                  float dx = f->x + f->width / 2 - 80;
                  float dy = f->y + f->height / 2 - 60;
                  float distance = sqrtf(dx * dx + dy * dy) / 100;
                  float priority = f->width * f->height * f->score *
                    (1.25f - 0.25f * fminf(distance, 1));
                  if (priority > best)
                    { best = priority; p->stats.primary = *f; }
                }
            }
        }
#endif
      p->stats.decode_us += result.usec;
      if (result.usec > p->stats.max_decode_us)
        p->stats.max_decode_us = result.usec;
      if (age > p->stats.max_age_us) p->stats.max_age_us = age;
      if (ret == 0)
        {
          p->stats.decoded++;
          p->stats.last_sequence = slot->sequence;
          p->stats.width = result.width;
          p->stats.height = result.height;
          p->stats.bytes = result.bytes;
        }
      else
        {
          p->stats.failed++;
          p->stats.last_error = ret;
          /* Failed decode may have overwritten part of RGB. */
          p->stats.bytes = 0;
        }
      slot->state = SLOT_FREE;
      pthread_mutex_unlock(&p->lock);
    }
  return NULL;
}

int k7_pipeline_start(struct k7_pipeline_s **out, size_t jpeg_capacity,
                      unsigned int scale, unsigned int delay_ms,
                      uint8_t *rgb, size_t rgb_capacity, bool detect_faces,
                      const struct k7_track_config_s *track)
{
  struct k7_pipeline_s *p;
  pthread_attr_t attr;
  struct sched_param scheduling = {0};
  int ret;
  *out = NULL;
  if (!jpeg_capacity || jpeg_capacity > 4 * 1024 * 1024 || !rgb ||
      (scale != 1 && scale != 2 && scale != 4 && scale != 8) ||
      delay_ms > 200 || rgb_capacity < (640 / scale) * (480 / scale) * 3)
    return -EINVAL;

#ifndef CONFIG_EXAMPLES_K7HOST_TRACK
  if (track) return -ENOTSUP;
#endif
  if (track && !detect_faces) return -EINVAL;
  if (detect_faces && scale != 4) return -EINVAL;
#ifndef CONFIG_EXAMPLES_K7HOST_YUNET
  if (detect_faces) return -ENOTSUP;
#endif
  p = calloc(1, sizeof(*p));
  if (!p) return -ENOMEM;
  p->storage = malloc(jpeg_capacity * K7_PIPE_SLOTS);
  if (!p->storage) { free(p); return -ENOMEM; }
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  p->gimbal_fd = -1;
  atomic_init(&p->motion_done, false);
  if (track)
    {
      int x=0, y=0;
      p->tracking=true;
      p->voice_control=track->voice_control;
      if(track->photo || track->voice_control) {
        p->photo=track->voice_control?k7_photo_create_native():k7_photo_create();
        if(!p->photo){ret=ENOMEM;goto free_storage;}
      }
      atomic_store(&g_track_halt, track->voice_control);
      if (track->voice_control) atomic_store(&g_voice_mode, 0);
      if (track->transmit)
        {
          p->gimbal_fd=gimbal_link_open(&x, &y);
          if (p->gimbal_fd < 0) { ret=-p->gimbal_fd; goto free_storage; }
        }
      ret=k7_track_init(&p->controller, track, x, y);
      if (ret < 0) { ret=-ret; goto free_storage; }
      p->stats.track_x=x; p->stats.track_y=y;
      printf("TRACK mode=%s limit=%d sign=%d,%d initial=%d,%d\n",
             track->transmit ? "run" : "dry",track->limit,
             track->sign_x,track->sign_y,x,y);
      printf("TRACK axes=%s axis_extent_required=1\n",
             track->axes==TRACK_X ? "x" : track->axes==TRACK_Y ? "y" : "xy");
    }
#endif
  p->stride = jpeg_capacity;
  p->rgb = rgb;
  p->rgb_capacity = rgb_capacity;
  p->scale = scale;
  p->delay_ms = delay_ms;
  for (unsigned int i = 0; i < K7_PIPE_SLOTS; i++)
    p->slots[i].data = p->storage + i * jpeg_capacity;

#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
  if (detect_faces)
    {
      p->yunet = k7_yunet_create();
      if (!p->yunet) { ret = ENOMEM; goto free_storage; }
    }
#endif
  ret = pthread_mutex_init(&p->lock, NULL);
  if (ret) goto free_storage;
  ret = pthread_cond_init(&p->ready, NULL);
  if (ret) goto destroy_mutex;
  ret = pthread_attr_init(&attr);
  if (ret) goto destroy_cond;
  ret = pthread_attr_setstacksize(&attr, 16384);
  if (ret) goto destroy_attr;
#ifdef __NuttX__
  /* Provisioning runs at 85 on CPU0. A continuously ready FIFO decoder
   * must not starve it; keep a lower fallback priority even with affinity.
   * USB refill remains at 100/192, ASR capture uses CPU1. */
  scheduling.sched_priority = 80;
  ret = pthread_attr_setschedpolicy(&attr, SCHED_FIFO);
  if (ret) goto destroy_attr;
  ret = pthread_attr_setschedparam(&attr, &scheduling);
  if (ret) goto destroy_attr;
  ret = pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);
  if (ret) goto destroy_attr;
#if defined(CONFIG_SMP) && CONFIG_SMP_NCPUS > 1
  {
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
#if CONFIG_SMP_NCPUS > 2
    CPU_SET(2, &cpus);
#else
    CPU_SET(1, &cpus);
#endif
    ret = pthread_attr_setaffinity_np(&attr, sizeof(cpus), &cpus);
    if (ret) goto destroy_attr;
  }
#endif
#else
  (void)scheduling;
#endif
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  if (track && track->preview)
    {
      ret=k7_preview_queue_start(&p->preview);
      if (ret < 0) { ret=-ret; goto destroy_attr; }
    }
#endif
  p->started_us = monotonic_us();
  ret = pthread_create(&p->thread, &attr, decode_worker, p);
  pthread_attr_destroy(&attr);
  if (ret)
    {
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
      int stopped=k7_preview_queue_stop(p->preview);
      if (stopped < 0) return stopped;
#endif
      goto destroy_cond;
    }
  *out = p;
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  if (p->voice_control)
    {
      pthread_mutex_lock(&g_voice_lock);
      g_voice_active = true;
      pthread_mutex_unlock(&g_voice_lock);
      puts("VOICE SESSION ready mode=0; awaiting explicit command");
    }
#endif
  return 0;

destroy_attr:
  pthread_attr_destroy(&attr);
destroy_cond:
  pthread_cond_destroy(&p->ready);
destroy_mutex:
  pthread_mutex_destroy(&p->lock);
free_storage:
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
  k7_yunet_destroy(p->yunet);
#endif
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  k7_photo_destroy(p->photo);
  gimbal_link_close(p->gimbal_fd);
#endif
  free(p->storage);
  free(p);
  return -ret;
}

void k7_pipeline_publish(struct k7_pipeline_s *p,
                         const uint8_t *jpeg, size_t bytes)
{
  int chosen = -1;
  uint64_t now = monotonic_us();
  pthread_mutex_lock(&p->lock);
  p->stats.published++;
  /* Only this capture task publishes, so there cannot be another WRITING
   * slot. One decoder owns at most one slot: a free or pending slot exists.
   */
  for (unsigned int i = 0; i < K7_PIPE_SLOTS; i++)
    if (p->slots[i].state == SLOT_FREE) { chosen = i; break; }
  if (chosen < 0)
    {
      for (unsigned int i = 0; i < K7_PIPE_SLOTS; i++)
        if (p->slots[i].state == SLOT_PENDING &&
            (chosen < 0 ||
             p->slots[i].sequence < p->slots[chosen].sequence))
          chosen = i;
    }
  if (!jpeg || bytes > p->stride || bytes < 4 || chosen < 0)
    {
      p->stats.dropped++;
      pthread_mutex_unlock(&p->lock);
      return;
    }
  struct slot_s *slot = &p->slots[chosen];
  if (slot->state == SLOT_PENDING)
    {
      p->pending--;
      p->stats.dropped++;
    }
  slot->state = SLOT_WRITING;
  slot->sequence = p->stats.published;
  pthread_mutex_unlock(&p->lock);

  memcpy(slot->data, jpeg, bytes);
  slot->bytes = bytes;
  slot->published_us = now;

  pthread_mutex_lock(&p->lock);
  slot->state = SLOT_PENDING;
  p->pending++;
  if (p->pending > p->stats.peak_pending)
    p->stats.peak_pending = p->pending;
  pthread_cond_signal(&p->ready);
  pthread_mutex_unlock(&p->lock);
}

int k7_pipeline_finish(struct k7_pipeline_s *p,
                       struct k7_pipeline_stats_s *stats)
{
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  if (p->voice_control)
    {
      pthread_mutex_lock(&g_voice_lock);
      g_voice_active = false;
      atomic_store(&g_voice_mode, 0);
      atomic_store(&g_track_halt, true);
      pthread_mutex_unlock(&g_voice_lock);
    }
#endif
  pthread_mutex_lock(&p->lock);
  p->stopping = true;
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  atomic_store(&p->motion_done, true);
#endif
  pthread_cond_signal(&p->ready);
  pthread_mutex_unlock(&p->lock);
  int ret = pthread_join(p->thread, NULL);
  /* A failed join must never free memory a live decoder could access. */
  if (ret) return -ret;
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  ret=k7_preview_queue_stop(p->preview);
  if (ret < 0) return ret;
#endif
  p->stats.elapsed_us = monotonic_us() - p->started_us;
  *stats = p->stats;
  pthread_cond_destroy(&p->ready);
  pthread_mutex_destroy(&p->lock);
#ifdef CONFIG_EXAMPLES_K7HOST_YUNET
  k7_yunet_destroy(p->yunet);
#endif
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  k7_photo_destroy(p->photo);
  gimbal_link_close(p->gimbal_fd);
#endif
  free(p->storage);
  free(p);
  return 0;
}

