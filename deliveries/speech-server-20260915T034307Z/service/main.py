"""HTTP API for the K7 cloud speech service."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from aliyun_speech import SpeechServiceError, synthesize_pcm, transcribe_wav
from audio import asr_upload_to_wav

MAX_AUDIO_BYTES = 10 * 1024 * 1024
logger = logging.getLogger("speech-service")

app = FastAPI(title="K7 Cloud Speech Service")


class TTSRequest(BaseModel):
    text: str


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.error(
            "path=%s status=500 elapsed_ms=%.1f",
            request.url.path,
            (time.perf_counter() - started) * 1000,
        )
        raise
    logger.info(
        "path=%s status=%d elapsed_ms=%.1f",
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return _error(400, "Invalid request parameters")


@app.exception_handler(Exception)
async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
    return _error(500, "Internal server error")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/asr", response_model=None)
async def asr(audio: UploadFile) -> dict[str, object] | JSONResponse:
    content = await audio.read(MAX_AUDIO_BYTES + 1)
    await audio.close()
    if len(content) > MAX_AUDIO_BYTES:
        return _error(413, "Audio file is too large")
    if not content:
        return _error(400, "Audio file is empty")
    try:
        wav = asr_upload_to_wav(content)
    except ValueError:
        return _error(400, "Audio must be 16 kHz mono S16LE PCM")
    try:
        text = await transcribe_wav(wav)
    except SpeechServiceError as exc:
        return _error(500 if exc.configuration else 502, str(exc) if exc.configuration else "ASR service failed")
    return {"success": True, "text": text}


@app.post("/tts", response_model=None)
async def tts(payload: TTSRequest) -> Response:
    text = payload.text.strip()
    if not text or len(text) > 1000:
        return _error(400, "Text must contain 1 to 1000 characters")
    try:
        pcm = await synthesize_pcm(text)
    except SpeechServiceError as exc:
        return _error(500 if exc.configuration else 502, str(exc) if exc.configuration else "TTS service failed")
    return Response(
        content=pcm,
        media_type="audio/pcm;rate=16000;channels=1;encoding=signed-int;bits=16",
        headers={"Content-Disposition": 'inline; filename="speech.pcm"'},
    )
