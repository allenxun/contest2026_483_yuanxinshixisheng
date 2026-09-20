import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import argparse
import time

log_dir = os.path.join(PROJECT_ROOT, "logs")
if not os.path.exists(log_dir):
    os.mkdir(log_dir)

from server.api import run_api
from rag.common.utils import logger
from rag.common.configuration import settings
from rag.connector.database.base import create_tables
from rag.connector.base import embedding_model
from rag.module.base import reranker


def warm_up_local_models():
    """Pay one-time CUDA initialization cost before accepting user requests."""
    try:
        started = time.perf_counter()
        embedding_model.embed_query("模型预热")
        if reranker is not None:
            reranker.compute_score([["模型预热", "模型预热"]])
        logger.info("本地模型预热完成，耗时 %.3f 秒", time.perf_counter() - started)
    except Exception as exc:
        logger.warning("本地模型预热失败，首次请求可能较慢：%s", exc, exc_info=exc)


def get_parser():
    parser = argparse.ArgumentParser(prog='RAG-API-Server',
                                     description='')
    parser.add_argument("--host", type=str, default=settings.server.api_server_host)
    parser.add_argument("--port", type=int, default=settings.server.api_server_port)
    parser.add_argument("--ssl_keyfile", type=str)
    parser.add_argument("--ssl_certfile", type=str)
    parser.add_argument("--create_tables", action='store_true', default=False)
    parser.add_argument("--root_path", type=str, default="",
                        help="反向代理挂载的外部路径前缀，如 /chat/api；直连部署留空")
    return parser.parse_args()


def main():
    args = get_parser()

    if args.create_tables:
        create_tables()

    warm_up_local_models()
    logger.info("=========================Starting Service=========================")

    try:
        run_api(host=args.host,
                port=args.port,
                ssl_keyfile=args.ssl_keyfile,
                ssl_certfile=args.ssl_certfile,
                root_path=args.root_path or None)
    except Exception as e:
        logger.error("Api Server 启动失败：", e)
        sys.stderr.write("Fail to start application")


if __name__ == "__main__":
    main()
