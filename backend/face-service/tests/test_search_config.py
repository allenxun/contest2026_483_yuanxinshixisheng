"""Search policy configuration: defaults are fixed and invalid values fail fast.

The four ``FACE_SVC_SEARCH_*`` keys are server-side policy.  Bad values must
abort startup and must NOT echo the rejected value.
"""

from __future__ import annotations

import os

import pytest

from face_service.config import ConfigError, Settings

LOOPBACK = "127.0.0.1"
DUMMY_TOKEN = "dummy-token-for-tests-not-a-secret"


@pytest.fixture(autouse=True)
def _clean_face_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("FACE_SVC_"):
            monkeypatch.delenv(key, raising=False)
    yield monkeypatch


def _base_env(monkeypatch):
    monkeypatch.setenv("FACE_SVC_HOST", LOOPBACK)
    monkeypatch.setenv("FACE_SVC_INTERNAL_TOKEN", DUMMY_TOKEN)


def test_search_defaults_are_conservative_and_uncalibrated_placeholders():
    s = Settings()
    assert s.search_match_threshold == 0.60
    assert s.search_uncertain_band == 0.10
    assert s.search_margin == 0.05
    assert s.search_top_k == 5
    # Stricter than the 1:1 default by design (1:N false accepts grow with N).
    assert s.search_match_threshold > s.verify_threshold


def test_search_values_read_from_env(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("FACE_SVC_SEARCH_MATCH_THRESHOLD", "0.80")
    monkeypatch.setenv("FACE_SVC_SEARCH_UNCERTAIN_BAND", "0.15")
    monkeypatch.setenv("FACE_SVC_SEARCH_MARGIN", "0.10")
    monkeypatch.setenv("FACE_SVC_SEARCH_TOP_K", "3")
    s = Settings.from_env()
    assert s.search_match_threshold == 0.80
    assert s.search_uncertain_band == 0.15
    assert s.search_margin == 0.10
    assert s.search_top_k == 3


@pytest.mark.parametrize("value", ["2", "10"])
def test_search_top_k_min_and_max_accepted(monkeypatch, value):
    # Lower bound is 2: top_k bounds the margin window, and 1 leaves no runner-up.
    _base_env(monkeypatch)
    monkeypatch.setenv("FACE_SVC_SEARCH_TOP_K", value)
    assert Settings.from_env().search_top_k == int(value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("FACE_SVC_SEARCH_MATCH_THRESHOLD", "0"),
        ("FACE_SVC_SEARCH_MATCH_THRESHOLD", "1.5"),
        ("FACE_SVC_SEARCH_MATCH_THRESHOLD", "abc"),
        ("FACE_SVC_SEARCH_UNCERTAIN_BAND", "-0.1"),
        ("FACE_SVC_SEARCH_UNCERTAIN_BAND", "0.61"),
        ("FACE_SVC_SEARCH_MARGIN", "-0.1"),
        ("FACE_SVC_SEARCH_MARGIN", "1.5"),
        ("FACE_SVC_SEARCH_TOP_K", "0"),
        ("FACE_SVC_SEARCH_TOP_K", "1"),
        ("FACE_SVC_SEARCH_TOP_K", "11"),
        ("FACE_SVC_SEARCH_TOP_K", "abc"),
    ],
)
def test_invalid_search_config_fails_fast_without_echoing_value(monkeypatch, key, value):
    _base_env(monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError) as exc:
        Settings.from_env()
    message = str(exc.value)
    assert key in message
    # The rejected value is never echoed as a value (the message may legitimately
    # contain numeric domain bounds such as "1..10", so check value syntax).
    assert f"='{value}'" not in message
    assert f"={value}" not in message
    assert f"'{value}'" not in message