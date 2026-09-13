"""真实阿里云 OSS 存储 provider（Python 侧）定向测试。

**不访问真实阿里云 OSS**：全部用**假凭据**（``LTAI-FAKE-DO-NOT-USE`` 等明显假值）
+ 假 bucket 对象 / 本地 HTTP stub。覆盖：

- provider 按服务独立选择（``MVP_D_STORAGE_PROVIDER``）与生产 fail-closed；
- ``AliyunOssStorage`` put/get/exists/delete 与元数据（Content-Type/Content-Length）；
- 失败→重试语义映射：NoSuchKey → 不存在；AccessDenied/4xx → 终态不可重试；
  RequestError/5xx → 瞬时（``ArchiveError.terminal is False``，保留既有可重试路径）；
- objectKey 与 Java 完全一致；``media_objects.bucket`` 取真实配置桶；
- 真实故障绝不回退本地文件系统；
- 本地 HTTP stub 验证 oss2 **真实 wire** 请求构造（路径/头部/签名请求；签名值用假
  凭据算得，不代表真实 OSS 接受）。
"""
from __future__ import annotations

import base64
import http.server
import threading
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

import oss2
import pytest
from sqlalchemy import Engine, text

from d_support import PNG_BYTES, clean_d_tables, fetch_result_media, seed_assessment
from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import HandlerContext
from mvp_worker.handlers.dshared.constants import DEFAULT_BUCKET
from mvp_worker.handlers.dshared.dconfig import DConfig, ProviderConfigError
from mvp_worker.handlers.dshared.dmedia import (
    ArchiveError,
    archive_result_images,
    load_image_bytes,
)
from mvp_worker.handlers.dshared.providers import build_storage_port
from mvp_worker.handlers.dshared.resolve import storage_for
from mvp_worker.media.storage import (
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_BUCKET_ENV,
    STORAGE_PROVIDER_ENV,
    AliyunOssStorage,
    FilesystemStorageDouble,
    StorageConfigError,
    StorageNotFoundError,
    StorageTransientError,
    build_object_key,
)

FAKE_AK = "LTAI-FAKE-DO-NOT-USE"
FAKE_SK = "fake-secret-do-not-use"
FAKE_BUCKET = "fake-bucket-do-not-use"
FAKE_TOKEN = "fake-sts-token-do-not-use"


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


# ---------------------------------------------------------------- fixtures / helpers


class _FakeGetResult:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class _FakeBucket:
    """假 bucket：记录 put 的 key/字节/头部；缺失对象按 oss2 NoSuchKey 语义。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[tuple[str, bytes, dict[str, str]]] = []
        self.last_get_result: _FakeGetResult | None = None

    def put_object(self, key: str, data: bytes, headers: Any = None) -> Any:
        self.objects[key] = bytes(data)
        self.puts.append((key, bytes(data), dict(headers or {})))
        return object()

    def get_object(self, key: str) -> _FakeGetResult:
        if key not in self.objects:
            raise oss2.exceptions.NoSuchKey(404, {}, b"", {"Code": "NoSuchKey"})
        self.last_get_result = _FakeGetResult(self.objects[key])
        return self.last_get_result

    def object_exists(self, key: str) -> bool:
        return key in self.objects

    def delete_object(self, key: str) -> Any:
        self.objects.pop(key, None)
        return object()


class _RaisingBucket:
    """假 bucket：所有操作抛同一 oss2 异常（验证失败映射）。"""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def put_object(self, key: str, data: bytes, headers: Any = None) -> Any:
        raise self._exc

    def get_object(self, key: str) -> Any:
        raise self._exc

    def object_exists(self, key: str) -> bool:
        raise self._exc

    def delete_object(self, key: str) -> Any:
        raise self._exc


def _oss_storage(bucket_obj: Any, *, bucket_name: str = FAKE_BUCKET) -> AliyunOssStorage:
    storage = AliyunOssStorage(
        bucket_name=bucket_name,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        region="cn-hangzhou",
    )
    storage._bucket = bucket_obj  # 注入假 bucket，避免任何真实网络访问
    return storage


def _ctx(extras: dict[str, Any] | None = None) -> HandlerContext:
    return HandlerContext(
        engine=None,  # type: ignore[arg-type]  # storage_for 不使用 engine
        config=WorkerConfig(),
        job=None,  # type: ignore[arg-type]
        abort_event=threading.Event(),
        extras=extras or {},
    )


def _set_oss_env(monkeypatch: Any, *, bucket: str | None = FAKE_BUCKET) -> None:
    monkeypatch.setenv(STORAGE_PROVIDER_ENV, "aliyun_oss")
    if bucket:
        monkeypatch.setenv(OSS_BUCKET_ENV, bucket)
    monkeypatch.setenv(OSS_ACCESS_KEY_ID_ENV, FAKE_AK)
    monkeypatch.setenv(OSS_ACCESS_KEY_SECRET_ENV, FAKE_SK)


def _seed_analyzing(engine: Engine) -> str:
    return seed_assessment(
        engine, status="analyzing", current_photo_version=1, processing_revision=2
    )


def _images() -> list[dict[str, Any]]:
    return [{"ref": "skin-result-1", "caption": "结果图", "bytes": PNG_BYTES}]


def _row_bucket(engine: Engine, media_id: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT bucket FROM media_objects WHERE id = CAST(:id AS uuid)"),
                {"id": media_id},
            ).scalar_one()
        )


# ============================================================== 1) 适配器单测


def test_oss_put_writes_key_content_type_and_purpose_meta() -> None:
    fake = _FakeBucket()
    storage = _oss_storage(fake)
    data = PNG_BYTES
    storage.put("dev/assessment_result/m1", data, content_type="image/png")

    key, written, headers = fake.puts[0]
    assert key == "dev/assessment_result/m1"
    assert written == data
    assert headers.get("Content-Type") == "image/png"
    # 用途元数据（非身份信息），供对象溯源；不写任何敏感内容。
    assert headers.get("x-oss-meta-purpose") == "assessment_result"


def test_oss_put_without_content_type_still_works() -> None:
    fake = _FakeBucket()
    storage = _oss_storage(fake)
    storage.put("dev/assessment_source/m2", b"abc")
    assert fake.puts[0][2].get("Content-Type") is None


def test_oss_get_roundtrip_and_closes_stream() -> None:
    fake = _FakeBucket()
    storage = _oss_storage(fake)
    storage.put("dev/assessment_result/m1", PNG_BYTES, content_type="image/png")
    assert storage.get("dev/assessment_result/m1") == PNG_BYTES
    assert fake.last_get_result is not None and fake.last_get_result.closed is True


def test_oss_exists_and_delete_idempotent() -> None:
    fake = _FakeBucket()
    storage = _oss_storage(fake)
    assert storage.exists("dev/assessment_result/m1") is False
    storage.put("dev/assessment_result/m1", b"x")
    assert storage.exists("dev/assessment_result/m1") is True
    storage.delete("dev/assessment_result/m1")
    assert storage.exists("dev/assessment_result/m1") is False
    storage.delete("dev/assessment_result/m1")  # 幂等，不抛


def test_oss_nosuchkey_get_and_exists_semantics() -> None:
    exc = oss2.exceptions.NoSuchKey(404, {}, b"", {"Code": "NoSuchKey"})
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageNotFoundError):
        storage.get("dev/assessment_result/missing")
    assert storage.exists("dev/assessment_result/missing") is False
    storage.delete("dev/assessment_result/missing")  # 不存在 → 幂等


@pytest.mark.parametrize(
    "exc",
    [
        oss2.exceptions.AccessDenied(403, {}, b"", {"Code": "AccessDenied"}),
        oss2.exceptions.ServerError(403, {}, b"", {"Code": "SignatureDoesNotMatch"}),
        oss2.exceptions.ClientError("bad request"),
    ],
)
def test_oss_access_or_param_errors_map_to_config_error(exc: BaseException) -> None:
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageConfigError) as ei:
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")
    message = str(ei.value)
    assert FAKE_AK not in message and FAKE_SK not in message  # 绝不泄露凭据


@pytest.mark.parametrize(
    "exc",
    [
        oss2.exceptions.RequestError(OSError("connection reset")),
        oss2.exceptions.ServerError(500, {}, b"", {"Code": "InternalError"}),
        oss2.exceptions.ServerError(503, {}, b"", {"Code": "ServiceUnavailable"}),
    ],
)
def test_oss_transient_errors_map_to_retryable(exc: BaseException) -> None:
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageTransientError):
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")


def test_oss_constructor_missing_credentials_no_value_leak() -> None:
    with pytest.raises(StorageConfigError) as ei:
        AliyunOssStorage(
            bucket_name="", access_key_id=FAKE_AK, access_key_secret=FAKE_SK
        )
    message = str(ei.value)
    assert FAKE_AK not in message and FAKE_SK not in message


# ====================================================== 2) provider 选择与守卫


def test_default_provider_is_double(monkeypatch: Any, tmp_path: Any) -> None:
    for name in (STORAGE_PROVIDER_ENV, OSS_BUCKET_ENV, OSS_ACCESS_KEY_ID_ENV,
                 OSS_ACCESS_KEY_SECRET_ENV):
        monkeypatch.delenv(name, raising=False)
    storage = build_storage_port(
        DConfig.from_env(), environment="dev", dev_dir=str(tmp_path / "dev")
    )
    assert isinstance(storage, FilesystemStorageDouble)


def test_storage_for_selects_aliyun_oss(monkeypatch: Any) -> None:
    _set_oss_env(monkeypatch)
    storage = storage_for(_ctx())
    assert isinstance(storage, AliyunOssStorage)
    assert storage.bucket_name == FAKE_BUCKET


@pytest.mark.parametrize(
    "missing_env,expected",
    [
        (OSS_BUCKET_ENV, OSS_BUCKET_ENV),
        (OSS_ACCESS_KEY_ID_ENV, OSS_ACCESS_KEY_ID_ENV),
        (OSS_ACCESS_KEY_SECRET_ENV, OSS_ACCESS_KEY_SECRET_ENV),
    ],
)
def test_oss_missing_required_config_raises_config_error(
    monkeypatch: Any, missing_env: str, expected: str
) -> None:
    _set_oss_env(monkeypatch)
    monkeypatch.delenv(missing_env, raising=False)
    with pytest.raises(ProviderConfigError) as ei:
        build_storage_port(DConfig.from_env(), environment="dev")
    assert expected in str(ei.value)  # 只报"缺哪个键"
    assert FAKE_AK not in str(ei.value) and FAKE_SK not in str(ei.value)


def test_unknown_storage_provider_fails_fast(monkeypatch: Any) -> None:
    monkeypatch.setenv(STORAGE_PROVIDER_ENV, "bogus")
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert STORAGE_PROVIDER_ENV in str(ei.value)


@pytest.mark.parametrize(
    "prod_env",
    [
        {"APP_ENV": "production"},
        {"MVP_WORKER_ENVIRONMENT": "production"},
        {"MVP_NOTIFY_ENV": "prod"},
        {"APP_ENV": "dev", "SPRING_PROFILES_ACTIVE": "prod,dev"},
        {"MVP_NOTIFY_ENV": "dev", "APP_ENV": "production"},  # 矛盾组合仍拒绝
    ],
)
def test_production_double_storage_rejected(
    monkeypatch: Any, prod_env: dict[str, str]
) -> None:
    for key, value in prod_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(STORAGE_PROVIDER_ENV, "double")
    with pytest.raises(ProviderConfigError):
        build_storage_port(DConfig.from_env(), environment="dev", dev_dir="/tmp/nope")


def test_production_explicit_environment_rejects_double(monkeypatch: Any) -> None:
    monkeypatch.setenv(STORAGE_PROVIDER_ENV, "double")
    with pytest.raises(ProviderConfigError):
        build_storage_port(DConfig.from_env(), environment="production")


def test_production_aliyun_oss_allowed_with_credentials(monkeypatch: Any) -> None:
    _set_oss_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    storage = build_storage_port(DConfig.from_env(), environment="production")
    assert isinstance(storage, AliyunOssStorage)  # 生产允许真实 OSS


def test_existing_face_double_guard_unchanged(monkeypatch: Any) -> None:
    """不得放松既有 face/skin/plan 生产守卫（回归）。"""
    from mvp_worker.handlers.dshared.providers import build_face_port

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ProviderConfigError):
        build_face_port(DConfig.from_env(), environment="production")


# ====================================================== 3) objectKey 跨语言一致


def test_object_key_matches_java_format() -> None:
    media_id = str(uuid.uuid4())
    assert build_object_key("dev", "assessment_result", media_id) == (
        f"dev/assessment_result/{media_id}"
    )


def test_object_key_fixed_uuid_matches_java_literal() -> None:
    media_id = "3f2b6c1e-9a4d-4f0e-8b7c-1d2e3f4a5b6c"
    assert build_object_key("dev", "assessment_result", media_id) == (
        "dev/assessment_result/3f2b6c1e-9a4d-4f0e-8b7c-1d2e3f4a5b6c"
    )


# ====================================================== 4) bucket 一致性


def test_bucket_for_double_keeps_legacy_default(tmp_path: Any) -> None:
    from mvp_worker.handlers.dshared.dmedia import _bucket_for

    assert _bucket_for(FilesystemStorageDouble(tmp_path / "s")) == DEFAULT_BUCKET


def test_bucket_for_oss_uses_configured_bucket() -> None:
    from mvp_worker.handlers.dshared.dmedia import _bucket_for

    assert _bucket_for(_oss_storage(_FakeBucket())) == FAKE_BUCKET


def test_archive_double_writes_legacy_bucket(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    aid = _seed_analyzing(engine)
    archived = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid, photo_version=1,
        result_images=_images(), max_bytes=10_000_000,
    )
    assert _row_bucket(engine, str(archived[0]["media_id"])) == DEFAULT_BUCKET


def test_archive_oss_writes_configured_bucket(engine: Engine) -> None:
    storage = _oss_storage(_FakeBucket())
    aid = _seed_analyzing(engine)
    archived = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid, photo_version=1,
        result_images=_images(), max_bytes=10_000_000,
    )
    assert _row_bucket(engine, str(archived[0]["media_id"])) == FAKE_BUCKET


# ====================================================== 5) 失败 → 重试语义（PG）


def test_archive_oss_access_denied_is_terminal(engine: Engine) -> None:
    """AccessDenied（配置错误）→ ArchiveError.terminal is True；pending 行保留。"""
    exc = oss2.exceptions.AccessDenied(403, {}, b"", {"Code": "AccessDenied"})
    storage = _oss_storage(_RaisingBucket(exc))
    aid = _seed_analyzing(engine)
    with pytest.raises(ArchiveError) as ei:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid, photo_version=1,
            result_images=_images(), max_bytes=10_000_000,
        )
    assert ei.value.code == "RESULT_ARCHIVE_FAILED"
    assert ei.value.terminal is True
    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "pending"


@pytest.mark.parametrize(
    "exc",
    [
        oss2.exceptions.RequestError(OSError("dns failure")),
        oss2.exceptions.ServerError(503, {}, b"", {"Code": "ServiceUnavailable"}),
    ],
)
def test_archive_oss_transient_is_retryable(
    engine: Engine, exc: BaseException
) -> None:
    """RequestError/5xx → 既有 RESULT_ARCHIVE_FAILED（terminal=False）可重试路径。"""
    storage = _oss_storage(_RaisingBucket(exc))
    aid = _seed_analyzing(engine)
    with pytest.raises(ArchiveError) as ei:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid, photo_version=1,
            result_images=_images(), max_bytes=10_000_000,
        )
    assert ei.value.code == "RESULT_ARCHIVE_FAILED"
    assert ei.value.terminal is False
    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "pending"


def test_oss_failure_never_falls_back_to_filesystem(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """``aliyun_oss`` 模式真实故障 → 绝不写本地文件系统、绝不退回 double。"""
    dev_dir = tmp_path / "fssentinel"
    monkeypatch.setenv("MVP_A_STORAGE_DEV_DIR", str(dev_dir))
    _set_oss_env(monkeypatch)
    storage = storage_for(_ctx())
    assert isinstance(storage, AliyunOssStorage)
    assert not isinstance(storage, FilesystemStorageDouble)

    exc = oss2.exceptions.RequestError(OSError("network down"))
    storage._bucket = _RaisingBucket(exc)
    aid = _seed_analyzing(engine)
    with pytest.raises(ArchiveError) as ei:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid, photo_version=1,
            result_images=_images(), max_bytes=10_000_000,
        )
    assert ei.value.terminal is False
    assert not dev_dir.exists()  # 本地替身目录从未被创建/写入


# ====================================================== 6) 本地 HTTP stub（真实 wire）


class _StubOss:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[dict[str, Any]] = []
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _key(self, path: str) -> str:
        return unquote(urlparse(path).path).split("/", 2)[2]

    def _error(self, handler: Any, code: str) -> bytes:
        body = f"<Error><Code>{code}</Code></Error>".encode()
        handler.send_response(404)
        handler.send_header("Content-Type", "application/xml")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("x-oss-err", base64.b64encode(body).decode())
        handler.end_headers()
        return body

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # 静音测试输出
                pass

            def _record(self) -> bytes:
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(length) if length else b""
                stub.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                return body

            def do_PUT(self) -> None:
                body = self._record()
                stub.objects[stub._key(self.path)] = body
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                self._record()
                key = stub._key(self.path)
                if key not in stub.objects:
                    self.wfile.write(stub._error(self, "NoSuchKey"))
                    return
                data = stub.objects[key]
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_HEAD(self) -> None:
                self._record()
                if stub._key(self.path) not in stub.objects:
                    stub._error(self, "NoSuchKey")
                    return
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_DELETE(self) -> None:
                self._record()
                stub.objects.pop(stub._key(self.path), None)
                self.send_response(204)
                self.end_headers()

        return Handler


@pytest.fixture
def oss_stub() -> Any:
    stub = _StubOss()
    try:
        yield stub
    finally:
        stub.close()


def _wire_storage(endpoint: str) -> AliyunOssStorage:
    storage = AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        endpoint=endpoint,
        region="cn-hangzhou",
    )
    # 本地 stub 用 path-style（真实 OSS endpoint 走 virtual-host，不受影响）。
    storage._bucket = oss2.Bucket(
        oss2.Auth(FAKE_AK, FAKE_SK),
        endpoint,
        FAKE_BUCKET,
        region="cn-hangzhou",
        is_path_style=True,
    )
    return storage


def test_oss_wire_put_get_headers_roundtrip(oss_stub: _StubOss) -> None:
    """真实 oss2 请求构造：路径含正确 key、Content-Type/Content-Length、往返一致。"""
    storage = _wire_storage(oss_stub.endpoint)
    key = "dev/assessment_result/3f2b6c1e-9a4d-4f0e-8b7c-1d2e3f4a5b6c"
    storage.put(key, PNG_BYTES, content_type="image/png")

    put = [r for r in oss_stub.requests if r["method"] == "PUT"][0]
    assert key in unquote(put["path"])  # path-style: 路径含正确 key（URL 编码）
    assert put["headers"]["content-type"] == "image/png"
    assert int(put["headers"]["content-length"]) == len(PNG_BYTES)
    assert "authorization" in put["headers"]  # 私有桶请求已签名（假凭据）

    assert storage.get(key) == PNG_BYTES
    assert storage.exists(key) is True
    storage.delete(key)
    assert storage.exists(key) is False


def test_oss_wire_missing_key_maps_to_not_found(oss_stub: _StubOss) -> None:
    storage = _wire_storage(oss_stub.endpoint)
    with pytest.raises(StorageNotFoundError):
        storage.get("dev/assessment_result/missing")
    assert storage.exists("dev/assessment_result/missing") is False


# =========================================== 7) BLOCKER 4：永久错误 → 终态分类


def test_oss_nosuchbucket_is_permanent_config_error() -> None:
    """NoSuchBucket（HTTP 404）是永久配置错误，绝非"对象不存在"/可重试。"""
    exc = oss2.exceptions.NoSuchBucket(404, {}, b"", {"Code": "NoSuchBucket"})
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageConfigError):
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")
    with pytest.raises(StorageConfigError):
        storage.get("dev/assessment_result/m1")


@pytest.mark.parametrize(
    "code",
    [
        "NoSuchBucket",
        "InvalidBucketName",
        "AccessDenied",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "RequestTimeTooSkewed",
        "SecondLevelDomainForbidden",
    ],
)
def test_oss_permanent_code_overrides_4xx_status(code: str) -> None:
    """永久性 code 白名单优先于 status：即使 400/403/404 也归终态。"""
    status = 400 if code in ("InvalidBucketName",) else 403
    exc = oss2.exceptions.ServerError(status, {}, b"", {"Code": code})
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageConfigError):
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")


@pytest.mark.parametrize("code", ["RequestTimeout", "ServiceUnavailable"])
def test_oss_transient_code_whitelist_overrides_4xx_status(code: str) -> None:
    """明确的瞬时 code 归可重试（即使 HTTP status 落在 4xx）。"""
    exc = oss2.exceptions.ServerError(408, {}, b"", {"Code": code})
    storage = _oss_storage(_RaisingBucket(exc))
    with pytest.raises(StorageTransientError):
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")


def test_oss_unknown_statusless_error_falls_back_to_terminal() -> None:
    """兜底方向=终态：无 status/code 的未知异常不伪装成可重试瞬时故障。"""
    storage = _oss_storage(_RaisingBucket(ValueError("unexpected boom")))
    with pytest.raises(StorageConfigError):
        storage.put("dev/assessment_result/m1", b"x", content_type="image/png")


def test_archive_oss_nosuchbucket_is_terminal(engine: Engine) -> None:
    exc = oss2.exceptions.NoSuchBucket(404, {}, b"", {"Code": "NoSuchBucket"})
    storage = _oss_storage(_RaisingBucket(exc))
    aid = _seed_analyzing(engine)
    with pytest.raises(ArchiveError) as ei:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid, photo_version=1,
            result_images=_images(), max_bytes=10_000_000,
        )
    assert ei.value.code == "RESULT_ARCHIVE_FAILED" and ei.value.terminal is True


# ================================= 8) IMPORTANT 6：源图读取 bucket 一致性校验


class _CountingStorage:
    """包装替身并统计 get 次数，证明 bucket 不一致时**未发起任何对象读取**。"""

    def __init__(self, inner: FilesystemStorageDouble) -> None:
        self._inner = inner
        self.get_calls = 0

    def put(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        self._inner.put(object_key, data, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        self.get_calls += 1
        return self._inner.get(object_key)

    def delete(self, object_key: str) -> None:
        self._inner.delete(object_key)

    def exists(self, object_key: str) -> bool:
        return self._inner.exists(object_key)


def _insert_source_row(engine: Engine, *, bucket: str) -> str:
    mid = str(uuid.uuid4())
    key = build_object_key("dev", "assessment_source", mid)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO media_objects (id, bucket, object_key, purpose, state)"
                " VALUES (CAST(:id AS uuid), :bucket, :key, 'assessment_source', 'available')"
            ),
            {"id": mid, "bucket": bucket, "key": key},
        )
    return mid


def test_load_image_bytes_bucket_mismatch_terminal_and_no_read(
    engine: Engine, tmp_path: Any
) -> None:
    storage = _CountingStorage(FilesystemStorageDouble(tmp_path / "s"))
    mid = _insert_source_row(engine, bucket="other-bucket-do-not-use")
    with pytest.raises(StorageConfigError) as ei:
        load_image_bytes(engine, storage, {"front": mid})
    assert storage.get_calls == 0  # 未发起任何对象读取
    msg = str(ei.value)
    assert "values omitted" in msg
    assert "other-bucket-do-not-use" not in msg  # 不输出桶名


def test_load_image_bytes_bucket_match_reads_ok(engine: Engine, tmp_path: Any) -> None:
    storage = _CountingStorage(FilesystemStorageDouble(tmp_path / "s"))
    mid = _insert_source_row(engine, bucket=DEFAULT_BUCKET)
    storage.put(build_object_key("dev", "assessment_source", mid), PNG_BYTES)
    out = load_image_bytes(engine, storage, {"front": mid})
    assert isinstance(out, dict) and out["front"] == PNG_BYTES
    assert storage.get_calls == 1


def test_load_image_bytes_transient_returns_reason(engine: Engine, tmp_path: Any) -> None:
    """瞬时读取失败仍是可重试的字符串语义（未被 BLOCKER 修复误伤）。"""

    class _TransientStorage(_CountingStorage):
        def get(self, object_key: str) -> bytes:
            self.get_calls += 1
            raise StorageTransientError("network blip")

    storage = _TransientStorage(FilesystemStorageDouble(tmp_path / "s"))
    mid = _insert_source_row(engine, bucket=DEFAULT_BUCKET)
    out = load_image_bytes(engine, storage, {"front": mid})
    assert isinstance(out, str) and "storage read failed" in out


def test_archive_existing_row_bucket_mismatch_is_terminal(
    engine: Engine, tmp_path: Any
) -> None:
    """既有结果行桶≠配置桶 → 归档终态（不 put、不改行；不伪装成可重试）。"""
    import hashlib
    import json as _json

    aid = _seed_analyzing(engine)
    media_id = str(uuid.uuid4())
    key = build_object_key("dev", "assessment_result", media_id)
    digest = hashlib.sha256(PNG_BYTES).hexdigest()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO media_objects (id, bucket, object_key, purpose, assessment_id,"
                " photo_version, uploader_type, state, content_type, byte_size, content_hash,"
                " storage_metadata)"
                " VALUES (CAST(:id AS uuid), 'other-bucket-do-not-use', :key,"
                " 'assessment_result', CAST(:a AS uuid), 1, 'worker', 'pending',"
                " 'image/png', :bs, :h, CAST(:meta AS jsonb))"
            ),
            {
                "id": media_id, "key": key, "a": aid, "bs": len(PNG_BYTES), "h": digest,
                "meta": _json.dumps({"schema_version": 1, "provider_ref": "skin-result-1"}),
            },
        )
    storage = FilesystemStorageDouble(tmp_path / "s")
    with pytest.raises(ArchiveError) as ei:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid, photo_version=1,
            result_images=_images(), max_bytes=10_000_000,
        )
    assert ei.value.terminal is True
    assert not any((tmp_path / "s").rglob("*"))  # 未写任何对象
