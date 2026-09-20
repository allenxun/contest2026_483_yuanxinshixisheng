"""K7 PCM / WAV helpers.

Board capture and playback are 16 kHz, mono, 16-bit signed little-endian PCM.
HTTP still uses a file upload, so the same PCM is wrapped with a 44-byte WAV header.
"""

from __future__ import annotations

import array
import struct

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # S16LE
WAV_HEADER_SIZE = 44


def wrap_pcm_s16le_as_wav(
    pcm: bytes,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> bytes:
    """Prefix raw S16LE PCM with a canonical 44-byte PCM WAV header."""
    if len(pcm) % SAMPLE_WIDTH:
        raise ValueError("PCM length must be a multiple of 2 bytes")
    byte_rate = sample_rate * channels * SAMPLE_WIDTH
    block_align = channels * SAMPLE_WIDTH
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        channels,
        sample_rate,
        byte_rate,
        block_align,
        SAMPLE_WIDTH * 8,
        b"data",
        data_size,
    )
    assert len(header) == WAV_HEADER_SIZE
    return header + pcm


def is_riff_wave(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _iter_wav_chunks(wav: bytes):
    offset = 12
    while offset + 8 <= len(wav):
        chunk_id = wav[offset : offset + 4]
        claimed = struct.unpack_from("<I", wav, offset + 4)[0]
        start = offset + 8
        available = len(wav) - start
        size = min(claimed, available)
        yield chunk_id, wav[start : start + size]
        if claimed > available:
            return
        offset = start + claimed + (claimed % 2)


def _parse_wav_s16(wav: bytes) -> tuple[bytes, int, int]:
    """Return (interleaved S16LE samples, sample_rate, channels)."""
    if not is_riff_wave(wav):
        raise ValueError("Not a WAV file")
    fmt: bytes | None = None
    pcm: bytes | None = None
    for chunk_id, payload in _iter_wav_chunks(wav):
        if chunk_id == b"fmt " and fmt is None:
            fmt = payload
        elif chunk_id == b"data" and pcm is None:
            pcm = payload
    if fmt is None or len(fmt) < 16:
        raise ValueError("WAV file has no fmt chunk")
    if pcm is None:
        raise ValueError("WAV file has no data chunk")
    audio_format, channels, sample_rate, _byte_rate, _block_align, bits = struct.unpack_from(
        "<HHIIHH", fmt, 0
    )
    if audio_format != 1 or bits != 16:
        raise ValueError("WAV must be 16-bit PCM")
    if channels < 1:
        raise ValueError("WAV has invalid channel count")
    frame_bytes = channels * SAMPLE_WIDTH
    pcm = pcm[: len(pcm) - (len(pcm) % frame_bytes)]
    if not pcm:
        raise ValueError("WAV data chunk is empty")
    return pcm, sample_rate, channels


def _to_mono_s16(pcm: bytes, channels: int) -> bytes:
    if channels == 1:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    mono = array.array("h")
    for i in range(0, len(samples), channels):
        frame = samples[i : i + channels]
        mono.append(int(sum(frame) / len(frame)))
    return mono.tobytes()


def _resample_s16_mono(pcm: bytes, src_rate: int, dst_rate: int = SAMPLE_RATE) -> bytes:
    if src_rate == dst_rate:
        return pcm
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError("Invalid sample rate")
    samples = array.array("h")
    samples.frombytes(pcm)
    n_in = len(samples)
    if n_in == 1:
        return pcm
    n_out = max(1, round(n_in * dst_rate / src_rate))
    out = array.array("h")
    scale = (n_in - 1) / (n_out - 1) if n_out > 1 else 0.0
    for i in range(n_out):
        pos = i * scale
        i0 = int(pos)
        i1 = min(i0 + 1, n_in - 1)
        frac = pos - i0
        out.append(int(round(samples[i0] * (1.0 - frac) + samples[i1] * frac)))
    return out.tobytes()


def k7_pcm_from_audio(data: bytes) -> bytes:
    """Normalize any supported upload to 16 kHz mono S16LE PCM."""
    if is_riff_wave(data):
        pcm, sample_rate, channels = _parse_wav_s16(data)
        pcm = _to_mono_s16(pcm, channels)
        return _resample_s16_mono(pcm, sample_rate)
    if len(data) % SAMPLE_WIDTH:
        raise ValueError("PCM length must be a multiple of 2 bytes")
    return data


def asr_upload_to_wav(data: bytes) -> bytes:
    """Turn an ASR upload into a 16 kHz mono S16LE WAV for the cloud ASR API.

    WAV files are decoded and converted if needed. Anything else is treated as
    K7 raw PCM (16 kHz / mono / S16LE) and wrapped with a 44-byte header.
    """
    return wrap_pcm_s16le_as_wav(k7_pcm_from_audio(data))


def tts_bytes_to_wav(data: bytes) -> bytes:
    """Normalize TTS bytes to a 16 kHz mono S16LE WAV for the board."""
    return wrap_pcm_s16le_as_wav(k7_pcm_from_audio(data))


def pcm_from_wav(wav: bytes) -> bytes:
    """Return 16 kHz mono S16LE PCM from a WAV (tolerates streaming-style headers)."""
    return k7_pcm_from_audio(wav)
