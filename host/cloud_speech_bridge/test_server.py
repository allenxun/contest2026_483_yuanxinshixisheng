import http.client
import json
import threading
import unittest

from bridge import AsrResult, BridgeError, ErrorCode, TtsResult, pcm16le_to_wav
from server import create_server


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.failure = None

    def transcribe(self, audio, audio_format="pcm16le"):
        self.calls.append(("asr", audio_format, audio))
        if self.failure:
            raise self.failure
        return AsrResult("你好联网")

    def synthesize(self, text, voice=None):
        self.calls.append(("tts", text, voice))
        if self.failure:
            raise self.failure
        return TtsResult(b"\x01\x00\x02\x00")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.bridge = FakeBridge()
        self.server = create_server(self.bridge, port=0, max_request_bytes=128)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = (response.status, dict(response.getheaders()), payload)
        connection.close()
        return result

    def test_health_is_loopback_and_has_no_cors(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, headers, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        health = json.loads(body)
        self.assertEqual(health["status"], "ok")
        self.assertEqual((health["ready"], health["asr"], health["tts"]), (True, True, True))
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_asr_accepts_wav_and_raw_pcm(self):
        wav = pcm16le_to_wav(b"\x01\x00\x02\x00")
        status, _, body = self.request("POST", "/v1/asr", wav, {"Content-Type": "audio/wav"})
        self.assertEqual((status, json.loads(body)["text"]), (200, "你好联网"))
        self.assertEqual(self.bridge.calls[-1][1], "wav")
        status, _, _ = self.request(
            "POST", "/v1/asr", b"\x03\x00", {"Content-Type": "application/octet-stream"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.bridge.calls[-1][1], "pcm16le")

    def test_tts_returns_16k_mono_wav_and_forwards_voice(self):
        request = json.dumps({
            "text": "联网成功", "voice": "白桦", "format": "wav",
            "sample_rate": 16000, "channels": 1,
        }).encode("utf-8")
        status, headers, body = self.request("POST", "/v1/tts", request, {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertTrue(body.startswith(b"RIFF"))
        self.assertEqual(self.bridge.calls[-1], ("tts", "联网成功", "白桦"))

        bad = json.dumps({"text": "联网成功", "sample_rate": 24000}).encode("utf-8")
        status, _, body = self.request("POST", "/v1/tts", bad, {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "unsupported_audio_format")

    def test_body_limit_and_bad_media_type_are_stable_json(self):
        status, _, body = self.request(
            "POST", "/v1/asr", b"x" * 129, {"Content-Type": "application/octet-stream"}
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body)["error"]["code"], "body_too_large")
        status, _, body = self.request("POST", "/v1/asr", b"x", {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(json.loads(body)["error"]["code"], "unsupported_media_type")

    def test_bridge_error_mapping_and_no_upstream_details(self):
        self.bridge.failure = BridgeError(ErrorCode.TIMEOUT, "cloud speech upstream timed out", retryable=True)
        request = json.dumps({"text": "hello"}).encode("utf-8")
        status, _, body = self.request("POST", "/v1/tts", request, {"Content-Type": "application/json"})
        error = json.loads(body)["error"]
        self.assertEqual((status, error["code"], error["retryable"]), (504, "timeout", True))

    def test_invalid_json_options_and_unknown_routes_are_rejected(self):
        status, headers, body = self.request("OPTIONS", "/v1/tts")
        self.assertEqual(status, 405)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(json.loads(body)["error"]["code"], "method_not_allowed")
        status, _, body = self.request("POST", "/v1/tts", b"{", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_json")
        status, _, body = self.request("GET", "/missing")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
