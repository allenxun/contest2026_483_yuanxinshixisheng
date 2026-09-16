"""face-service 内部 token 的安全文件读取（phase 1：只读凭据，绝不回显取值）。

安全契约（fail-closed，全部抛 :class:`ProviderConfigError`）：

- 路径**缺失 / 不可读** → 拒绝；
- **不是普通文件**（目录、FIFO、socket、字符设备等）→ 拒绝；
- 权限**必须精确为 0600**（``stat.S_IMODE(st_mode) == 0o600``）→ 其余（0644/0640/
  0700/0777…）一律拒绝；
- 内容为空或**纯空白** → 拒绝。

读取成功时**只剥掉一个结尾换行**（``\\n`` 或 ``\\r\\n``），其余字节原样保留；不做
strip，避免悄悄改变 token 值。

**绝密卫生**：token 取值不得出现在异常消息、日志、repr 或测试快照中——错误消息只
点名**配置键名与路径**。本模块返回的字符串由调用方持有；调用方（transport 构造）在
构造时**读取一次**（read-once-at-construction，不做进程级缓存），不写入任何属性名含
``token`` 的日志。

实现用 ``os.open`` + ``os.fstat`` 在同一文件描述符上做“是否普通文件 / 权限”检查，避免
先 ``stat`` 再 ``open`` 的 TOCTOU 竞态；不跟随符号链接语义以 ``os.stat`` 的目标为准
（与 face-service ``config.py`` 的 ``Path.stat()`` 行为一致）。
"""
from __future__ import annotations

import os
import stat as stat_module

from .dconfig import FACE_SERVICE_TOKEN_FILE_ENV, ProviderConfigError


class TokenFileError(ProviderConfigError):
    """token 文件读取/权限/内容错误（可重试面由 face 工厂既有路径分类）。"""


def _one_trailing_newline_stripped(content: str) -> str:
    """只剥掉**一个**结尾换行（``\\r\\n`` 或 ``\\n``），其余内容原样保留。"""
    if content.endswith("\r\n"):
        return content[:-2]
    if content.endswith("\n"):
        return content[:-1]
    return content


def read_token_file(path: str, *, env_name: str = FACE_SERVICE_TOKEN_FILE_ENV) -> str:
    """从 ``path`` 读取内部 token；任何不合规都 fail-closed。

    - ``env_name`` 仅用于错误消息定位配置键（默认 ``MVP_D_FACE_SERVICE_TOKEN_FILE``）；
    - 返回 token 字符串（已剥一个结尾换行）；**绝不**把该值放进任何异常/日志。
    """
    if not path or not path.strip():
        raise TokenFileError(
            f"{env_name} is not set: a 0600 regular token file path is required"
        )
    display_path = path.strip()
    try:
        fd = os.open(display_path, os.O_RDONLY)
    except OSError as exc:
        # 只暴露路径与 errno 类名，绝不回显文件内容。
        raise TokenFileError(
            f"{env_name} is not readable (path={display_path!r}): {type(exc).__name__}"
        ) from exc
    try:
        try:
            st = os.fstat(fd)
        except OSError as exc:
            raise TokenFileError(
                f"{env_name} cannot be stat'ed (path={display_path!r}): "
                f"{type(exc).__name__}"
            ) from exc
        if not stat_module.S_ISREG(st.st_mode):
            raise TokenFileError(
                f"{env_name} must be a regular file (path={display_path!r})"
            )
        mode = stat_module.S_IMODE(st.st_mode)
        if mode != 0o600:
            raise TokenFileError(
                f"{env_name} must have permissions exactly 0600 "
                f"(path={display_path!r}; observed={oct(mode)})"
            )
        try:
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                fd = -1  # fdopen 接管所有权
                content = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise TokenFileError(
                f"{env_name} is not readable as UTF-8 text "
                f"(path={display_path!r}): {type(exc).__name__}"
            ) from exc
    finally:
        if fd >= 0:
            os.close(fd)

    if not content or content.strip() == "":
        raise TokenFileError(
            f"{env_name} content is empty (path={display_path!r})"
        )
    return _one_trailing_newline_stripped(content)


__all__ = ["TokenFileError", "read_token_file"]