import os
import threading
import time

import pytest
import redis

from arena import worker


class FakeRedis:
    """Stands in for Redis and stops the worker loop after one ping."""

    def __init__(self, stop: threading.Event, *, reachable: bool):
        self._stop = stop
        self._reachable = reachable

    def ping(self) -> bool:
        self._stop.set()
        if not self._reachable:
            raise redis.ConnectionError("connection refused")
        return True


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / "worker.heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", path)
    return path


def run_one_beat(heartbeat_file, *, reachable: bool) -> None:
    stop = threading.Event()
    worker.run(FakeRedis(stop, reachable=reachable), heartbeat_file, stop)


def test_check_fails_when_no_worker_has_run(heartbeat_file):
    assert worker.main(["--check"]) == 1


def test_check_passes_while_worker_reaches_redis(heartbeat_file):
    run_one_beat(heartbeat_file, reachable=True)

    assert worker.main(["--check"]) == 0


def test_check_fails_when_redis_is_unreachable(heartbeat_file, caplog):
    run_one_beat(heartbeat_file, reachable=False)

    assert worker.main(["--check"]) == 1
    assert "Redis unreachable (ConnectionError)" in caplog.text
    assert "connection refused" not in caplog.text


def test_check_fails_once_the_heartbeat_is_stale(heartbeat_file):
    run_one_beat(heartbeat_file, reachable=True)
    stale = time.time() - worker.HEARTBEAT_MAX_AGE_SECONDS - 1
    os.utime(heartbeat_file, (stale, stale))

    assert worker.main(["--check"]) == 1


def test_restart_discards_the_previous_heartbeat(heartbeat_file):
    run_one_beat(heartbeat_file, reachable=True)
    run_one_beat(heartbeat_file, reachable=False)

    assert worker.main(["--check"]) == 1
