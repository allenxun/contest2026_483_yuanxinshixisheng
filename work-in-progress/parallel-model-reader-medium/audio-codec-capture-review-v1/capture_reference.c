#include "capture_reference.h"
#include <string.h>
/* Source 101: ES8388 User Guide 2011-06-17 p26.
 * Source 102: same guide p20 pair2 alternative.
 * Source 103: frozen Linux es8323.c S16/I2S and ADC data-map fields.
 * Source 104: same guide p27 standby reference.
 * This is a review sequence, NOT a board initialization implementation.
 * Known-baseline reset, settling, ALC state, hardware readback and shutdown
 * ownership remain missing. No REVIEW_ALL or TARGET_REVIEWED promotion. */
void k7_capture16_reference(struct kc_plan *p)
{
 static const struct kc_step steps[] = {
  {KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,101,0x08,0x00,0,0},
  {KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,101,0x02,0xf3,0,0},
  {KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,101,0x2b,0x80,0,0},
  {KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,101,0x00,0x05,0,0},
  {KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,101,0x01,0x40,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x03,0x00,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,102,0x0a,0xf0,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,102,0x0b,0x82,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x09,0x00,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,103,0x0c,0x0c,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x0d,0x02,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x10,0x00,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x11,0x00,0,0},
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x0f,0x30,0,0},
  /* Guide says choose ALC if needed here; deliberately unresolved. */
  {KC_WRITE,KC_CAPTURE,KC_REFERENCE_ONLY,101,0x02,0x55,0,0}
 };
 if (!p) return;
 memset(p,0,sizeof(*p));
 p->mode=KC_HARDWARE;p->address=0x10;p->sample_rate=16000;
 p->mclk=4096000;p->bclk=512000;p->slots=2;p->slot_bits=16;
 p->count=sizeof(steps)/sizeof(steps[0]);
 memcpy(p->steps,steps,sizeof(steps));
}
