"""Runtime: один процесс для панели и работы. Подставные зависимости — тот же приём, что для Supervisor
(tests/test_supervisor.py), просто проверяем, что Runtime.start/pause/stop по-настоящему дёргают Supervisor."""
import threading
import time

import pytest

from nexus.panel.runtime import PAUSED, RUNNING, STOPPED, Runtime, Unavailable, get_runtime
from nexus.tasks import TaskStore


class FakeSupervisor:
    def __init__(self):
        self.ticks = 0
        self.shutdowns = []

    def tick(self):
        self.ticks += 1

    def shutdown(self, reason):
        self.shutdowns.append(reason)


class FakeWatch:
    def check(self):
        return type("O", (), {"may_work": True, "state": "MONIKA_FREE", "busy": [], "unknown": []})()


class FakeCollector:
    def __init__(self):
        self.calls = 0

    def run_due(self, may_work):
        self.calls += 1
        return {}


def wait_until(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    sup = FakeSupervisor()
    rt = Runtime(store=TaskStore(tmp_path / "n.db"), watch=FakeWatch(), engine=object(), items=object(),
                sources=[], topics=[], memory=object(), supervisor=sup, collector=FakeCollector(),
                sleep=lambda s: time.sleep(0.01))
    yield rt, sup
    rt.shutdown_process()


def test_initial_state_is_stopped(runtime):
    rt, sup = runtime
    assert rt.state == STOPPED and sup.ticks == 0


def test_start_runs_loop_and_ticks(runtime):
    rt, sup = runtime
    rt.start()
    assert rt.state == RUNNING
    assert wait_until(lambda: sup.ticks > 2)


def test_pause_stops_ticking_and_calls_shutdown(runtime):
    rt, sup = runtime
    rt.start()
    wait_until(lambda: sup.ticks > 0)
    rt.pause()
    assert rt.state == PAUSED and sup.shutdowns == ["Давид поставил Nexus на паузу"]
    n = sup.ticks
    time.sleep(0.05)
    assert sup.ticks == n                                   # на паузе tick() больше не зовётся


def test_start_after_pause_resumes_ticking_without_new_thread(runtime):
    rt, sup = runtime
    rt.start()
    wait_until(lambda: sup.ticks > 0)
    rt.pause()
    thread_before = rt._thread
    rt.start()
    assert rt.state == RUNNING and rt._thread is thread_before      # тот же поток, не новый
    n = sup.ticks
    assert wait_until(lambda: sup.ticks > n)


def test_stop_calls_shutdown_and_idles_the_thread(runtime):
    """stop() не убивает поток — он просто засыпает (ничего не тикает), чтобы start() потом
    продолжил на том же потоке, а не плодил новые. Поток убивает только shutdown_process()."""
    rt, sup = runtime
    rt.start()
    wait_until(lambda: sup.ticks > 0)
    rt.stop()
    assert rt.state == STOPPED and "Давид остановил Nexus" in sup.shutdowns
    thread = rt._thread
    n = sup.ticks
    time.sleep(0.05)
    assert sup.ticks == n and thread.is_alive()                 # поток жив, просто бездействует
    rt.shutdown_process()
    assert wait_until(lambda: not thread.is_alive())             # а вот выход из программы его завершает


def test_start_twice_is_a_noop(runtime):
    rt, sup = runtime
    rt.start()
    wait_until(lambda: sup.ticks > 0)
    t1 = rt._thread
    rt.start()
    assert rt._thread is t1


def test_pause_without_running_is_a_noop(runtime):
    rt, sup = runtime
    rt.pause()
    assert rt.state == STOPPED and sup.shutdowns == []


def test_collector_and_planner_run_periodically(runtime):
    rt, sup = runtime
    rt.collector = FakeCollector()
    rt._next_collect = 0.0
    rt.start()
    assert wait_until(lambda: rt.collector.calls >= 1)


def test_background_exception_is_caught_and_recorded(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)

    class BoomSupervisor(FakeSupervisor):
        def tick(self):
            raise RuntimeError("бум")
    rt = Runtime(store=TaskStore(tmp_path / "n.db"), watch=FakeWatch(), engine=object(), items=object(),
                sources=[], topics=[], memory=object(), supervisor=BoomSupervisor(), collector=FakeCollector(),
                sleep=lambda s: time.sleep(0.01))
    rt.start()
    assert wait_until(lambda: rt.last_error)
    assert rt.state == RUNNING                                 # сломанная итерация не выключает Nexus совсем
    rt.shutdown_process()


def test_unavailable_never_raises():
    u = Unavailable("движок занят")
    assert u.state == "недоступно" and u.reason == "движок занят"
    u.start(); u.pause(); u.stop(); u.shutdown_process()        # ничего не падает


def test_get_runtime_is_a_singleton(monkeypatch):
    import nexus.panel.runtime as rtmod
    monkeypatch.setattr(rtmod, "_runtime", None)
    created = []
    monkeypatch.setattr(rtmod, "Runtime", lambda: created.append(1) or object())
    a = get_runtime()
    b = get_runtime()
    assert a is b and len(created) == 1
