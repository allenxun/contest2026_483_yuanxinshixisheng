"""Host-side Xiaomi MiMo ASR/TTS bridge candidate.

The module keeps credentials in process memory only.  Callers inject a
transport in tests; production use can select :class:`UrllibTransport`.
"""

import base64
import io
import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
import wave
from enum import Enum
from typing import Any, Mapping, Optional


class ErrorCode(str, Enum):
    INVALID_AUDIO = "invalid_audio"
    INVALID_CONFIG = "invalid_config"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UPSTREAM = "upstream"
    BAD_RESPONSE = "bad_response"
    OUTPUT_LIMIT = "output_limit"


class BridgeError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class HttpResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body


class UrllibTransport:
    """Bounded synchronous HTTPS transport for the host-side candidate."""

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read(max_response_bytes + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            # Read only a bounded error body and never expose it: services may echo data.
            exc.read(min(max_response_bytes, 4096))
            return HttpResponse(exc.code, b"")
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError):
                raise BridgeError(ErrorCode.TIMEOUT, "cloud speech request timed out", retryable=True)
            raise BridgeError(ErrorCode.NETWORK, "cloud speech network request failed", retryable=True)
        if len(payload) > max_response_bytes:
            raise BridgeError(ErrorCode.OUTPUT_LIMIT, "cloud speech response exceeds limit")
        return HttpResponse(status, payload)


class MiMoConfig:
    def __init__(
        self,
        base_url,
        api_key,
        timeout_seconds=20.0,
        asr_model="mimo-v2.5-asr",
        tts_model="mimo-v2.5-tts",
        voice="白桦",
        max_request_bytes=8_000_000,
        max_response_bytes=12_000_000,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.asr_model = asr_model
        self.tts_model = tts_model
        self.voice = voice
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_env(cls) -> "MiMoConfig":
        api_key = os.environ.get("MIMO_API_KEY", "")
        base_url = os.environ.get("MIMO_BASE_URL", "")
        if not api_key or not base_url:
            raise BridgeError(
                ErrorCode.INVALID_CONFIG,
                "MIMO_API_KEY and MIMO_BASE_URL are required",
            )
        return cls(base_url=base_url, api_key=api_key)

    def endpoint(self) -> str:
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise BridgeError(ErrorCode.INVALID_CONFIG, "MIMO_BASE_URL must be an HTTPS origin or /v1 URL")
        if parsed.query or parsed.fragment:
            raise BridgeError(ErrorCode.INVALID_CONFIG, "MIMO_BASE_URL must not contain query or fragment")
        host = parsed.hostname.lower()
        if self.api_key.startswith("tp-") and host == "api.xiaomimimo.com":
            raise BridgeError(ErrorCode.INVALID_CONFIG, "Token Plan key requires its Token Plan regional endpoint")
        if self.api_key.startswith("sk-") and host.startswith("token-plan-"):
            raise BridgeError(ErrorCode.INVALID_CONFIG, "pay-as-you-go key cannot use a Token Plan endpoint")
        path = parsed.path.rstrip("/")
        if not path:
            path = "/v1"
        if path.endswith("/chat/completions"):
            endpoint_path = path
        else:
            endpoint_path = path + "/chat/completions"
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, endpoint_path, "", ""))


class AsrResult:
    def __init__(self, text):
        self.text = text


class TtsResult:
    def __init__(self, pcm16le, sample_rate_hz=16_000, channels=1):
        self.pcm16le = pcm16le
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels

    def as_wav(self) -> bytes:
        return pcm16le_to_wav(self.pcm16le, self.sample_rate_hz)


def pcm16le_to_wav(pcm: bytes, sample_rate_hz: int = 16_000) -> bytes:
    if len(pcm) % 2:
        raise BridgeError(ErrorCode.INVALID_AUDIO, "PCM16LE byte count must be even")
    if sample_rate_hz <= 0:
        raise BridgeError(ErrorCode.INVALID_AUDIO, "sample rate must be positive")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        wav.writeframes(pcm)
    return output.getvalue()


def _read_mono_pcm16_wav(payload: bytes, *, required_rate: Optional[int] = None):
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise BridgeError(ErrorCode.INVALID_AUDIO, "WAV must be mono uncompressed PCM16")
            rate = wav.getframerate()
            if required_rate is not None and rate != required_rate:
                raise BridgeError(ErrorCode.INVALID_AUDIO, f"WAV sample rate must be {required_rate} Hz")
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise BridgeError(ErrorCode.INVALID_AUDIO, "invalid WAV container") from exc
    if len(frames) % 2:
        raise BridgeError(ErrorCode.INVALID_AUDIO, "WAV PCM payload is truncated")
    return rate, frames


def _resample_mono_pcm16_linear(pcm: bytes, source_rate: int, target_rate: int = 16_000) -> bytes:
    """Bounded offline resampling for the host bridge.

    This is deliberately stateless because the current MiMo call is non-streaming.
    The K7 receives exactly mono S16LE at ``target_rate``.
    """
    if source_rate <= 0 or target_rate <= 0 or len(pcm) % 2:
        raise BridgeError(ErrorCode.INVALID_AUDIO, "invalid PCM resampling parameters")
    count = len(pcm) // 2
    if count == 0 or source_rate == target_rate:
        return pcm
    samples = struct.unpack(f"<{count}h", pcm)
    output_count = max(1, (count * target_rate) // source_rate)
    output = bytearray(output_count * 2)
    for out_index in range(output_count):
        numerator = out_index * source_rate
        left = numerator // target_rate
        fraction = numerator % target_rate
        if left >= count - 1:
            value = samples[-1]
        else:
            a = samples[left]
            b = samples[left + 1]
            value = (a * (target_rate - fraction) + b * fraction + target_rate // 2) // target_rate
        struct.pack_into("<h", output, out_index * 2, max(-32768, min(32767, value)))
    return bytes(output)


class MiMoSpeechBridge:
    def __init__(self, config: MiMoConfig, transport=None):
        self._config = config
        self._transport = transport or UrllibTransport()
        self._endpoint = config.endpoint()

    def transcribe(self, audio: bytes, *, audio_format: str = "pcm16le") -> AsrResult:
        if audio_format == "pcm16le":
            wav = pcm16le_to_wav(audio, 16_000)
        elif audio_format == "wav":
            _read_mono_pcm16_wav(audio, required_rate=16_000)
            wav = audio
        else:
            raise BridgeError(ErrorCode.INVALID_AUDIO, "ASR accepts pcm16le or wav")
        encoded = base64.b64encode(wav).decode("ascii")
        request = {
            "model": self._config.asr_model,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "input_audio",
                    "input_audio": {"data": encoded, "format": "wav"},
                }],
            }],
            "asr_options": {"language": "zh"},
            "stream": False,
        }
        result = self._call(request)
        try:
            text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BridgeError(ErrorCode.BAD_RESPONSE, "ASR response has no transcript") from exc
        if not isinstance(text, str) or not text.strip():
            raise BridgeError(ErrorCode.BAD_RESPONSE, "ASR transcript is empty")
        return AsrResult(text=text)

    def synthesize(self, text: str, *, voice: Optional[str] = None) -> TtsResult:
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 8192:
            raise BridgeError(ErrorCode.INVALID_CONFIG, "TTS text must contain 1..8192 UTF-8 bytes")
        selected_voice = voice or self._config.voice
        request = {
            "model": self._config.tts_model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"format": "wav", "voice": selected_voice},
            "stream": False,
        }
        result = self._call(request)
        try:
            encoded = result["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BridgeError(ErrorCode.BAD_RESPONSE, "TTS response has no audio") from exc
        if not isinstance(encoded, str):
            raise BridgeError(ErrorCode.BAD_RESPONSE, "TTS audio is not Base64 text")
        try:
            wav = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise BridgeError(ErrorCode.BAD_RESPONSE, "TTS audio Base64 is invalid") from exc
        rate, pcm = _read_mono_pcm16_wav(wav)
        if rate < 8_000 or rate > 48_000:
            raise BridgeError(ErrorCode.INVALID_AUDIO, "TTS WAV sample rate is unsupported")
        pcm16 = _resample_mono_pcm16_linear(pcm, rate, 16_000)
        return TtsResult(pcm16le=pcm16)

    def _call(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        body = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self._config.max_request_bytes:
            raise BridgeError(ErrorCode.OUTPUT_LIMIT, "cloud speech request exceeds limit")
        response = self._transport.post_json(
            self._endpoint,
            {
                "Authorization": "Bearer " + self._config.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body,
            self._config.timeout_seconds,
            self._config.max_response_bytes,
        )
        self._raise_http(response.status)
        if len(response.body) > self._config.max_response_bytes:
            raise BridgeError(ErrorCode.OUTPUT_LIMIT, "cloud speech response exceeds limit")
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(ErrorCode.BAD_RESPONSE, "cloud speech response is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise BridgeError(ErrorCode.BAD_RESPONSE, "cloud speech response must be a JSON object")
        return decoded

    @staticmethod
    def _raise_http(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in (401, 403):
            raise BridgeError(ErrorCode.AUTH, "cloud speech authentication failed")
        if status == 429:
            raise BridgeError(ErrorCode.RATE_LIMITED, "cloud speech rate limit reached", retryable=True)
        if status in (408, 504):
            raise BridgeError(ErrorCode.TIMEOUT, "cloud speech upstream timed out", retryable=True)
        if 500 <= status < 600:
            raise BridgeError(ErrorCode.UPSTREAM, "cloud speech upstream failed", retryable=True)
        raise BridgeError(ErrorCode.UPSTREAM, f"cloud speech HTTP status {status}")
