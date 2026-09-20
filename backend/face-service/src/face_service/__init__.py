"""InsightFace-for-openvela: project-dedicated, isolated face service.

Public surface is intentionally small; see :mod:`face_service.app` for the
FastAPI factory and :mod:`face_service.model` for the model seam.
"""

from .app import create_app
from .config import Settings
from .errors import ErrorCode, FaceServiceError
from .model import FaceDetection, FaceModel, FakeModel, InsightFaceModel, build_model
from .store import FaceStore

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "create_app",
    "Settings",
    "ErrorCode",
    "FaceServiceError",
    "FaceDetection",
    "FaceModel",
    "FakeModel",
    "InsightFaceModel",
    "build_model",
    "FaceStore",
]
