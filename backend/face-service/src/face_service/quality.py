"""Honest, computable face-quality signals.

Design rule: **never fabricate a metric**.  Anything this build cannot compute
from the model output or the pixels is returned as
``{"supported": false, "reason": ...}``.  Liveness is always unsupported because
``buffalo_l`` ships no liveness model; detection scores and embedding
similarities are explicitly NOT used as liveness proxies.

Genuinely computed signals (all deterministic, no CV model required):

* ``det_score``      -- from the detector (real confidence).
* ``blur``           -- variance of the 4-neighbour Laplacian over the grayscale
  face crop (a standard focus measure).
* ``bbox_area_ratio``-- detection box area / image area.
* ``illumination``   -- grayscale mean and standard deviation of the crop.

Unsupported in this build (with reason): ``pose``, ``occlusion``, ``liveness``.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from .errors import ErrorCode, FaceServiceError

#: Fixed, honest liveness statement.  Never derived from det_score/similarity.
LIVENESS_UNSUPPORTED: dict[str, Any] = {
    "supported": False,
    "reason": "buffalo_l has no liveness model",
}


def liveness_block() -> dict[str, Any]:
    """Return a copy of the fixed unsupported-liveness block."""
    return dict(LIVENESS_UNSUPPORTED)


def decode_rgb_image(image_bytes: bytes) -> np.ndarray:
    """Decode arbitrary image bytes to an ``(H, W, 3)`` uint8 RGB array.

    Raises :class:`FaceServiceError` with ``IMAGE_DECODE_FAILED`` when the bytes
    are not a decodable image.  No image bytes are echoed in the error.
    """
    if not image_bytes:
        raise FaceServiceError(ErrorCode.IMAGE_DECODE_FAILED, "empty image payload")
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FaceServiceError(
            ErrorCode.IMAGE_DECODE_FAILED, "image could not be decoded"
        ) from exc


def _to_gray(image: np.ndarray) -> np.ndarray:
    # ITU-R BT.601 luma, matching common focus-measure implementations.
    return (
        0.299 * image[:, :, 0] + 0.587 * image[:, :, 1] + 0.114 * image[:, :, 2]
    ).astype(np.float64)


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian.  Higher == sharper."""
    g = gray.astype(np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = (
        -4.0 * g[1:-1, 1:-1]
        + g[:-2, 1:-1]
        + g[2:, 1:-1]
        + g[1:-1, :-2]
        + g[1:-1, 2:]
    )
    return float(lap.var())


def _crop(image: np.ndarray, bbox: tuple[float, float, float, float]) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    ix1 = max(0, min(w, int(round(x1))))
    iy1 = max(0, min(h, int(round(y1))))
    ix2 = max(0, min(w, int(round(x2))))
    iy2 = max(0, min(h, int(round(y2))))
    if ix2 - ix1 < 1 or iy2 - iy1 < 1:
        return image
    return image[iy1:iy2, ix1:ix2]


def evaluate_quality(
    *,
    bbox: tuple[float, float, float, float],
    det_score: float,
    image: np.ndarray,
    min_det_score: float,
    min_blur: float,
    min_bbox_ratio: float,
    landmarks_available: bool = False,
) -> dict[str, Any]:
    """Compute the quality block for one detection.

    ``landmarks_available`` only affects the *availability note* for pose; no
    pose estimate is produced by this build even when landmarks exist, because
    no validated estimator is wired here -- saying otherwise would be dishonest.
    """
    h, w = image.shape[:2]
    image_area = float(max(1, h * w))
    crop = _crop(image, bbox)
    gray = _to_gray(crop)

    x1, y1, x2, y2 = bbox
    box_w = max(0.0, float(x2) - float(x1))
    box_h = max(0.0, float(y2) - float(y1))
    bbox_area_ratio = (box_w * box_h) / image_area

    blur = laplacian_variance(gray)
    gray_flat = gray.reshape(-1)
    illum_mean = float(gray_flat.mean()) if gray_flat.size else 0.0
    illum_std = float(gray_flat.std()) if gray_flat.size else 0.0

    min_acceptable = (
        float(det_score) >= min_det_score
        and blur >= min_blur
        and bbox_area_ratio >= min_bbox_ratio
    )

    pose_reason = (
        "no validated pose estimator is wired into this build"
        if landmarks_available
        else "landmark output is not available from the configured model in this build"
    )

    return {
        "det_score": float(det_score),
        "bbox": [float(x1), float(y1), float(x2), float(y2)],
        "bbox_width": box_w,
        "bbox_height": box_h,
        "bbox_area_ratio": bbox_area_ratio,
        "image_width": int(w),
        "image_height": int(h),
        "blur": {
            "supported": True,
            "value": blur,
            "method": "laplacian_variance_gray_crop",
        },
        "illumination": {
            "supported": True,
            "mean": illum_mean,
            "std": illum_std,
            "method": "gray_mean_std_crop",
        },
        "pose": {"supported": False, "reason": pose_reason},
        "occlusion": {
            "supported": False,
            "reason": "no validated occlusion estimator is wired into this build",
        },
        "liveness": liveness_block(),
        "min_acceptable": min_acceptable,
        "thresholds": {
            "det_score": min_det_score,
            "blur": min_blur,
            "bbox_area_ratio": min_bbox_ratio,
        },
    }


__all__ = [
    "decode_rgb_image",
    "laplacian_variance",
    "evaluate_quality",
    "liveness_block",
    "LIVENESS_UNSUPPORTED",
]
