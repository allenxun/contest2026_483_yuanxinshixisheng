"""Shared rate limiter instance for the FastAPI application."""

from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

def rate_limit_key(request) -> str:
    """Use the network address; never trust an unverified identity header."""
    return f"ip:{get_remote_address(request)}"

# 基于客户端 IP 地址的限流器。
# 默认限制：每分钟 60 次请求；特定端点在路由注册时单独设置更严格的限制。
# Do not let slowapi/Starlette open `.env` with the locale encoding (GBK on
# Chinese Windows). App secrets are already loaded via python-dotenv (UTF-8).
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["60/minute"],
    config_filename=str(Path(__file__).with_name("slowapi.env")),
)
