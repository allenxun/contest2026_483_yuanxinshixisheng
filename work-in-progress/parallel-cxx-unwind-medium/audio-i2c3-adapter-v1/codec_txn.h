#ifndef CODEC_TXN_H
#define CODEC_TXN_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define KC_MAX_STEPS 64u
#define KC_MAX_READ_RULES 16u
enum kc_status { KC_OK, KC_PENDING, KC_BUSY, KC_NOT_READY, KC_INVALID,
 KC_IO, KC_SHORT, KC_TIMEOUT, KC_CANCELLED, KC_READBACK, KC_CLOCK,
 KC_STALE, KC_EXHAUSTED, KC_DELAY_ERROR };
enum kc_state { KC_OFF, KC_POWERING, KC_INITIALIZING, KC_PREPARING,
 KC_READY, KC_STOPPING, KC_ERROR };
enum kc_mode { KC_HARDWARE, KC_SIMULATION };
enum kc_evidence { KC_UNREVIEWED, KC_REFERENCE_ONLY, KC_TARGET_REVIEWED, KC_SIM_ONLY };
enum kc_kind { KC_WRITE, KC_READ_VERIFY, KC_DELAY };
enum kc_stage { KC_INIT, KC_CAPTURE };
enum kc_phase { KC_PHASE_NONE, KC_PHASE_POWER, KC_PHASE_CLOCK,
 KC_PHASE_STEP, KC_PHASE_CAPTURE, KC_PHASE_READY };
enum kc_control { KC_POWER_PREPARE, KC_CAPTURE_PREPARE, KC_QUIESCE };
enum { KC_REVIEW_IDENTITY=1u, KC_REVIEW_RAILS=2u, KC_REVIEW_CLOCK=4u,
 KC_REVIEW_FORMAT=8u, KC_REVIEW_ANALOG=16u, KC_REVIEW_STOP=32u,
 KC_REVIEW_ALL=63u };
struct kc_step {
 enum kc_kind kind; enum kc_stage stage; enum kc_evidence evidence;
 uint16_t source_id; /* local provenance table, nonzero; not a security boundary */
 uint8_t reg,value,mask; uint32_t delay_ms;
};
struct kc_read_rule { uint8_t reg,allowed_mask; enum kc_evidence evidence; uint16_t source_id; };
struct kc_plan {
 enum kc_mode mode; unsigned reviews;
 uint8_t address; uint32_t sample_rate,mclk,bclk;
 uint8_t slots,slot_bits;
 size_t count,read_count;
 struct kc_step steps[KC_MAX_STEPS];
 struct kc_read_rule reads[KC_MAX_READ_RULES];
};
struct kc_io_result { int error; size_t tx_done,rx_done; };
/* Serialized service task only. No callback may retain stack buffers after return.
 * No callbacks may longjmp. Bus exceptions/OS errors must be translated.
 * Bus reports actual byte counts separately: write(reg,value) TX=2/RX=0;
 * combined read TX register=1/RX value=1. A sum of two bytes is insufficient.
 * The adapter checks messages, STOP/restart and lengths.
 * Absolute deadline uses the SAME monotonic clock as now_ms. Lower layer must
 * enforce it; this layer can only reject a result AFTER a blocking call returns.
 * control(KC_QUIESCE)==0 means all old I/O/DMA exited, capture disabled and
 * amplifier kept off. Nonzero retains lease. It is never merely cancel sent.
 */
struct kc_port {
 void *ctx;
 uint64_t (*now_ms)(void *);
 struct kc_io_result (*write)(void *,uint8_t,const uint8_t *,size_t,uint64_t);
 struct kc_io_result (*read)(void *,uint8_t,uint8_t,uint8_t *,uint64_t);
 int (*delay_ms)(void *,uint32_t,uint64_t);
 int (*clock_ready)(void *,uint32_t,uint32_t,uint32_t,uint64_t);
 int (*control)(void *,enum kc_control,uint64_t,uint64_t);
 enum kc_mode mode; /* must match plan; fake plans cannot use a hardware port */
};
/* Fixed storage, no malloc. Do not copy after start or re-init a live context.
 * All calls serialized; only cancel may be called reentrantly from a callback.
 * For cross-thread cancellation, post a message to this owner task. Not an SMP
 * lock or a shared I2C bus arbiter; all codec clients must use this one owner.
 */
struct kc_context {
 struct kc_port port;struct kc_plan plan;
 enum kc_state state;enum kc_status result,cleanup_result;
 enum kc_phase phase,failed_phase;
 uint64_t id,next_id,deadline,last_time;
 size_t index,failed_step,tx_done,rx_done;
 int port_error,cleanup_port_error;
 bool in_call,cancel,clock_checked,clock_fault;
};
enum kc_status kc_init(struct kc_context *,const struct kc_port *);
enum kc_status kc_start(struct kc_context *,const struct kc_plan *,uint64_t absolute_deadline,uint64_t *id);
enum kc_status kc_poll(struct kc_context *);
enum kc_status kc_cancel(struct kc_context *,uint64_t id);
enum kc_status kc_stop(struct kc_context *,uint64_t id);
/* One bounded cleanup attempt per call; a new deadline can be supplied even
 * after transaction timeout. Success is actual quiescence, not elapsed time. */
enum kc_status kc_cleanup(struct kc_context *,uint64_t id,uint64_t absolute_deadline);
enum kc_status kc_reset_error(struct kc_context *);
/* Source reference only; incomplete clock/format/analog/stop review. start
 * MUST return KC_NOT_READY without any bus or control access. */
void kc_es8388_reference(struct kc_plan *);
#endif
