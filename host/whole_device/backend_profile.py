"""Resolve the backend origin used by every whole-device request.

The LAN origin remains the default for existing development runs.  A cloud
origin is selected explicitly through ``VELAVISION_BACKEND_BASE_URL`` (or by
using the cloud assessment config), so authentication, upload, polling and
narration cannot accidentally be split across two deployments.
"""
import os
from urllib.parse import urlsplit, urlunsplit


def normalize_base_url(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing_backend_base_url')
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.username or parts.password:
        raise ValueError('invalid_backend_base_url')
    if parts.query or parts.fragment:
        raise ValueError('invalid_backend_base_url')
    path = parts.path.rstrip('/')
    return urlunsplit((parts.scheme, parts.netloc, path, '', ''))


def configured_base_url(auth_base_url=None, explicit=None):
    """Return one validated origin for login and all subsequent API calls."""
    selected = explicit or os.getenv('VELAVISION_BACKEND_BASE_URL') or auth_base_url
    return normalize_base_url(selected)


def configured_profile():
    """Human-readable profile name for diagnostics without exposing secrets."""
    override = os.getenv('VELAVISION_BACKEND_BASE_URL')
    if override:
        return 'cloud' if normalize_base_url(override).startswith('https://') else 'custom'
    return 'auth-config'
