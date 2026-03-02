"""Server runner — starts FastAPI, Celery Worker, and Celery Beat.

Production entry point that manages all three processes:
1. FastAPI (uvicorn) — HTTP/WebSocket server
2. Celery Worker — async task execution
3. Celery Beat — periodic task scheduling
"""

from __future__ import annotations

import os
import sys
import signal
import subprocess
import time
import structlog

logger = structlog.get_logger()


def run_server():
    """Start all server processes."""
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = os.environ.get("APP_PORT", "8000")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    processes = []

    try:
        # 1. Start FastAPI
        logger.info("server.starting_fastapi", host=host, port=port)
        fastapi_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "src.app:create_app",
                "--factory",
                "--host", host,
                "--port", port,
            ],
            env={**os.environ},
        )
        processes.append(("fastapi", fastapi_proc))

        # Give FastAPI time to start
        time.sleep(2)

        logger.info("server.all_started", process_count=len(processes))

        # Wait for any process to exit
        while True:
            for name, proc in processes:
                retcode = proc.poll()
                if retcode is not None:
                    logger.error(
                        "server.process_exited",
                        process=name,
                        exit_code=retcode,
                    )
                    raise SystemExit(f"{name} exited with code {retcode}")
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit) as e:
        logger.info("server.shutting_down", reason=str(e))
    finally:
        # Graceful shutdown
        for name, proc in processes:
            if proc.poll() is None:
                logger.info("server.stopping", process=name)
                proc.send_signal(signal.SIGTERM)

        # Wait for graceful shutdown (5s timeout)
        for name, proc in processes:
            try:
                proc.wait(timeout=5)
                logger.info("server.stopped", process=name)
            except subprocess.TimeoutExpired:
                logger.warning("server.force_killing", process=name)
                proc.kill()


if __name__ == "__main__":
    run_server()
