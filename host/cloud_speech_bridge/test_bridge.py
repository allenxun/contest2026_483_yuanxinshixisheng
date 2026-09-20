import base64
import io
import json
import math
import os
import struct
import unittest
import wave
from unittest.mock import patch

from bridge import (
    BridgeError,
    ErrorCode,
    HttpResponse,
    MiMoConfig,
    MiMoSpeechBridge,
    pcm16le_to_wav,
)


def sine_pcm(rate: int, frames: int) -> bytes:
    values = [int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(frames)]
    return struct.pack(f"<{frames}h", *values)


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, body, timeout_seconds, max_response_bytes):
        self.calls.append((url, headers, body, timeout_seconds, max_response_bytes))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class BridgeTests(unittest.TestCase):
    def config(self, **overrides):
        values = dict(base_url="https://token-plan-cn.xiaomimimo.com/v1", api_key="test-secret")
        values.update(overrides)
        return MiMoConfig(**values)

    def test_config_comes_from_environment(self):
        with patch.dict(os.environ, {"MIMO_API_KEY": "runtime-only", "MIMO_BASE_URL": "https://example.test/v1"}, clear=True):
            cfg = MiMoConfig.from_env()
        self.assertEqual(cfg.api_key, "runtime-only")
        self.assertEqual(cfg.endpoint(), "https://example.test/v1/chat/completions")

    def test_missing_environment_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(BridgeError) as raised:
            MiMoConfig.from_env()
        self.assertEqual(raised.exception.code, ErrorCode.INVALID_CONFIG)

    def test_key_and_endpoint_families_cannot_be_mixed(self):
        with self.assertRaises(BridgeError) as token_plan:
            MiMoConfig("https://api.xiaomimimo.com/v1", "tp-placeholder").endpoint()
        self.assertEqual(token_plan.exception.code, ErrorCode.INVALID_CONFIG)
        with self.assertRaises(BridgeError) as metered:
            MiMoConfig("https://token-plan-cn.xiaomimimo.com/v1", "sk-placeholder").endpoint()
        self.assertEqual(metered.exception.code, ErrorCode.INVALID_CONFIG)

    def test_pcm_asr_is_wrapped_as_16k_mono_wav(self):
        reply = HttpResponse(200, b'{"choices":[{"message":{"content":"hello"}}]}')
        fake = FakeTransport(reply)
        result = MiMoSpeechBridge(self.config(), fake).transcribe(sine_pcm(16000, 320))
        self.assertEqual(result.text, "hello")
        url, headers, body, timeout, _ = fake.calls[0]
        self.assertEqual(url, "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer test-secret")
        self.assertGreater(timeout, 0)
        obj = json.loads(body)
        encoded = obj["messages"][0]["content"][0]["input_audio"]
        self.assertEqual(encoded["format"], "wav")
        with wave.open(io.BytesIO(base64.b64decode(encoded["data"])), "rb") as wav:
            self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (16000, 1, 2))

    def test_asr_rejects_wrong_rate_wav(self):
        wav = pcm16le_to_wav(sine_pcm(24000, 100), 24000)
        with self.assertRaises(BridgeError) as raised:
            MiMoSpeechBridge(self.config(), FakeTransport(None)).transcribe(wav, audio_format="wav")
        self.assertEqual(raised.exception.code, ErrorCode.INVALID_AUDIO)

    def test_tts_decodes_24k_wav_and_returns_16k_pcm(self):
        source = sine_pcm(24000, 2400)
        audio = base64.b64encode(pcm16le_to_wav(source, 24000)).decode("ascii")
        reply = HttpResponse(200, json.dumps({"choices": [{"message": {"audio": {"data": audio}}}]}).encode())
        fake = FakeTransport(reply)
        result = MiMoSpeechBridge(self.config(), fake).synthesize("联网成功")
        self.assertEqual((result.sample_rate_hz, result.channels), (16000, 1))
        self.assertEqual(len(result.pcm16le), 1600 * 2)
        with wave.open(io.BytesIO(result.as_wav()), "rb") as wav:
            self.assertEqual((wav.getframerate(), wav.getnframes()), (16000, 1600))
        request = json.loads(fake.calls[0][2])
        self.assertEqual(request["model"], "mimo-v2.5-tts")
        self.assertEqual(request["audio"], {"format": "wav", "voice": "白桦"})

    def test_http_errors_have_stable_mapping_and_do_not_leak_key(self):
        cases = [(401, ErrorCode.AUTH, False), (429, ErrorCode.RATE_LIMITED, True), (503, ErrorCode.UPSTREAM, True)]
        for status, code, retryable in cases:
            with self.subTest(status=status), self.assertRaises(BridgeError) as raised:
                MiMoSpeechBridge(self.config(), FakeTransport(HttpResponse(status, b"secret echo"))).synthesize("test")
            self.assertEqual(raised.exception.code, code)
            self.assertEqual(raised.exception.retryable, retryable)
            self.assertNotIn("test-secret", str(raised.exception))

    def test_timeout_mapping_is_preserved(self):
        failure = BridgeError(ErrorCode.TIMEOUT, "cloud speech request timed out", retryable=True)
        with self.assertRaises(BridgeError) as raised:
            MiMoSpeechBridge(self.config(), FakeTransport(failure)).synthesize("test")
        self.assertEqual(raised.exception.code, ErrorCode.TIMEOUT)

    def test_malformed_or_oversized_responses_are_rejected(self):
        with self.assertRaises(BridgeError) as malformed:
            MiMoSpeechBridge(self.config(), FakeTransport(HttpResponse(200, b"not json"))).synthesize("test")
        self.assertEqual(malformed.exception.code, ErrorCode.BAD_RESPONSE)
        cfg = self.config(max_response_bytes=4)
        with self.assertRaises(BridgeError) as oversized:
            MiMoSpeechBridge(cfg, FakeTransport(HttpResponse(200, b"12345"))).synthesize("test")
        self.assertEqual(oversized.exception.code, ErrorCode.OUTPUT_LIMIT)

    def test_tts_rejects_invalid_base64_and_wav(self):
        invalid_b64 = b'{"choices":[{"message":{"audio":{"data":"%%%"}}}]}'
        with self.assertRaises(BridgeError) as bad_b64:
            MiMoSpeechBridge(self.config(), FakeTransport(HttpResponse(200, invalid_b64))).synthesize("test")
        self.assertEqual(bad_b64.exception.code, ErrorCode.BAD_RESPONSE)
        encoded = base64.b64encode(b"not a wav").decode("ascii")
        invalid_wav = json.dumps({"choices": [{"message": {"audio": {"data": encoded}}}]}).encode()
        with self.assertRaises(BridgeError) as bad_wav:
            MiMoSpeechBridge(self.config(), FakeTransport(HttpResponse(200, invalid_wav))).synthesize("test")
        self.assertEqual(bad_wav.exception.code, ErrorCode.INVALID_AUDIO)


if __name__ == "__main__":
    unittest.main()
