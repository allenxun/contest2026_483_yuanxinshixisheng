"""StoragePort + 文件系统替身 + 阿里云 OSS 适配器（本地开发/测试双端共用布局）。

镜像 Java 侧存储适配端口的最小面：put/get/delete/exists。生产由真实 OSS
适配器替换（凭据只走环境变量）。文件系统替身仅用于 A 包骨架与 B/C/D 测试。

**跨语言一致性**：对象 key 规范 ``environment/purpose/random-media-id`` 与 Java
``MediaService`` 相同；OSS 配置键名/默认值与 Java ``app.storage.oss.*`` 对齐（见
``MVP_A_STORAGE_OSS_*``）。**endpoint 拆为两项**：对象操作（put/get/delete/exists）
一律走**服务端访问 endpoint**（``MVP_A_STORAGE_OSS_SERVER_ENDPOINT``）；签名地址由
**公网 endpoint**（``MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT``）构建的**独立** bucket 生成
（:meth:`AliyunOssStorage.sign_public_url`），**绝不**"签名后用服务端 host 做字符串
替换"。**私有桶**：对象字节读取走 ``get_object`` 流式。签名地址本轮**未接入任何
handler / 任务 payload / HTTP 面**（是否对外暴露属架构决定，另行裁定）。
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
# endpoint 分两项且**均无默认**（aliyun_oss 必填）：
#   * server endpoint：对象操作（put/get/delete/exists）使用；
#   * public endpoint：客户端签名地址（sign_public_url）使用。
# 旧单 endpoint 键已彻底移除：**不读取、不做 fallback**，只配旧键会在配置校验期明确失败。
DEFAULT_OSS_REGION = "cn-hangzhou"
OSS_REGION_ENV = "MVP_A_STORAGE_OSS_REGION"
OSS_SERVER_ENDPOINT_ENV = "MVP_A_STORAGE_OSS_SERVER_ENDPOINT"
OSS_PUBLIC_ENDPOINT_ENV = "MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT"
OSS_BUCKET_ENV = "MVP_A_STORAGE_OSS_BUCKET"
OSS_ACCESS_KEY_ID_ENV = "MVP_A_STORAGE_OSS_ACCESS_KEY_ID"
OSS_ACCESS_KEY_SECRET_ENV = "MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET"
OSS_SECURITY_TOKEN_ENV = "MVP_A_STORAGE_OSS_SECURITY_TOKEN"

#: OSS 官方对 V4 预签名 URL 的有效期上限：604800 秒（7 天）。超限**明确失败**，不静默截断。
MAX_SIGN_EXPIRES_SECONDS = 604800


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

    日志只含 ``operation`` / ``bucketConfigured``（布尔，**只表示是否已配置、
    绝不含桶名取值**）/ 用途段 ``purpose``（objectKey 第二段，如
    ``assessment_result``）/ ``request_id`` / OSS ``code`` / HTTP ``status``；
    **绝不**记录真实桶名、完整 ``objectKey``、``media_id`` 或
    AK/SK/SecurityToken（凭据也不在本函数入参中）。与 Java
    ``OssStorageAdapter`` 的 ``op/code/requestId`` 日志卫生一致。
    """
    if isinstance(exc, StorageError):
        return exc
    status = getattr(exc, "status", None)
    code = str(getattr(exc, "code", "") or "")
    request_id = getattr(exc, "request_id", "") or ""
    # 只取 objectKey 的第二段（用途），解析失败 → "<unparsed>"；绝不回退输出完整 key。
    purpose = _object_purpose(object_key) or "<unparsed>"
    mlog(
        log,
        logging.WARNING,
        "oss.storage_error",
        operation=operation,
        bucketConfigured=bool(bucket),
        purpose=purpose,
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
    """真实阿里云 OSS 存储适配器（**私有桶**；双 endpoint 分工）。

    - **对象操作**（``put``/``get``/``delete``/``exists``）一律走 ``server_endpoint``
      构建的 bucket。
    - **签名地址**由 ``public_endpoint`` 构建的**独立** bucket 生成
      （:meth:`sign_public_url`），复用同一 ``auth``；**绝不**用 server bucket 签名后
      替换 host/scheme（正确性约束：按最终访问域名直接签名）。
    - **签名版本随凭据类型**（保持既有行为，本轮刻意不改）：长期 AK/SK 用经典
      ``oss2.Auth``（**V1**）；STS 用 ``oss2.StsAuth(..., auth_version=oss2.AUTH_VERSION_4)``
      （**V4**，``OSS4-HMAC-SHA256``）。两个 bucket 均传 ``region``：V4 的 Credential Scope 含
      ``<date>/<region>/oss/aliyun_v4_request``，region 参与签名、跨 region 不可复用、
      V4 缺 region 会失败；V1 不使用 region，但仍传入以保持两个 bucket 构造一致。
      **为何不统一改 V4**：根已在 ``ede19b5`` 上用真实凭据验证过 V1 数据面；V4 把 region
      纳入签名，若 ``MVP_A_STORAGE_OSS_REGION`` 与桶实际区域不符则 V1 可用而 V4 失败。
      统一迁移到 V4（官方推荐）属需要真实凭据重新验证的独立决定，须由根裁定。
    - ``public_endpoint`` 目前按**标准 OSS 域名**处理（未实现自定义域名
      ``is_cname=True``）；若后续需要 CNAME，另行加参数与测试。
    - ``put`` 写入真实 ``Content-Type``（调用方经 ``content_type`` 传入）与由 oss2
      依字节长度生成的 ``Content-Length``；可选写 ``x-oss-meta-purpose``（仅用途段，
      不含任何身份/敏感信息）。
    - ``get`` 用 ``get_object`` 流式读取并确保 ``close()``，返回 bytes。
    - ``exists`` 用 ``object_exists``（HEAD）；``delete`` 幂等。

    **安全提示**：预签名 URL 是"持有即可用"的临时授权，有效期内可被互联网上任何人
    访问。因此本适配器**不把签名地址接入任何 handler 输出 / 任务 payload / HTTP 面**；
    是否对 APP / 云台暴露属架构决定，由根裁定。

    凭据与两个 endpoint 只存在于实例内部，绝不写入日志/异常消息。
    """

    provider_name = STORAGE_PROVIDER_ALIYUN_OSS

    def __init__(
        self,
        *,
        bucket_name: str,
        access_key_id: str,
        access_key_secret: str,
        server_endpoint: str,
        public_endpoint: str,
        region: str = DEFAULT_OSS_REGION,
        security_token: str | None = None,
    ) -> None:
        missing = [
            name
            for name, value in (
                ("bucket_name", bucket_name),
                ("access_key_id", access_key_id),
                ("access_key_secret", access_key_secret),
                ("server_endpoint", server_endpoint),
                ("public_endpoint", public_endpoint),
            )
            if not value
        ]
        if missing:
            # 只报告"缺哪个字段"，绝不回显任何取值（endpoint 亦按敏感配置处理）。
            raise StorageConfigError(
                "aliyun oss storage missing required fields: " + ", ".join(missing)
            )
        import oss2  # 延迟 import：仅真实 OSS 部署需要

        # 签名版本**保持既有行为**（本轮刻意不改）：非 STS 用经典 oss2.Auth（V1），
        # STS 用 StsAuth(auth_version=V4)。理由：根已在 ede19b5 上用真实凭据验证过 V1 数据面
        # （put/get/exists/delete 全部成功），而 V4 会把 region 纳入 Credential Scope——
        # 一旦 MVP_A_STORAGE_OSS_REGION 与桶实际区域不符，V1 可用而 V4 会直接失败。
        # 把已验证的数据面改成未验证状态，属于需要真实凭据重新验证的独立决定，不在本轮范围。
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
        self._server_endpoint = server_endpoint
        self._public_endpoint = public_endpoint
        self._region = region
        # 对象操作 bucket：server endpoint；region 必传（V4 Credential Scope）。
        self._bucket = oss2.Bucket(auth, server_endpoint, bucket_name, region=region)
        # 签名专用 bucket：public endpoint，复用同一 auth 且同样传 region；签名与 host
        # 均来自 public endpoint，绝不对签名结果做 host/scheme/路径字符串替换。
        self._public_bucket = oss2.Bucket(auth, public_endpoint, bucket_name, region=region)

    @property
    def bucket_name(self) -> str:
        """配置的 bucket 名（供 T11 ``media_objects.bucket`` 写入对齐）。"""
        return self._bucket_name

    def sign_public_url(self, object_key: str, expires_seconds: int) -> str:
        """用**公网 endpoint** 的独立 bucket 生成签名 GET 地址。

        签名版本随凭据类型（长期 AK/SK → V1；STS → V4），与对象操作使用的 auth 完全一致。

        - ``slash_safe=True``：object key 含 ``/``，默认会转义路径分隔符；开启后生成
          可直接使用的 URL。注意它影响 canonical URI ⇒ **生成后不得再改路径编码**
          （与"不得替换 host"同理）。
        - 有效期校验：``1 <= expires_seconds <= MAX_SIGN_EXPIRES_SECONDS``（604800 秒 = 7 天）。
          该上限取自 V4 的最大有效期，但**对两种签名版本统一适用**，以保证跨语言行为一致
          （Java 侧 ``OssPublicUrlSigner.MAX_EXPIRY`` 同为 7 天）；越界**明确失败**
          （``StorageConfigError``），**不静默截断也不静默回退默认值**。
        - STS 临时凭据签名时，URL **实际有效期 = min(expires_seconds, token 剩余有效期)**，
          token 过期后 URL 立即失效。
        - **本轮不接入任何 handler / 任务 payload / HTTP 面**；仅供后续架构裁定后调用。
        """
        if (
            isinstance(expires_seconds, bool)
            or not isinstance(expires_seconds, int)
            or not (1 <= expires_seconds <= MAX_SIGN_EXPIRES_SECONDS)
        ):
            raise StorageConfigError(
                "sign_public_url expires_seconds out of range"
                f" (1..{MAX_SIGN_EXPIRES_SECONDS})"
            )
        return self._public_bucket.sign_url(
            "GET", object_key, expires_seconds, slash_safe=True
        )

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
