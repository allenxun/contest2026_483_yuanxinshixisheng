"""Stable error codes, HTTP mapping and the unified error envelope.

Every failure surfaced by the HTTP API is a ``FaceServiceError``.  The code is
stable and documented in ``README.md``; callers are expected to branch on
``code`` and ``retryable``, never on the human readable ``message``.

Security: ``FaceServiceError`` never carries image bytes, embeddings, tokens or
filesystem paths.  ``details`` is reserved for non-secret scalar context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Stable wire codes.  Value == the string sent on the wire."""

    # Request / image problems (caller can fix by sending a different request).
    NO_FACE = "NO_FACE"
    MULTI_FACES_AMBIGUOUS = "MULTI_FACES_AMBIGUOUS"
    IMAGE_DECODE_FAILED = "IMAGE_DECODE_FAILED"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INVALID_REQUEST = "INVALID_REQUEST"

    # Store / subject problems.
    SUBJECT_NOT_FOUND = "SUBJECT_NOT_FOUND"
    NAMESPACE_NOT_FOUND = "NAMESPACE_NOT_FOUND"
    SUBJECT_ALREADY_EXISTS = "SUBJECT_ALREADY_EXISTS"

    # Honest capability / quality signals.
    QUALITY_INSUFFICIENT = "QUALITY_INSUFFICIENT"
    LIVENESS_UNSUPPORTED = "LIVENESS_UNSUPPORTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_NOT_LOADED = "MODEL_NOT_LOADED"

    # Transport / infrastructure.
    UNAUTHORIZED = "UNAUTHORIZED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    INFERENCE_TIMEOUT = "INFERENCE_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorSpec:
    code: ErrorCode
    http_status: int
    retryable: bool
    description: str


#: Single source of truth for (code -> HTTP status, retryable).
ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.NO_FACE: ErrorSpec(
        ErrorCode.NO_FACE, 400, False, "No face was detected in the supplied image."
    ),
    ErrorCode.MULTI_FACES_AMBIGUOUS: ErrorSpec(
        ErrorCode.MULTI_FACES_AMBIGUOUS,
        400,
        False,
        "More than one face was detected and the operation requires exactly one.",
    ),
    ErrorCode.IMAGE_DECODE_FAILED: ErrorSpec(
        ErrorCode.IMAGE_DECODE_FAILED, 400, False, "Image bytes could not be decoded."
    ),
    ErrorCode.IMAGE_TOO_LARGE: ErrorSpec(
        ErrorCode.IMAGE_TOO_LARGE, 413, False, "Request body exceeds the configured size limit."
    ),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: ErrorSpec(
        ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        415,
        False,
        "Content-Type must be multipart/form-data or application/json.",
    ),
    ErrorCode.INVALID_REQUEST: ErrorSpec(
        ErrorCode.INVALID_REQUEST, 400, False, "Request shape or parameters are invalid."
    ),
    ErrorCode.SUBJECT_NOT_FOUND: ErrorSpec(
        ErrorCode.SUBJECT_NOT_FOUND, 404, False, "Subject does not exist in this namespace."
    ),
    ErrorCode.NAMESPACE_NOT_FOUND: ErrorSpec(
        ErrorCode.NAMESPACE_NOT_FOUND, 404, False, "Namespace does not exist."
    ),
    ErrorCode.SUBJECT_ALREADY_EXISTS: ErrorSpec(
        ErrorCode.SUBJECT_ALREADY_EXISTS,
        409,
        False,
        "Subject already exists and the configured on-exists policy is 'conflict'.",
    ),
    ErrorCode.QUALITY_INSUFFICIENT: ErrorSpec(
        ErrorCode.QUALITY_INSUFFICIENT,
        422,
        False,
        "Computed quality signals are below the configured minimum.",
    ),
    ErrorCode.LIVENESS_UNSUPPORTED: ErrorSpec(
        ErrorCode.LIVENESS_UNSUPPORTED,
        501,
        False,
        "Liveness detection is not supported by the configured model (buffalo_l).",
    ),
    ErrorCode.MODEL_UNAVAILABLE: ErrorSpec(
        ErrorCode.MODEL_UNAVAILABLE, 503, True, "The face model could not be loaded."
    ),
    ErrorCode.MODEL_NOT_LOADED: ErrorSpec(
        ErrorCode.MODEL_NOT_LOADED, 503, True, "The face model is not loaded yet."
    ),
    ErrorCode.UNAUTHORIZED: ErrorSpec(
        ErrorCode.UNAUTHORIZED, 401, False, "Missing or invalid internal token."
    ),
    ErrorCode.CONCURRENCY_LIMIT: ErrorSpec(
        ErrorCode.CONCURRENCY_LIMIT, 429, True, "Too many concurrent inference requests."
    ),
    ErrorCode.INFERENCE_TIMEOUT: ErrorSpec(
        ErrorCode.INFERENCE_TIMEOUT, 504, True, "Inference exceeded the configured timeout."
    ),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(
        ErrorCode.INTERNAL_ERROR, 500, True, "Unexpected internal error."
    ),
}


def error_body(code: ErrorCode, message: str | None, request_id: str,
               details: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = ERROR_SPECS[code]
    body: dict[str, Any] = {
        "error": {
            "code": spec.code.value,
            "message": message or spec.description,
            "retryable": spec.retryable,
            "request_id": request_id,
        }
    }
    if details:
        body["error"]["details"] = details
    return body


class FaceServiceError(Exception):
    """Domain error carrying a stable code and optional non-secret details."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or ERROR_SPECS[code].description)
        self.code = code
        self.message = message
        self.details = details

    @property
    def http_status(self) -> int:
        return ERROR_SPECS[self.code].http_status

    @property
    def retryable(self) -> bool:
        return ERROR_SPECS[self.code].retryable

    def to_body(self, request_id: str) -> dict[str, Any]:
        return error_body(self.code, self.message, request_id, self.details)


__all__ = [
    "ErrorCode",
    "ErrorSpec",
    "ERROR_SPECS",
    "FaceServiceError",
    "error_body",
]
