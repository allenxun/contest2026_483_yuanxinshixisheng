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
import logging
import threading
import uuid
from contextlib import contextmanager
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
from mvp_worker.logging_setup import JsonFormatter
from mvp_worker.media.storage import (
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_BUCKET_ENV,
    OSS_PUBLIC_ENDPOINT_ENV,
    OSS_SERVER_ENDPOINT_ENV,
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
FAKE_SERVER_ENDPOINT = "https://oss-fake-server.example.com"
FAKE_PUBLIC_ENDPOINT = "https://oss-fake-public.example.com"
#: 已彻底移除的旧单 endpoint 键（仅测试用：验证迁移失败与"从不被读取"）。
LEGACY_ENDPOINT_ENV = "MVP_A_STORAGE_OSS_ENDPOINT"


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
        server_endpoint=FAKE_SERVER_ENDPOINT,
        public_endpoint=FAKE_PUBLIC_ENDPOINT,
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
    monkeypatch.setenv(OSS_SERVER_ENDPOINT_ENV, FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv(OSS_PUBLIC_ENDPOINT_ENV, FAKE_PUBLIC_ENDPOINT)


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
            bucket_name="", access_key_id=FAKE_AK, access_key_secret=FAKE_SK,
            server_endpoint=FAKE_SERVER_ENDPOINT, public_endpoint=FAKE_PUBLIC_ENDPOINT,
        )
    message = str(ei.value)
    assert "bucket_name" in message
    for secret_value in (
        FAKE_AK, FAKE_SK, FAKE_BUCKET, FAKE_SERVER_ENDPOINT, FAKE_PUBLIC_ENDPOINT,
    ):
        assert secret_value not in message


def test_oss_constructor_missing_endpoint_no_value_leak() -> None:
    with pytest.raises(StorageConfigError) as ei:
        AliyunOssStorage(
            bucket_name=FAKE_BUCKET, access_key_id=FAKE_AK, access_key_secret=FAKE_SK,
            server_endpoint="", public_endpoint=FAKE_PUBLIC_ENDPOINT,
        )
    message = str(ei.value)
    assert "server_endpoint" in message
    assert FAKE_PUBLIC_ENDPOINT not in message


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
        (OSS_SERVER_ENDPOINT_ENV, OSS_SERVER_ENDPOINT_ENV),
        (OSS_PUBLIC_ENDPOINT_ENV, OSS_PUBLIC_ENDPOINT_ENV),
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
    assert FAKE_SERVER_ENDPOINT not in str(ei.value)
    assert FAKE_PUBLIC_ENDPOINT not in str(ei.value)


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


# =============== 2b) endpoint 拆分 / 旧键迁移 / server-public 路由 / 签名 ===============


class _RecordingBucket:
    """注入 ``oss2.Bucket`` 的间谍：记录构造 endpoint 与各操作调用。"""

    def __init__(self, auth: Any, endpoint: str, bucket_name: str, **kwargs: Any) -> None:
        self.auth = auth
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.kwargs = kwargs
        self.calls: list[Any] = []

    def put_object(self, key: str, data: bytes, headers: Any = None) -> Any:
        self.calls.append("put_object")
        return object()

    def get_object(self, key: str) -> Any:
        self.calls.append("get_object")
        raise oss2.exceptions.NoSuchKey(404, {}, b"", {"Code": "NoSuchKey"})

    def object_exists(self, key: str) -> bool:
        self.calls.append("object_exists")
        return False

    def delete_object(self, key: str) -> Any:
        self.calls.append("delete_object")
        return object()

    def sign_url(self, method: str, key: str, expires: int, **kwargs: Any) -> str:
        self.calls.append(("sign_url", method, key, expires, kwargs))
        return f"{self.endpoint}/{key}?signed=1"


def _install_recording_buckets(monkeypatch: Any) -> list[_RecordingBucket]:
    created: list[_RecordingBucket] = []

    def _factory(auth: Any, endpoint: str, bucket_name: str, **kwargs: Any) -> _RecordingBucket:
        bucket = _RecordingBucket(auth, endpoint, bucket_name, **kwargs)
        created.append(bucket)
        return bucket

    monkeypatch.setattr(oss2, "Bucket", _factory)
    return created


def test_endpoints_split_uses_server_and_public_buckets(monkeypatch: Any) -> None:
    created = _install_recording_buckets(monkeypatch)
    storage = AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        server_endpoint=FAKE_SERVER_ENDPOINT,
        public_endpoint=FAKE_PUBLIC_ENDPOINT,
        region="cn-hangzhou",
    )
    # 两个独立 bucket：先 server（对象操作）后 public（签名）。
    assert [b.endpoint for b in created] == [FAKE_SERVER_ENDPOINT, FAKE_PUBLIC_ENDPOINT]
    # 两个 bucket 都传 region：V4（STS 路径）需要它进入 Credential Scope；V1（长期 AK/SK）
    # 虽不使用 region，仍统一传入以保持两个 bucket 构造一致。
    assert all(b.kwargs.get("region") == "cn-hangzhou" for b in created)

    server_bucket, public_bucket = created
    storage.put("dev/assessment_result/m1", b"x", content_type="image/png")
    storage.exists("dev/assessment_result/m1")
    storage.delete("dev/assessment_result/m1")
    assert "put_object" in server_bucket.calls
    assert "object_exists" in server_bucket.calls
    assert "delete_object" in server_bucket.calls
    assert public_bucket.calls == []  # 对象操作绝不走 public bucket

    url = storage.sign_public_url("dev/assessment_result/m1", 3600)
    assert url.startswith(FAKE_PUBLIC_ENDPOINT)
    assert server_bucket.calls.count("put_object") == 1  # 签名不触发对象操作
    sign_calls = [c for c in public_bucket.calls if isinstance(c, tuple) and c[0] == "sign_url"]
    assert len(sign_calls) == 1
    assert sign_calls[0][1] == "GET"
    assert sign_calls[0][3] == 3600
    assert sign_calls[0][4].get("slash_safe") is True


def test_sign_public_url_uses_public_host_and_slash_safe() -> None:
    """签名地址针对 **public endpoint** 直接生成，且保留 `/`（slash_safe=True）。

    签名版本**随凭据类型**：长期 AK/SK → 经典 **V1**（查询参数 `OSSAccessKeyId`/`Expires`/
    `Signature`，**不含** `x-oss-signature-version`）；STS → **V4**
    （见 :func:`test_sign_public_url_uses_v4_when_sts_credentials`）。
    这是**刻意决定**而非遗漏：根已在 ``ede19b5`` 上用真实凭据验证过 V1 数据面，而 V4 把 region
    纳入 Credential Scope，一旦 ``MVP_A_STORAGE_OSS_REGION`` 与桶实际区域不符即失败；且 Java 侧
    同为 SDK 默认 V1，两侧对同一桶必须发出**同一种**签名版本。统一迁移 V4 须由根裁定并用真实
    凭据重新验证（见 :func:`test_auth_selection_preserves_the_verified_data_plane`）。
    """
    storage = AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        server_endpoint=FAKE_SERVER_ENDPOINT,
        public_endpoint=FAKE_PUBLIC_ENDPOINT,
        region="cn-hangzhou",
    )
    key = "dev/assessment_result/3f2b6c1e-9a4d-4f0e-8b7c-1d2e3f4a5b6c"
    url = storage.sign_public_url(key, 3600)
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.hostname is not None
    assert parsed.hostname.endswith("oss-fake-public.example.com")
    assert "oss-fake-server" not in parsed.hostname  # host 不等于 server host
    assert "/assessment_result/" in parsed.path  # slash_safe=True：分隔符未转义
    # 长期 AK/SK → V1 查询参数如实存在；V4 专属参数必须**不存在**（防止把版本写错却测试通过）。
    assert "OSSAccessKeyId=" in url
    assert "Expires=" in url
    assert "Signature=" in url
    assert "x-oss-signature-version" not in url
    # 与服务端 endpoint 签名的 host 不同（证明未用 server 签名再替换 host）。
    server_url = storage._bucket.sign_url("GET", key, 3600, slash_safe=True)
    assert urlparse(server_url).hostname != parsed.hostname
    assert urlparse(server_url).hostname.endswith("oss-fake-server.example.com")


@pytest.mark.parametrize("expires", [0, -1, 604801, True, 1.5, "60"])
def test_sign_public_url_rejects_out_of_range_expiry(expires: Any) -> None:
    storage = _oss_storage(_FakeBucket())
    with pytest.raises(StorageConfigError) as ei:
        storage.sign_public_url("dev/assessment_result/m1", expires)
    assert "out of range" in str(ei.value)


def test_sign_public_url_accepts_max_expiry() -> None:
    """604800 秒（7 天）是允许的上限；该上限对 V1/V4 **统一适用**（与 Java `MAX_EXPIRY` 一致）。"""
    storage = _oss_storage(_FakeBucket())
    url = storage.sign_public_url("dev/assessment_result/m1", 604800)
    # 确实产出了针对 public endpoint 的签名地址（长期 AK/SK ⇒ V1 查询参数）。
    # 注意 oss2 用 virtual-host 风格：host = <bucket>.<endpoint-host>，故不能用 startswith 断言。
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.hostname == f"{FAKE_BUCKET}.{urlparse(FAKE_PUBLIC_ENDPOINT).hostname}"
    assert "OSSAccessKeyId=" in url and "Signature=" in url


def test_sign_public_url_uses_v4_when_sts_credentials() -> None:
    """STS 临时凭据路径**仍是 V4**（``OSS4-HMAC-SHA256``）——这一支从未改变。

    保留 V4 覆盖：签名版本随凭据类型（AK/SK → V1，STS → V4）。同时如实记录 STS 语义——
    URL 实际有效期 = ``min(expires_seconds, token 剩余有效期)``，token 过期即失效。
    """
    storage = AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        security_token=FAKE_TOKEN,
        server_endpoint=FAKE_SERVER_ENDPOINT,
        public_endpoint=FAKE_PUBLIC_ENDPOINT,
        region="cn-hangzhou",
    )
    url = storage.sign_public_url("dev/assessment_result/m1", 3600)
    # oss2 用 virtual-host 风格：host = <bucket>.<endpoint-host>（不能用 startswith 断言）。
    parsed = urlparse(url)
    assert parsed.hostname == f"{FAKE_BUCKET}.{urlparse(FAKE_PUBLIC_ENDPOINT).hostname}"
    assert "x-oss-signature-version=OSS4-HMAC-SHA256" in url
    # V4 的 Credential Scope 含 region（跨 region 不可复用）。
    assert "cn-hangzhou" in url
    # STS token 参与签名（以查询参数形式），但**绝不**出现在异常/日志中（另有净化用例覆盖）。
    assert "security-token=" in url.lower() or "securitytoken=" in url.lower()


def test_legacy_single_endpoint_only_fails_with_migration_hint(monkeypatch: Any) -> None:
    monkeypatch.setenv(STORAGE_PROVIDER_ENV, "aliyun_oss")
    monkeypatch.setenv(OSS_BUCKET_ENV, FAKE_BUCKET)
    monkeypatch.setenv(OSS_ACCESS_KEY_ID_ENV, FAKE_AK)
    monkeypatch.setenv(OSS_ACCESS_KEY_SECRET_ENV, FAKE_SK)
    monkeypatch.delenv(OSS_SERVER_ENDPOINT_ENV, raising=False)
    monkeypatch.delenv(OSS_PUBLIC_ENDPOINT_ENV, raising=False)
    legacy_value = "https://legacy-single-endpoint.example.com"
    monkeypatch.setenv(LEGACY_ENDPOINT_ENV, legacy_value)
    with pytest.raises(ProviderConfigError) as ei:
        build_storage_port(DConfig.from_env(), environment="dev")
    message = str(ei.value)
    # 点名两个新变量 + 迁移提示；绝不回显旧取值。
    assert OSS_SERVER_ENDPOINT_ENV in message
    assert OSS_PUBLIC_ENDPOINT_ENV in message
    assert "split" in message and "migrate" in message
    assert legacy_value not in message
    assert FAKE_AK not in message and FAKE_SK not in message


def test_legacy_endpoint_ignored_when_new_endpoints_present(monkeypatch: Any) -> None:
    _set_oss_env(monkeypatch)
    legacy_value = "https://legacy-single-endpoint.example.com"
    monkeypatch.setenv(LEGACY_ENDPOINT_ENV, legacy_value)
    created = _install_recording_buckets(monkeypatch)
    storage = build_storage_port(DConfig.from_env(), environment="dev")
    assert isinstance(storage, AliyunOssStorage)
    used = [bucket.endpoint for bucket in created]
    assert FAKE_SERVER_ENDPOINT in used and FAKE_PUBLIC_ENDPOINT in used
    assert legacy_value not in used  # 旧键从未被读取/使用


def test_legacy_endpoint_symbols_removed_from_storage_module() -> None:
    import mvp_worker.media.storage as storage_module

    assert not hasattr(storage_module, "OSS_ENDPOINT_ENV")
    assert not hasattr(storage_module, "DEFAULT_OSS_ENDPOINT")


def test_dconfig_has_split_endpoint_fields_only() -> None:
    cfg = DConfig.from_env()
    assert hasattr(cfg, "oss_server_endpoint")
    assert hasattr(cfg, "oss_public_endpoint")
    assert not hasattr(cfg, "oss_endpoint")


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
        server_endpoint=endpoint,
        public_endpoint=endpoint,
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


# ============================================= 9) 日志卫生（与 Java 侧一致）


@contextmanager
def _captured_storage_log() -> Any:
    """捕获 ``mvp_worker.media.storage`` 的结构化 JSON 日志行。"""
    logger = logging.getLogger("mvp_worker.media.storage")
    lines: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(JsonFormatter())
    old_level, old_prop = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_prop


def test_oss_error_log_omits_bucket_and_full_key() -> None:
    """OSS 失败日志不得含真实桶名/完整 objectKey/media_id；含新字段。"""
    media_id = str(uuid.uuid4())
    object_key = build_object_key("dev", "assessment_result", media_id)
    exc = oss2.exceptions.AccessDenied(403, {}, b"", {"Code": "AccessDenied"})
    storage = _oss_storage(_RaisingBucket(exc))

    with _captured_storage_log() as lines:
        with pytest.raises(StorageConfigError):
            storage.put(object_key, b"x", content_type="image/png")

    assert len(lines) == 1
    text = lines[0]
    # 必须移除：真实桶名 / 完整 key / media_id / 凭据
    assert FAKE_BUCKET not in text
    assert object_key not in text
    assert media_id not in text
    assert FAKE_AK not in text and FAKE_SK not in text
    # 必须保留/新增：operation / bucketConfigured / purpose / ossCode / httpStatus
    assert '"operation": "put"' in text
    assert '"bucketConfigured": true' in text
    assert '"purpose": "assessment_result"' in text
    assert '"ossCode": "AccessDenied"' in text
    assert '"httpStatus": 403' in text


def test_oss_error_log_get_path_and_bucket_configured_false() -> None:
    """get 路径同样脱敏；未配置桶 → bucketConfigured=false（仍不写桶名）。"""
    media_id = str(uuid.uuid4())
    object_key = build_object_key("dev", "assessment_source", media_id)
    exc = oss2.exceptions.ServerError(503, {}, b"", {"Code": "ServiceUnavailable"})
    storage = _oss_storage(_RaisingBucket(exc))

    with _captured_storage_log() as lines:
        with pytest.raises(StorageTransientError):
            storage.get(object_key)

    assert len(lines) == 1
    text = lines[0]
    assert FAKE_BUCKET not in text and object_key not in text and media_id not in text
    assert '"operation": "get"' in text
    assert '"purpose": "assessment_source"' in text
    assert '"ossCode": "ServiceUnavailable"' in text

    # 直接调用：bucket="" → false，且不出现任何桶名。
    from mvp_worker.media.storage import _map_oss_error

    with _captured_storage_log() as lines2:
        mapped = _map_oss_error(
            exc, operation="exists", object_key=object_key, bucket=""
        )
    assert isinstance(mapped, StorageTransientError)
    assert len(lines2) == 1
    assert '"bucketConfigured": false' in lines2[0]
    assert object_key not in lines2[0]


def test_oss_error_log_unparsed_purpose_never_falls_back_to_key() -> None:
    """无法解析用途段 → "<unparsed>"，绝不回退输出完整 key。"""
    malformed = "mediaid-without-slashes"
    exc = oss2.exceptions.ServerError(500, {}, b"", {"Code": "InternalError"})
    storage = _oss_storage(_RaisingBucket(exc))

    with _captured_storage_log() as lines:
        with pytest.raises(StorageTransientError):
            storage.put(malformed, b"x", content_type="image/png")

    assert len(lines) == 1
    text = lines[0]
    assert malformed not in text
    assert '"purpose": "<unparsed>"' in text


def test_auth_selection_preserves_the_verified_data_plane(monkeypatch: Any) -> None:
    """回归守卫：签名版本**随凭据类型**，长期 AK/SK 必须仍用经典 V1 ``oss2.Auth``。

    根已在 ``ede19b5`` 上用真实凭据验证过 V1 数据面（put/get/exists/delete 全部成功）。
    V4 会把 region 纳入 Credential Scope（``<date>/<region>/oss/aliyun_v4_request``），
    若 ``MVP_A_STORAGE_OSS_REGION`` 与桶实际区域不符，则 V1 可用而 V4 直接失败。
    因此任何把数据面静默改成 V4（例如 ``ProviderAuthV4``）的改动都必须让本测试失败；
    统一迁移到 V4 属需要真实凭据重新验证的独立决定，须由根裁定后显式实施。
    """
    captured: list[Any] = []
    real_bucket = oss2.Bucket

    def _spy(auth: Any, endpoint: str, bucket_name: str, **kwargs: Any) -> Any:
        captured.append((auth, endpoint))
        return real_bucket(auth, endpoint, bucket_name, **kwargs)

    monkeypatch.setattr(oss2, "Bucket", _spy)

    # 长期 AK/SK：两个 bucket（server + public）都必须用经典 V1 Auth，绝不是 ProviderAuthV4。
    AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        server_endpoint="https://oss-fake-server.example.com",
        public_endpoint="https://oss-fake-public.example.com",
        region="cn-fake-region",
    )
    assert len(captured) == 2, "server bucket 与 public bucket 各构建一次"
    assert all(isinstance(auth, oss2.Auth) for auth, _ in captured)
    assert not any(isinstance(auth, oss2.ProviderAuthV4) for auth, _ in captured)
    # 两个 bucket 分别绑定 server 与 public endpoint（顺序即构造顺序）。
    assert [ep for _, ep in captured] == [
        "https://oss-fake-server.example.com",
        "https://oss-fake-public.example.com",
    ]

    # STS：保持既有的 V4 StsAuth（这一支从未改变）。
    captured.clear()
    AliyunOssStorage(
        bucket_name=FAKE_BUCKET,
        access_key_id=FAKE_AK,
        access_key_secret=FAKE_SK,
        security_token="FAKE-STS-DO-NOT-USE",
        server_endpoint="https://oss-fake-server.example.com",
        public_endpoint="https://oss-fake-public.example.com",
        region="cn-fake-region",
    )
    assert len(captured) == 2
    assert all(isinstance(auth, oss2.StsAuth) for auth, _ in captured)


def test_dconfig_repr_redacts_credentials_and_endpoints(monkeypatch: Any) -> None:
    """回归守卫：``repr(DConfig)`` **绝不**输出 AK/SK/STS token 与 endpoint/bucket 取值。

    dataclass 默认 repr 会原样打印全部 37 个字段（含 ``oss_access_key_secret`` 等）；一旦将来
    有人写 ``log.info("%s", cfg)`` 或把 cfg 带进异常消息就会泄漏凭据。``DConfig`` 已改为
    ``@dataclass(frozen=True, repr=False)`` + 自定义**按字段名模式**脱敏的 ``__repr__``，
    故将来新增的同类字段会自动被覆盖。非敏感字段仍原样显示以便调试。
    """
    monkeypatch.setenv(OSS_ACCESS_KEY_ID_ENV, FAKE_AK)
    monkeypatch.setenv(OSS_ACCESS_KEY_SECRET_ENV, FAKE_SK)
    monkeypatch.setenv(OSS_BUCKET_ENV, FAKE_BUCKET)
    monkeypatch.setenv(OSS_SERVER_ENDPOINT_ENV, FAKE_SERVER_ENDPOINT)
    monkeypatch.setenv(OSS_PUBLIC_ENDPOINT_ENV, FAKE_PUBLIC_ENDPOINT)

    text = repr(DConfig.from_env())
    for sensitive in (FAKE_AK, FAKE_SK, FAKE_BUCKET, FAKE_SERVER_ENDPOINT, FAKE_PUBLIC_ENDPOINT):
        assert sensitive not in text, f"repr leaked a sensitive value: {sensitive}"
    assert "<redacted>" in text
    # 非敏感字段仍可见（否则脱敏过度、失去调试价值）。
    assert "storage_provider=" in text
    assert "oss_region=" in text or "face_provider=" in text
