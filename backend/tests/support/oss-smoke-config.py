#!/usr/bin/env python3
"""B 真实 OSS 跨语言 smoke —— 私有 UTF-8 YAML → Python 侧环境变量翻译器（root-only）。

为什么需要它
------------
Java 侧用 snakeyaml 直接读根的私有 ``application-local.yml``；但 worker venv **没有 pyyaml**，
为一个 root-only smoke 给生产依赖树新增依赖不合理。因此由驱动脚本调用**系统 python3**
（已确认带 pyyaml）读取同一份 YAML，把 OSS 配置翻译成 Python 侧生产配置路径
（``mvp_worker.handlers.dshared.dconfig``）使用的环境变量。

安全约束（硬性）
----------------
- **绝不打印任何值**。``--check`` 只输出**键名**清单；``--emit shell`` 的输出只应被
  ``eval "$(...)"`` 捕获后进入同进程环境，**不得**重定向到终端、日志或文件。
- 以**显式 UTF-8** 读取 YAML（``encoding="utf-8"``）。这是上一轮短信中文签名乱码
  （``Properties.load(InputStream)`` 按 ISO-8859-1 解码）的同类教训：任何隐式平台编码都禁止。
- **绝不**把私有配置复制进工作树；本脚本只读、只在 stdout 产生 export 语句。
- 缺失键只报**键名**，绝不回显已存在的值。

用法
----
    python3 oss-smoke-config.py --config /path/to/application-local.yml --check
    eval "$(python3 oss-smoke-config.py --config /path/to/application-local.yml --emit shell)"

退出码：0 成功；2 参数/文件错误；3 provider 不是 aliyun；4 必填键缺失。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── 唯一映射表 ────────────────────────────────────────────────────────────────
# YAML 键（Spring 风格，与 AliyunOssProperties 组件一一对应）→ Python 侧环境变量名。
# 若实施道核实 dconfig.py 的实际变量名与此不同，**只改这张表**，不要改其它逻辑。
#
# 2026-09-14 起 endpoint 拆分为两项（**不兼容旧单 endpoint、不做 fallback**）：
#   server-endpoint → 对象操作（put/get/exists/delete）使用的服务端访问 endpoint
#   public-endpoint → 给 APP/云台的签名地址所针对的客户端公网 endpoint
# 旧的 app.storage.oss.endpoint / MVP_A_STORAGE_OSS_ENDPOINT **一律忽略**（与 Java、Python
# 两侧生产代码一致），只在 stderr 给出迁移提示（只报键名，绝不报值）。
YAML_TO_ENV: dict[str, str] = {
    "server-endpoint": "MVP_A_STORAGE_OSS_SERVER_ENDPOINT",
    "public-endpoint": "MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT",
    "region": "MVP_A_STORAGE_OSS_REGION",
    "bucket": "MVP_A_STORAGE_OSS_BUCKET",
    "access-key-id": "MVP_A_STORAGE_OSS_ACCESS_KEY_ID",
    "access-key-secret": "MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET",
    "security-token": "MVP_A_STORAGE_OSS_SECURITY_TOKEN",
}
# 必填（缺失即拒绝运行；STS 与 region 可选）
REQUIRED_YAML_KEYS: tuple[str, ...] = (
    "server-endpoint",
    "public-endpoint",
    "bucket",
    "access-key-id",
    "access-key-secret",
)
# 已废弃的旧键：只用于给出迁移提示，绝不参与解析（no fallback）。
LEGACY_YAML_KEYS: tuple[str, ...] = ("endpoint",)
LEGACY_MIGRATION_HINT = (
    "legacy key app.storage.oss.endpoint is no longer supported and was IGNORED; "
    "configure app.storage.oss.server-endpoint (object operations) and "
    "app.storage.oss.public-endpoint (client-facing signed URLs)"
)
PROVIDER_ENV: str = "MVP_D_STORAGE_PROVIDER"
PROVIDER_VALUE_PY: str = "aliyun_oss"


def _dig(root: dict, path: list[str]):
    """按路径下钻嵌套 dict；任何一层缺失或类型不符都返回 None（不抛、不回显）。"""
    cur = root
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _load(path: Path) -> dict:
    try:
        import yaml  # 系统 python3 提供；worker venv 不提供（故意不新增依赖）
    except ModuleNotFoundError:
        print(
            "oss-smoke-config: PyYAML is required in the SYSTEM python3 that runs the driver "
            "(the worker venv intentionally has no yaml dependency)",
            file=sys.stderr,
        )
        return {}
    try:
        # 显式 UTF-8：绝不用平台默认编码。
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
    except OSError:
        # 不回显路径内容或异常细节（可能含私有目录结构）。
        print("oss-smoke-config: config file is not readable", file=sys.stderr)
        return {}
    if not isinstance(loaded, dict):
        print("oss-smoke-config: config root is not a mapping", file=sys.stderr)
        return {}
    return loaded


def _lookup(root: dict, dotted: str, parts: list[str]):
    """与 Java 侧 ``OssLiveSmoke.value(map, dotted)`` **严格对称**：先扁平点号键，再嵌套下钻。

    两侧必须同样宽容/同样严格，否则会出现"一侧拿到凭据、另一侧中止"的半成功危害。
    只接受 Spring 规范 kebab-case 拼写；camelCase/snake_case/UPPER 一律视为缺失（响亮拒绝）。
    """
    flat = root.get(dotted)
    if isinstance(flat, str) and flat.strip():
        return flat.strip()
    nested = _dig(root, parts)
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return None


def _shell_quote(value: str) -> str:
    """单引号安全转义（POSIX shell）。值本身绝不会被打印。"""
    return "'" + value.replace("'", "'\\''") + "'"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="B real-OSS cross-language smoke: private UTF-8 YAML -> Python env translator "
        "(root-only; never prints values)")
    parser.add_argument("--config", required=True, help="path to the private UTF-8 YAML (read-only)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="print PRESENT/MISSING KEY NAMES ONLY")
    group.add_argument("--emit", choices=("shell",), help="print export statements for eval")
    args = parser.parse_args(argv)

    path = Path(args.config)
    if not path.is_file():
        print("oss-smoke-config: --config does not point to a readable file", file=sys.stderr)
        return 2

    root = _load(path)
    if not root:
        return 2

    # 与 Java 侧 OssLiveSmoke.value(map, dotted) **严格对称**：先扁平点号键，再嵌套下钻。
    # 只接受 Spring 规范 kebab-case 拼写（access-key-id 等）；camelCase / snake_case / UPPER
    # 一律视为缺失并**响亮拒绝**（只列键名）。刻意不加投机式 relaxed binding：半实现会造成
    # "Python 侧拿到凭据而 Java 侧中止"的半成功危害，比两侧统一拒绝更糟。
    provider = _lookup(root, "app.storage.provider", ["app", "storage", "provider"])

    def lookup(yaml_key: str):
        return _lookup(root, f"app.storage.oss.{yaml_key}", ["app", "storage", "oss", yaml_key])

    values = {key: lookup(key) for key in YAML_TO_ENV}
    missing = [key for key in REQUIRED_YAML_KEYS if not values.get(key)]

    # 遗留键检测：只用于给出迁移提示，**绝不参与解析**（no fallback，与 Java/Python 两侧一致）。
    # stderr 输出，故不会被驱动的 `eval "$(...)"` 捕获；只报键名，绝不回显取值。
    legacy_ignored = sorted(
        key for key in LEGACY_YAML_KEYS
        if _lookup(root, f"app.storage.oss.{key}", ["app", "storage", "oss", key])
    )
    if legacy_ignored:
        print(
            f"oss-smoke-config: ignoring legacy key(s) {legacy_ignored} — {LEGACY_MIGRATION_HINT}",
            file=sys.stderr,
        )

    if args.check:
        present = sorted(key for key, value in values.items() if value)
        print(f"provider={'aliyun' if provider == 'aliyun' else '<not-aliyun-or-absent>'}")
        print(f"present={present}")
        print(f"missing={sorted(missing)}")
        print(f"optional_absent={sorted(k for k in ('region', 'security-token') if not values.get(k))}")
        print(f"legacy_ignored={legacy_ignored}")
        if provider != "aliyun":
            return 3
        return 4 if missing else 0

    # --emit shell
    if provider != "aliyun":
        print(
            "oss-smoke-config: app.storage.provider must be 'aliyun' for a live OSS smoke "
            "(refusing to emit credentials for a non-real provider)",
            file=sys.stderr,
        )
        return 3
    if missing:
        print(f"oss-smoke-config: missing required config keys: {sorted(missing)}", file=sys.stderr)
        return 4

    lines = [f"export {PROVIDER_ENV}={_shell_quote(PROVIDER_VALUE_PY)}"]
    for yaml_key, env_name in YAML_TO_ENV.items():
        value = values.get(yaml_key)
        if value:
            lines.append(f"export {env_name}={_shell_quote(value)}")
    # 只输出 export 语句；调用方必须用 eval 捕获，绝不打印到终端或日志。
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
