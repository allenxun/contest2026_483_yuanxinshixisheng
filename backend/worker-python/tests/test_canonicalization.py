"""跨语言规范化基线：以 contracts/scripts/jcs.py（路径导入，只读）复现共享向量。

证明 Worker 侧工具链与契约基线一致（decisions #11；Java 侧测试复现同一向量）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from conftest import CONTRACTS_DIR

JCS_PATH = CONTRACTS_DIR / "scripts" / "jcs.py"
VECTORS_PATH = CONTRACTS_DIR / "samples" / "canonicalization" / "vectors.json"


@pytest.fixture(scope="module")
def jcs():
    spec = importlib.util.spec_from_file_location("contracts_jcs", JCS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vectors_all_reproduce(jcs) -> None:
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    assert len(vectors) >= 10
    for vec in vectors:
        assert jcs.sha256_hex(vec["input"]) == vec["expected_sha256"], vec["name"]


def test_order_pairs_equal_and_unequal(jcs) -> None:
    vectors = {v["name"]: v for v in json.loads(VECTORS_PATH.read_text("utf-8"))}
    a = vectors["nested-out-of-order-keys-a"]["expected_sha256"]
    b = vectors["nested-out-of-order-keys-b-equal-hash-to-a"]["expected_sha256"]
    assert a == b  # 语义相同 → 同摘要
    front = vectors["array-order-significant-front-left-right"]["expected_sha256"]
    rev = vectors["array-order-significant-reversed-different-hash"]["expected_sha256"]
    assert front != rev  # 数组有序 → 不同摘要
    c3 = vectors["near-collision-closure-final-count-3"]["expected_sha256"]
    c4 = vectors["near-collision-closure-final-count-4-different-hash"]["expected_sha256"]
    assert c3 != c4  # 近碰撞不合并


def test_duplicate_keys_rejected(jcs) -> None:
    with pytest.raises(jcs.CanonicalizationError):
        jcs.load_strict('{"a": 1, "a": 2}')


def test_echo_sample_roundtrips(jcs) -> None:
    sample = json.loads(
        (CONTRACTS_DIR / "samples" / "jobs" / "system-echo.json").read_text("utf-8")
    )
    digest = jcs.sha256_hex(sample)
    assert len(digest) == 64 and digest == digest.lower()
