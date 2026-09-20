"""Helpers for resolving local models with a ModelScope download fallback."""

from pathlib import Path

from rag.common.configuration import resolve_project_path
from rag.common.utils import logger

_MODEL_CONFIG = "config.json"
_MODEL_WEIGHTS = (
    "model.safetensors",
    "pytorch_model.bin",
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
)


def _is_usable_model_dir(model_path: Path) -> bool:
    if not model_path.is_dir():
        return False
    if not (model_path / _MODEL_CONFIG).is_file():
        return False
    return any((model_path / name).is_file() for name in _MODEL_WEIGHTS)


def ensure_model_available(model_name_or_path: str, modelscope_model_id: str) -> str:
    """Return a local model path, downloading it from ModelScope when absent."""
    if not model_name_or_path:
        raise ValueError("A local model path must be configured.")

    model_path = Path(resolve_project_path(model_name_or_path))
    if _is_usable_model_dir(model_path):
        return str(model_path)

    if not modelscope_model_id:
        raise FileNotFoundError(
            f"Model directory does not contain a usable model and no "
            f"ModelScope model ID is configured: {model_path}"
        )

    if model_path.exists():
        logger.info(
            f"Local model at {model_path} is incomplete; "
            f"downloading {modelscope_model_id} from ModelScope"
        )
    else:
        logger.info(
            f"Model not found at {model_path}; "
            f"downloading {modelscope_model_id} from ModelScope"
        )
    model_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded_path = Path(
        _snapshot_download(modelscope_model_id, str(model_path))
    ).resolve()
    if _is_usable_model_dir(model_path):
        logger.info(f"ModelScope model downloaded to {model_path}")
        return str(model_path)
    if _is_usable_model_dir(downloaded_path):
        logger.info(f"ModelScope model downloaded to {downloaded_path}")
        return str(downloaded_path)
    raise RuntimeError(
        f"ModelScope download of {modelscope_model_id} did not produce "
        f"config.json and model weights at {model_path}"
    )


def _snapshot_download(modelscope_model_id: str, local_dir: str) -> str:
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "The 'modelscope' package is required to download missing models."
        ) from exc
    return snapshot_download(modelscope_model_id, local_dir=local_dir)
