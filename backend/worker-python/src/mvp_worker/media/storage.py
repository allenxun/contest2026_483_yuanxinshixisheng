"""StoragePort + 文件系统替身 + 阿里云 OSS 适配器（本地开发/测试双端共用布局）。

镜像 Java 侧存储适配端口的最小面：put/get/delete/exists。生产由真实 OSS
适配器替换（凭据只走环境变量）。文件系统替身仅用于 A 包骨架与 B/C/D 测试。

**跨语言一致性**：对象 key 规范 ``environment/purpose/random-media-id`` 与 Java
``MediaService`` 相同；OSS 配置键名/默认值与 Java ``app.storage.oss.*`` 对齐（见
``MVP_A_STORAGE_OSS_*``）。**私有桶**：读取走 ``get_object`` 流式字节，绝不使用
``sign_url``/预签名 URL、不产生任何公开 URL。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Protocol

from ..logging_setup import mlog

log = logging.getLogger("mvp_worker.media.storage")

#: 受控 put 失败注入开关（测试专用，默认关闭，仅 dev/test 可达；生产由
#: ``dconfig.assert_no_double_injection_in_production`` fail-closed）。
#: 只影响对象 key 用途段为 ``assessment_result`` 的写入（worker 结果图归档），
#: 与 Java 侧上传（``assessment_source`` / 核验等用途）**按用途可区分**。
STORAGE_DOUBLE_FAIL_PUT_ENV = "MVP_D_STORAGE_DOUBLE_FAIL_PUT"

# --- 存储 provider 选择（沿用既有 ``MVP_D_*_PROVIDER`` 命名风格） ---
STORAGE_PROVIDER_ENV = "MVP_D_STORAGE_PROVIDER"
STORAGE_PROVIDER_DOUBLE = "double"
STORAGE_PROVIDER_ALIYUN_OSS = "aliyun_oss"
STORAGE_PROVIDERS = (STORAGE_PROVIDER_DOUBLE, STORAGE_PROVIDER_ALIYUN_OSS)

# --- OSS 配置 env（与 Java app.storage.oss.* 一一对应；跨语言共享 MVP_A_STORAGE_ 前缀） ---
# 默认值：region/endpoint 为公开文档示例（cn-hangzhou 经典地域），bucket 无默认（必填）。
DEFAULT_OSS_REGION = "cn-hangzhou"
DEFAULT_OSS_ENDPOINT = "https://oss-cn-hangzhou.aliyuncs.com"
OSS_REGION_ENV = "MVP_A_STORAGE_OSS_REGION"
OSS_ENDPOINT_ENV = "MVP_A_STORAGE_OSS_ENDPOINT"
OSS_BUCKET_ENV = "MVP_A_STORAGE_OSS_BUCKET"
OSS_ACCESS_KEY_ID_ENV = "MVP_A_STORAGE_OSS_ACCESS_KEY_ID"
OSS_ACCESS_KEY_SECRET_ENV = "MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET"
OSS_SECURITY_TOKEN_ENV = "MVP_A_STORAGE_OSS_SECURITY_TOKEN"


class StorageError(RuntimeError):
    pass


class StorageNotFoundError(StorageError):
    """对象不存在（``NoSuchKey``/404）。``get`` 抛此错、``exists`` 返回 False。"""


class StorageTransientError(StorageError):
    """瞬时故障（DNS/连接/超时/5xx）→ 上层按既有可重试语义处理。"""


class StorageConfigError(StorageError):
    """配置错误（凭据/权限/签名/4xx 参数）→ 重试不可恢复，上层落终态。"""


def storage_put_failure_injected() -> bool:
    """读取注入开关的**严格**语义值（与 DConfig / 生产守卫复用同一解析）。

    合法值域 ``1/true/yes/on`` → True，``0/false/no/off`` → False；未设/空 → False；
    **非法值 → ``ProviderConfigError``**（加载期已由 ``DConfig.storage_double_fail_put``
    校验，此处保证运行时读取与守卫语义完全一致）。延迟 import 以避免
    ``dconfig → storage`` 的模块级循环。
    """
    from ..handlers.dshared.dconfig import strict_env_bool

    return strict_env_bool(STORAGE_DOUBLE_FAIL_PUT_ENV, False)


def _object_purpose(object_key: str) -> str:
    parts = object_key.split("/")
    return parts[1] if len(parts) >= 2 else ""


class StoragePort(Protocol):
    def put(
        self, object_key: str, data: bytes, content_type: str | None = None
    ) -> None: ...
    def get(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str) -> None: ...
    def exists(self, object_key: str) -> bool: ...


def build_object_key(environment: str, purpose: str, media_id: str) -> str:
    """对象 key 规范 ``environment/purpose/random-media-id``（DD 10.1）。

    不含姓名/手机号/成员可读名称；media_id 为服务端随机 UUID 文本。
    与 Java ``MediaService`` 的 objectKey 构造逐字符一致。
    """
    return f"{environment}/{purpose}/{media_id}"


class FilesystemStorageDouble:
    """根目录 ``${MVP_A_STORAGE_DEV_DIR:-/tmp/mvp-a-storage}`` 下的文件存储替身。

    **跨语言布局约定**：文件路径 = ``<root>/<object_key>`` 原样，与 Java
    ``FileSystemStorageDouble``（app.storage.dev-dir，env APP_STORAGE_DEV_DIR /
    MVP_A_STORAGE_DEV_DIR 双名兼容）字节一致——同 root 同 key 读写同一文件。
    key 视为相对路径；解析后必须仍在根目录内（防 ``..`` 逃逸）。
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        base = root or os.environ.get("MVP_A_STORAGE_DEV_DIR", "/tmp/mvp-a-storage")
        self._root = Path(base).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, object_key: str) -> Path:
        candidate = (self._root / object_key).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise StorageError(f"object key escapes storage root: {object_key!r}")
        return candidate

    def put(
        self, object_key: str, data: bytes, content_type: str | None = None
    ) -> None:
        if storage_put_failure_injected() and _object_purpose(object_key) == "assessment_result":
            # 受控失败：镜像真实 OSS 结果图写入失败（dmedia 捕获后映射为既有
            # RESULT_ARCHIVE_FAILED，terminal=False → 可重试，绝不伪报成功）。
            raise StorageError(
                "injected result-image storage put failure"
                f" ({STORAGE_DOUBLE_FAIL_PUT_ENV}=true, purpose=assessment_result)"
            )
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # 原子替换，避免读到半写对象

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        if not path.is_file():
            raise StorageNotFoundError(f"object not found: {object_key!r}")
        return path.read_bytes()

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # 删除幂等（补偿重试友好）

    def exists(self, object_key: str) -> bool:
        return self._path(object_key).is_file()


# --- OSS 错误 → 重试语义 显式分类表 -------------------------------------------
# 不存在语义：**仅**对象缺失（NoSuchKey）。注意 ``NoSuchBucket`` 在 OSS 也返回
# HTTP 404，但它是**永久性配置错误**（bucket 名错/未创建），必须归 CONFIG，绝不能
# 当成"对象不存在"或可重试。
_OSS_NOT_FOUND_CODES = frozenset({"NoSuchKey"})

# 永久性配置/权限/参数错误 → :class:`StorageConfigError`（终态，不可重试）。
# 覆盖凭据/签名/时钟/域名/bucket 参数/对象名/请求体/能力不支持/已存在/过大等
# 重试绝不会成功的错误码（即使其 HTTP 状态是 4xx 或 404）。
_OSS_PERMANENT_CODES = frozenset(
    {
        "NoSuchBucket",
        "InvalidBucketName",
        "AccessDenied",
        "InvalidAccessKeyId",
        "InvalidAccessKeyID",
        "SignatureDoesNotMatch",
        "RequestTimeTooSkewed",
        "SecondLevelDomainForbidden",
        "MissingSecurityToken",
        "InvalidSecurityToken",
        "SecurityTokenExpired",
        "InvalidArgument",
        "InvalidObjectName",
        "MalformedXML",
        "OperationNotSupported",
        "ObjectAlreadyExists",
        "EntityTooLarge",
    }
)

# 确属瞬时的 OSS 错误码（服务端过载/超时/限流/传输完整性）→ 可重试。
_OSS_TRANSIENT_CODES = frozenset(
    {
        "RequestTimeout",
        "OperationTimeout",
        "ServiceUnavailable",
        "InternalError",
        "TooManyRequests",
    }
)


def _map_oss_error(
    exc: BaseException, *, operation: str, object_key: str, bucket: str
) -> StorageError:
    """把 oss2 异常映射为**决定重试语义**的三类 :class:`StorageError`。

    分类表（判定顺序即优先级）：

    ============================== ========================= ==================
    输入                           映射                       重试语义
    ============================== ========================= ==================
    ``NoSuchKey`` / code=NoSuchKey :class:`StorageNotFoundError` 不存在语义
    code ∈ 永久码集合（含 NoSuchBucket/AccessDenied/        :class:`StorageConfigError`   **终态**
    InvalidAccessKeyId/SignatureDoesNotMatch/RequestTimeTooSkewed/
    SecondLevelDomainForbidden/InvalidBucketName/InvalidArgument/…）
    ``RequestError``（DNS/连接/超时）                      :class:`StorageTransientError` **可重试**
    ``InconsistentError``（CRC/传输完整性）/code ∈ 瞬时码集合 :class:`StorageTransientError` **可重试**
    status 429 / ≥500                                      :class:`StorageTransientError` **可重试**
    ``ClientError``（SDK 侧参数/配置）/ 其它 4xx（含        :class:`StorageConfigError`   **终态**
    未识别 code 的 404）
    **兜底（无可用 status 的未知异常）**                    :class:`StorageConfigError`   **终态**
    ============================== ========================= ==================

    **兜底方向 = 终态（StorageConfigError），理由**：oss2 已把所有传输层故障统一
    包装为 ``RequestError``（status=-2），HTTP 响应则保留真实 status；因此能落到
    兜底的既非网络错误也非 5xx/429，重试极可能无益，继续按可重试处理只会掩盖永久性
    配置/数据缺陷并浪费重试预算（fail-closed）。未知 5xx/网络仍可重试，未知 4xx 以及
    无 status 的未知异常按终态处理。

    日志只含 bucket / object key / request_id / OSS code / HTTP status，
    **绝不**记录 AK/SK/SecurityToken（它们也不在本函数入参中）。
    """
    if isinstance(exc, StorageError):
        return exc
    status = getattr(exc, "status", None)
    code = str(getattr(exc, "code", "") or "")
    request_id = getattr(exc, "request_id", "") or ""
    mlog(
        log,
        logging.WARNING,
        "oss.storage_error",
        operation=operation,
        bucket=bucket,
        objectKey=object_key,
        requestId=request_id or None,
        ossCode=code or None,
        httpStatus=status if isinstance(status, int) else None,
    )

    def _build(cls: type[StorageError]) -> StorageError:
        return cls(
            f"OSS {operation} failed (code={code!r}, status={status!r}, request_id={request_id!r})"
        )

    # 延迟 import：oss2 是运行时依赖，但类型检查/无 OSS 场景不强制导入。
    try:
        from oss2 import exceptions as oss_exc
    except Exception:  # pragma: no cover - oss2 缺失（非 aliyun_oss 部署不会有此路径）
        oss_exc = None  # type: ignore[assignment]

    # 1) 不存在语义：仅对象缺失。
    if code in _OSS_NOT_FOUND_CODES:
        return _build(StorageNotFoundError)
    if oss_exc is not None and isinstance(exc, oss_exc.NoSuchKey):
        return _build(StorageNotFoundError)
    # 2) 明确的永久性配置/权限/参数错误（必须先于任何 status==404/4xx 判断，
    #    因为 NoSuchBucket 等也是 404）。
    if code in _OSS_PERMANENT_CODES:
        return _build(StorageConfigError)
    # 3) 瞬时：传输层 / 传输完整性 / 限流 / 5xx。
    if oss_exc is not None and isinstance(exc, oss_exc.RequestError):
        return _build(StorageTransientError)
    if oss_exc is not None and isinstance(exc, oss_exc.InconsistentError):
        return _build(StorageTransientError)
    if status == -2:  # OSS_REQUEST_ERROR_STATUS（网络/DNS/连接/超时）
        return _build(StorageTransientError)
    if isinstance(status, int) and (status == 429 or status >= 500):
        return _build(StorageTransientError)
    if code in _OSS_TRANSIENT_CODES:
        return _build(StorageTransientError)
    # 4) 终态：SDK 侧 ClientError / 其它 4xx 参数与权限错误（含未识别 code 的 404）。
    if oss_exc is not None and isinstance(exc, oss_exc.ClientError):
        return _build(StorageConfigError)
    if isinstance(status, int) and 400 <= status < 500:
        return _build(StorageConfigError)
    # 5) 兜底：终态配置错误（见 docstring 取舍说明）。
    return _build(StorageConfigError)


class AliyunOssStorage:
    """真实阿里云 OSS 存储适配器（**私有桶**；无公开 URL、无预签名 URL）。

    - ``put`` 写入真实 ``Content-Type``（调用方经 ``content_type`` 传入）与由 oss2
      依字节长度生成的 ``Content-Length``；可选写 ``x-oss-meta-purpose``（仅用途段，
      不含任何身份/敏感信息）。
    - ``get`` 用 ``get_object`` 流式读取并确保 ``close()``，返回 bytes。
    - ``exists`` 用 ``object_exists``（HEAD）；``delete`` 幂等。
    - 未使用 STS 时用经典 ``oss2.Auth``；提供 SecurityToken 时用
      ``oss2.StsAuth(..., auth_version=oss2.AUTH_VERSION_4)``（官方推荐 V4 签名）。

    凭据只存在于实例内部，绝不写入日志/异常消息。
    """

    provider_name = STORAGE_PROVIDER_ALIYUN_OSS

    def __init__(
        self,
        *,
        bucket_name: str,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str = DEFAULT_OSS_ENDPOINT,
        region: str = DEFAULT_OSS_REGION,
        security_token: str | None = None,
    ) -> None:
        if not bucket_name or not access_key_id or not access_key_secret:
            # 只报告"缺哪个键"，绝不回显值。
            raise StorageConfigError(
                "aliyun oss storage requires non-empty bucket/access key id/secret"
            )
        import oss2  # 延迟 import：仅真实 OSS 部署需要

        if security_token:
            auth: Any = oss2.StsAuth(
                access_key_id,
                access_key_secret,
                security_token,
                auth_version=oss2.AUTH_VERSION_4,
            )
        else:
            auth = oss2.Auth(access_key_id, access_key_secret)
        self._bucket_name = bucket_name
        self._endpoint = endpoint
        self._region = region
        self._bucket = oss2.Bucket(auth, endpoint, bucket_name, region=region)

    @property
    def bucket_name(self) -> str:
        """配置的 bucket 名（供 T11 ``media_objects.bucket`` 写入对齐）。"""
        return self._bucket_name

    def put(
        self, object_key: str, data: bytes, content_type: str | None = None
    ) -> None:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        purpose = _object_purpose(object_key)
        if purpose:
            # 仅记录非敏感用途段（如 assessment_result），不含身份信息。
            headers["x-oss-meta-purpose"] = purpose
        try:
            self._bucket.put_object(object_key, data, headers=headers or None)
        except Exception as exc:  # noqa: BLE001 - 统一映射为受控 StorageError
            raise _map_oss_error(
                exc, operation="put", object_key=object_key, bucket=self._bucket_name
            ) from exc

    def get(self, object_key: str) -> bytes:
        result: Any = None
        try:
            result = self._bucket.get_object(object_key)
            return result.read()
        except Exception as exc:  # noqa: BLE001
            raise _map_oss_error(
                exc, operation="get", object_key=object_key, bucket=self._bucket_name
            ) from exc
        finally:
            if result is not None:
                try:
                    result.close()
                except Exception:  # pragma: no cover - close 失败不影响已读结果
                    pass

    def delete(self, object_key: str) -> None:
        try:
            self._bucket.delete_object(object_key)
        except Exception as exc:  # noqa: BLE001
            mapped = _map_oss_error(
                exc, operation="delete", object_key=object_key, bucket=self._bucket_name
            )
            if isinstance(mapped, StorageNotFoundError):
                return  # 删除幂等
            raise mapped from exc

    def exists(self, object_key: str) -> bool:
        try:
            return bool(self._bucket.object_exists(object_key))
        except Exception as exc:  # noqa: BLE001
            mapped = _map_oss_error(
                exc, operation="exists", object_key=object_key, bucket=self._bucket_name
            )
            if isinstance(mapped, StorageNotFoundError):
                return False
            raise mapped from exc
