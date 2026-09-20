"""Minimal Alibaba Cloud Bailian ASR/TTS adapter."""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx
from audio import k7_pcm_from_audio
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_NATIVE_BASE_URL = "https://dashscope.aliyuncs.com"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class SpeechServiceError(RuntimeError):
    """Safe error raised to the HTTP layer."""

    def __init__(self, message: str, *, configuration: bool = False) -> None:
        super().__init__(message)
        self.configuration = configuration


def _required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("replace-with-"):
        raise SpeechServiceError("Speech service configuration is missing", configuration=True)
    return value


def _compatible_base_url() -> str:
    return os.getenv("ALIYUN_COMPATIBLE_BASE_URL", _DEFAULT_COMPATIBLE_BASE_URL).strip() or (
        _DEFAULT_COMPATIBLE_BASE_URL
    )


def _native_base_url() -> str:
    return os.getenv("ALIYUN_NATIVE_BASE_URL", _DEFAULT_NATIVE_BASE_URL).strip() or (
        _DEFAULT_NATIVE_BASE_URL
    )


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def _post_json(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, headers=_headers(api_key), json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SpeechServiceError("Alibaba Cloud speech request failed") from exc
    if not isinstance(data, dict):
        raise SpeechServiceError("Alibaba Cloud speech response was invalid")
    return data


async def transcribe_wav(audio: bytes) -> str:
    """调用阿里云 ASR 并返回识别文字。"""
    api_key = _required_setting("ALIYUN_API_KEY")
    model = _required_setting("ALIYUN_ASR_MODEL")
    data_uri = "data:audio/wav;base64," + base64.b64encode(audio).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": data_uri}}
                ],
            }
        ],
        "stream": False,
    }
    data = await _post_json(
        f"{_compatible_base_url().rstrip('/')}/chat/completions",
        api_key,
        payload,
    )
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise SpeechServiceError("Alibaba Cloud ASR response was invalid") from exc
    if not text:
        raise SpeechServiceError("Alibaba Cloud ASR returned no text")
    return text


async def synthesize_pcm(text: str) -> bytes:
    """调用阿里云 TTS，返回 16 kHz / mono / S16LE 裸 PCM。"""
    api_key = _required_setting("ALIYUN_API_KEY")
    model = _required_setting("ALIYUN_TTS_MODEL")
    voice = _required_setting("ALIYUN_TTS_VOICE")
    data = await _post_json(
        f"{_native_base_url().rstrip('/')}/api/v1/services/audio/tts/SpeechSynthesizer",
        api_key,
        {
            "model": model,
            "input": {
                "text": text,
                "voice": voice,
                "format": "wav",
                "sample_rate": 16000,
            },
        },
    )
    try:
        audio_url = data["output"]["audio"]["url"]
        if not isinstance(audio_url, str) or not audio_url:
            raise TypeError
    except (KeyError, TypeError) as exc:
        raise SpeechServiceError("Alibaba Cloud TTS response was invalid") from exc

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(audio_url)
            response.raise_for_status()
            audio = response.content
    except httpx.HTTPError as exc:
        raise SpeechServiceError("Alibaba Cloud TTS audio download failed") from exc
    if not audio:
        raise SpeechServiceError("Alibaba Cloud TTS returned empty audio")
    try:
        return k7_pcm_from_audio(audio)
    except ValueError as exc:
        raise SpeechServiceError("Alibaba Cloud TTS returned invalid PCM audio") from exc
