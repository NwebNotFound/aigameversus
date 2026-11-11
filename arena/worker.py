"""Match worker process.

Placeholder until the engine exists: the worker only proves that it is alive
and can reach Redis. It writes a heartbeat file after every successful ping;
`python -m arena.worker --check` (the container healthcheck) fails when that
heartbeat is missing or stale.
"""

import argparse
import logging
import os
import signal
import tempfile
import threading
import time
from pathlib import Path

import redis

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "arena-worker.heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 5.0
HEARTBEAT_MAX_AGE_SECONDS = 3 * HEARTBEAT_INTERVAL_SECONDS

log = logging.getLogger("arena.worker")


def beat(client: redis.Redis, heartbeat_file: Path) -> None:
    """Refresh the heartbeat if Redis answers; otherwise let it go stale."""
    try:
        client.ping()
    except redis.RedisError as error:
        # Log the error type only: connection details never reach the logs.
        log.warning("Redis unreachable (%s)", type(error).__name__)
        return
    heartbeat_file.touch()


def is_healthy(heartbeat_file: Path, now: float) -> bool:
    try:
        age = now - heartbeat_file.stat().st_mtime
    except FileNotFoundError:
        return False
    return age < HEARTBEAT_MAX_AGE_SECONDS


def run(client: redis.Redis, heartbeat_file: Path, stop: threading.Event) -> None:
    """Beat until `stop` is set."""
    heartbeat_file.unlink(missing_ok=True)
    while not stop.is_set():
        beat(client, heartbeat_file)
        stop.wait(HEARTBEAT_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena.worker", description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 0 if a running worker has a fresh heartbeat, else 1",
    )
    args = parser.parse_args(argv)
    if args.check:
        return 0 if is_healthy(HEARTBEAT_FILE, time.time()) else 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=2)
    log.info("worker started")
    run(client, HEARTBEAT_FILE, stop)
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
