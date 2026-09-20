"""BLOCKER 2: fail-closed auth defaults, strict boolean parsing, host/auth coupling.

All tests isolate ``FACE_SVC_*`` from the ambient environment so the real
process environment can never influence the assertions.
"""

from __future__ import annotations

import os

import pytest

from face_service.config import ConfigError, Settings, is_loopback_host

LOOPBACK = "127.0.0.1"
DUMMY_TOKEN = "dummy-token-for-tests-not-a-secret"


@pytest.fixture(autouse=True)
def _clean_face_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("FACE_SVC_"):
            monkeypatch.delenv(key, raising=False)
    yield monkeypatch


# -- defaults -------------------------------------------------------------
def test_dataclass_default_auth_required_is_true():
    assert Settings().auth_required is True


def test_from_env_default_auth_required_is_true(monkeypatch):
    # Host on loopback + a token so validation passes; auth_required is unset.
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)
    assert Settings.from_env().auth_required is True


def test_default_non_loopback_host_refuses_without_token(monkeypatch):
    # Nothing set: default host is 10.3.6.163 (non-loopback) and auth defaults
    # to true, so the service must refuse to start without a token.
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    assert "FACE_SVC_INTERNAL_TOKEN" in str(exc.value)


# -- strict boolean parsing ----------------------------------------------
def test_misspelled_bool_is_rejected_not_silently_false(monkeypatch):
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", "treu")
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    msg = str(exc.value)
    assert "FACE_SVC_AUTH_REQUIRED" in msg
    # The allowed domain is named ...
    assert "true" in msg and "false" in msg
    # ... but the rejected value is NOT echoed.
    assert "treu" not in msg


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", " on "])
def test_bool_truthy_values_accepted(monkeypatch, value):
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", value)
    assert Settings.from_env().auth_required is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", " off "])
def test_bool_falsy_values_accepted(monkeypatch, value):
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", value)
    assert Settings.from_env().auth_required is False


def test_other_bool_call_site_also_strict(monkeypatch):
    # QUALITY_ENFORCE benefits from the same strict parser.
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_QUALITY_ENFORCE", "maybe")
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    msg = str(exc.value)
    assert "FACE_SVC_QUALITY_ENFORCE" in msg
    assert "maybe" not in msg


# -- bind address / auth coupling ----------------------------------------
@pytest.mark.parametrize("host", ["10.3.6.163", "0.0.0.0", "192.168.1.10", "example.com"])
def test_non_loopback_requires_auth_true(monkeypatch, host):
    monkeypatch.setenv("FACE_SVC_HOST", host)
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", "false")
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    assert "FACE_SVC_AUTH_REQUIRED=true" in str(exc.value)


def test_non_loopback_with_auth_true_but_no_token_refused(monkeypatch):
    monkeypatch.setenv("FACE_SVC_HOST", "10.3.6.163")
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", "true")
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    assert "FACE_SVC_INTERNAL_TOKEN" in str(exc.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "LOCALHOST", " ::1 "])
def test_loopback_may_disable_auth(monkeypatch, host):
    monkeypatch.setenv("FACE_SVC_HOST", host)
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", "false")
    settings = Settings.from_env()
    assert settings.auth_required is False


def test_non_loopback_with_auth_and_token_allowed(monkeypatch):
    monkeypatch.setenv("FACE_SVC_HOST", "10.3.6.163")
    monkeypatch.setenv("FACE_SVC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)
    settings = Settings.from_env()
    assert settings.auth_required is True


def test_is_loopback_host_matrix():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host(" ::1 ")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("10.3.6.163")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("example.com")
