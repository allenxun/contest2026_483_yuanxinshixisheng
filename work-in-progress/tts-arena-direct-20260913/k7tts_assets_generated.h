#pragma once
#include <stdint.h>

/* Bound to k7tts.romfs SHA-256
 * 8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f.
 * genromfs places vits.ort data at the audited 0x730 byte offset. */
#define K7_TTS_ROM_ADDRESS UINT64_C(0x96000000)
#define K7_TTS_ROM_BYTES UINT32_C(33235968)
#define K7_TTS_ROM_CRC32 UINT32_C(0x9efc1996)
#define K7_TTS_MODEL_OFFSET UINT32_C(0x730)
#define K7_TTS_MODEL_BYTES UINT32_C(31190816)
