"""Start the FastAPI backend and Streamlit web UI together."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from rag.common.configuration import settings


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the LLM-RAG FastAPI backend and Streamlit web UI."
    )
    parser.add_argument("--api-host", default=settings.server.api_server_host)
    parser.add_argument("--api-port", type=int, default=settings.server.api_server_port)
    parser.add_argument("--web-host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=settings.server.web_server_port)
    parser.add_argument(
        "--skip-create-tables",
        action="store_true",
        help="Do not run the idempotent database table initialization on startup.",
    )
    return parser.parse_args()


def build_commands(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    api_command = [
        sys.executable,
        "-m",
        "server.main",
        "--host",
        args.api_host,
        "--port",
        str(args.api_port),
    ]
    if not args.skip_create_tables:
        api_command.append("--create_tables")

    web_command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "server/web_app.py",
        "--server.address",
        args.web_host,
        "--server.port",
        str(args.web_port),
        "--server.headless",
        "true",
        "--client.showSidebarNavigation",
        "false",
    ]
    return api_command, web_command


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 10
    for process in processes:
        if process.poll() is None:
            remaining = max(0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    args = parse_args()
    api_command, web_command = build_commands(args)
    processes: list[subprocess.Popen] = []

    print(f"FastAPI:   http://127.0.0.1:{args.api_port}/docs")
    web_url = f"http://localhost:{args.web_port}"
    print(f"Streamlit: {web_url}")
    print("Press Ctrl+C to stop both services.")

    try:
        processes.append(subprocess.Popen(api_command, cwd=PROJECT_ROOT))
        processes.append(subprocess.Popen(web_command, cwd=PROJECT_ROOT))

        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    if return_code != 0:
                        print(
                            f"A child service exited with status {return_code}.",
                            file=sys.stderr,
                        )
                    return return_code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping services...")
        return 0
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
