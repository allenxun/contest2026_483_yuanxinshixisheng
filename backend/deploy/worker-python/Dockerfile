# syntax=docker/dockerfile:1
# 版本锁定（decisions.md）：python:3.12-slim；psycopg[binary] 自带 libpq，无需系统构建依赖。
FROM python:3.12-slim AS run
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --system --create-home --uid 10001 appuser
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
USER appuser
# T12 运行循环已实装：无参数 = claim/dispatch/complete 循环 + /healthz /readyz；
# CLI 参数（--once/--check/--recover）透传：docker run --rm <image> --check
ENTRYPOINT ["python", "-m", "mvp_worker"]
