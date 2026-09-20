"""Loopback-only HTTP facade for the host MiMo speech bridge."""

import argparse
import json
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from .bridge import BridgeError, ErrorCode, MiMoConfig, MiMoSpeechBridge
except ImportError:  # Direct execution: python host/cloud_speech_bridge/server.py
    from bridge import BridgeError, ErrorCode, MiMoConfig, MiMoSpeechBridge


DEFAULT_MAX_REQUEST_BYTES = 2_000_000


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _error_status(error):
    return {
        ErrorCode.INVALID_AUDIO: 400,
        ErrorCode.INVALID_CONFIG: 503,
        ErrorCode.AUTH: 502,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.TIMEOUT: 504,
        ErrorCode.NETWORK: 503,
        ErrorCode.UPSTREAM: 502,
        ErrorCode.BAD_RESPONSE: 502,
        ErrorCode.OUTPUT_LIMIT: 502,
    }.get(error.code, 500)


def make_handler(bridge, max_request_bytes=DEFAULT_MAX_REQUEST_BYTES):
    if max_request_bytes <= 0:
        raise ValueError("max_request_bytes must be positive")

    class SpeechHandler(BaseHTTPRequestHandler):
        server_version = "VelaVisionSpeechBridge/1"
        sys_version = ""

        def setup(self):
            BaseHTTPRequestHandler.setup(self)
            self.connection.settimeout(15.0)

        def log_message(self, _format, *args):
            # Disable the default request log. ASR/TTS bodies and query strings
            # must never reach console logs.
            return

        def _send(self, status, body, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # No Access-Control-Allow-* headers: browser CORS is deliberately off.
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, value):
            self._send(status, _json_bytes(value))

        def _fail(self, status, code, message, retryable=False):
            self._send_json(status, {
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": bool(retryable),
                }
            })

        def _read_body(self):
            if self.headers.get("Transfer-Encoding"):
                self._fail(400, "invalid_request", "chunked request bodies are not supported")
                return None
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._fail(411, "length_required", "Content-Length is required")
                return None
            try:
                length = int(raw_length, 10)
            except ValueError:
                self._fail(400, "invalid_request", "Content-Length is invalid")
                return None
            if length < 0:
                self._fail(400, "invalid_request", "Content-Length is invalid")
                return None
            if length > max_request_bytes:
                self._fail(413, "body_too_large", "request body exceeds limit")
                return None
            body = self.rfile.read(length)
            if len(body) != length:
                self._fail(400, "invalid_request", "request body is truncated")
                return None
            return body

        def do_GET(self):
            if self.path != "/health":
                self._fail(404, "not_found", "route not found")
                return
            self._send_json(200, {
                "status": "ok",
                "service": "velavision-cloud-speech-bridge",
                "ready": True,
                "asr": True,
                "tts": True,
                "output": {"sample_rate_hz": 16000, "channels": 1, "format": "pcm16le"},
            })

        def do_POST(self):
            try:
                if self.path == "/v1/asr":
                    self._post_asr()
                elif self.path == "/v1/tts":
                    self._post_tts()
                else:
                    self._fail(404, "not_found", "route not found")
            except BridgeError as exc:
                self._fail(_error_status(exc), exc.code.value, str(exc), exc.retryable)
            except Exception:
                # Never expose exception details; they could contain a response or token.
                self._fail(500, "internal", "internal speech bridge failure")

        def do_OPTIONS(self):
            self._fail(405, "method_not_allowed", "CORS preflight is disabled")

        def do_PUT(self):
            self._fail(405, "method_not_allowed", "method is not supported")

        def do_PATCH(self):
            self._fail(405, "method_not_allowed", "method is not supported")

        def do_DELETE(self):
            self._fail(405, "method_not_allowed", "method is not supported")

        def _post_asr(self):
            media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type == "audio/wav" or media_type == "audio/x-wav":
                audio_format = "wav"
            elif media_type in ("application/octet-stream", "audio/pcm"):
                audio_format = "pcm16le"
            else:
                self._fail(415, "unsupported_media_type", "ASR requires audio/wav or raw PCM16LE")
                return
            body = self._read_body()
            if body is None:
                return
            result = bridge.transcribe(body, audio_format=audio_format)
            self._send_json(200, {"text": result.text})

        def _post_tts(self):
            media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                self._fail(415, "unsupported_media_type", "TTS requires application/json")
                return
            body = self._read_body()
            if body is None:
                return
            try:
                request = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._fail(400, "invalid_json", "request body must be valid UTF-8 JSON")
                return
            if not isinstance(request, dict) or not isinstance(request.get("text"), str):
                self._fail(400, "invalid_request", "TTS JSON requires string field text")
                return
            if request.get("format", "wav") != "wav" or request.get("sample_rate", 16000) != 16000 or request.get("channels", 1) != 1:
                self._fail(400, "unsupported_audio_format", "TTS output must be 16 kHz mono PCM16 WAV")
                return
            voice = request.get("voice")
            if voice is not None and not isinstance(voice, str):
                self._fail(400, "invalid_request", "TTS voice must be a string")
                return
            result = bridge.synthesize(request["text"], voice=voice)
            self._send(200, result.as_wav(), "audio/wav")

    return SpeechHandler


def create_server(bridge, port=18086, max_request_bytes=DEFAULT_MAX_REQUEST_BYTES):
    """Create a server that is unconditionally bound to IPv4 loopback."""
    return _ThreadingHTTPServer(
        ("127.0.0.1", port),
        make_handler(bridge, max_request_bytes=max_request_bytes),
    )


def main():
    parser = argparse.ArgumentParser(description="VelaVision loopback MiMo speech bridge")
    parser.add_argument("--port", type=int, default=18086)
    parser.add_argument("--max-request-bytes", type=int, default=DEFAULT_MAX_REQUEST_BYTES)
    args = parser.parse_args()
    config = MiMoConfig.from_env()
    server = create_server(MiMoSpeechBridge(config), args.port, args.max_request_bytes)
    print("VelaVision speech bridge listening on http://127.0.0.1:%d" % server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
