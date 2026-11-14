import threading
import time

import pytest

from nexus import config
from nexus.engine import Cancelled
from nexus.priority_watch import BUSY, FREE, UNKNOWN, Observation
from nexus.resources import Gpu
from nexus.supervisor import REST, WAIT, WORK, Supervisor
from nexus.tasks import COMPLETED, INTERRUPTED, TaskStore


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class FakeWatch:
    def __init__(self):
        self.state = FREE

    def check(self):
        return Observation(self.state, ["открыта программа"] if self.state == BUSY else [],
                           ["что-то не проверено"] if self.state == UNKNOWN else [])


class FakeGen:
    def __init__(self):
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()


class FakeEngine:
    def __init__(self, step_s=0.0, release=True):
        self.on = False
        self.calls = []
        self.step_s = step_s
        self.release = release
        self.requests = 0

    def alive(self):
        return self.on

    def start(self):
        self.calls.append("start")
        self.on = True

    def stop(self):
        self.calls.append("stop")
        self.on = False
        return True

    def unload_all(self):
        self.calls.append("unload")

    def pull(self, model):
        self.calls.append(("pull", model))

    def wait_vram_released(self, base, tol=300, timeout=30):
        self.calls.append("verify")
        return 0.1 if self.release else None

    def chat_stream(self, model, messages, options, keep_alive="5m", on_start=None):
        assert self.on, "запрос к выключенному движку"
        g = FakeGen()
        on_start(g)
        self.requests += 1
        end = time.monotonic() + self.step_s
        while time.monotonic() < end:
            if g.cancelled.is_set():
                raise Cancelled()
            time.sleep(0.005)
        if g.cancelled.is_set():
            raise Cancelled()
        yield f"абзац {self.requests}"


class FakeRes:
    def __init__(self):
        self.used = 500
        self.ram = 8.0
        self.game = set()

    def gpu(self):
        return Gpu(5, self.used, 8000 - self.used, 8188)

    def free_ram_gb(self):
        return self.ram

    def games(self):
        return self.game


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    store = TaskStore(tmp_path / "t.db")
    s = config.Settings(segment_s=100, rest_s=50, after_priority_s=30)
    watch, res, clock = FakeWatch(), FakeRes(), Clock()

    def make(engine):
        return Supervisor(store, watch, engine, res, s, clock=clock)
    yield store, watch, res, clock, make
    store.close()


def test_runs_task_to_end_then_stops_engine(env):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    tid = store.add("probe", "т", {"parts": 3})
    sup.tick()
    assert sup.mode == WORK and eng.on
    assert wait_until(lambda: store.get(tid).state == COMPLETED)
    assert len(store.get(tid).checkpoint["parts"]) == 3
    assert wait_until(lambda: not sup._worker_alive())
    sup.tick()
    assert sup.mode == WAIT and not eng.on
    assert eng.calls[-3:] == ["unload", "stop", "verify"]


def test_no_tasks_engine_never_starts(env):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    sup.tick()
    assert sup.mode == WAIT and eng.calls == []


@pytest.mark.parametrize("state", [BUSY, UNKNOWN])
def test_priority_app_not_free_blocks_start(env, state):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    store.add("probe", "т")
    watch.state = state
    sup.tick()
    assert sup.mode == WAIT and eng.calls == []


def test_yield_mid_request_and_resume_from_checkpoint(env):
    store, watch, res, clock, make = env
    eng = FakeEngine(step_s=0.3)
    sup = make(eng)
    tid = store.add("probe", "т", {"parts": 4})
    sup.tick()
    assert wait_until(lambda: len(store.get(tid).checkpoint.get("parts", [])) == 2)
    time.sleep(0.1)                                    # третий запрос в процессе
    watch.state = BUSY
    t0 = time.monotonic()
    sup.tick()
    took = time.monotonic() - t0
    t = store.get(tid)
    assert t.state == INTERRUPTED and "приоритетная программа" in t.reason
    assert len(t.checkpoint["parts"]) == 2             # недописанный абзац не сохранён
    assert not eng.on and eng.calls[-3:] == ["unload", "stop", "verify"]
    assert took < 1.0                                  # запрос оборван, а не дождался конца
    assert sup.yields[-1].released

    watch.state = FREE
    clock.t += 10
    sup.tick()
    assert sup.mode == WAIT and not eng.on             # ещё ждём after_priority_s
    clock.t += 30
    sup.tick()
    assert sup.mode == WORK
    assert wait_until(lambda: store.get(tid).state == COMPLETED, 5)
    parts = store.get(tid).checkpoint["parts"]
    assert len(parts) == 4 and parts[:2] == ["абзац 1", "абзац 2"]    # сделанное не переделано


def test_segment_end_rest_with_engine_off_then_continue(env):
    store, watch, res, clock, make = env
    eng = FakeEngine(step_s=0.05)
    sup = make(eng)
    tid = store.add("probe", "т", {"parts": 1000})
    sup.tick()
    assert wait_until(lambda: len(store.get(tid).checkpoint.get("parts", [])) >= 1)
    clock.t += 100
    sup.tick()
    assert sup.mode == REST and not eng.on
    assert store.get(tid).state == INTERRUPTED
    clock.t += 49
    sup.tick()
    assert sup.mode == REST and not eng.on
    clock.t += 1
    sup.tick()
    assert sup.mode == WORK and eng.on
    sup.shutdown()


def test_vram_not_released_blocks_new_work(env):
    store, watch, res, clock, make = env
    eng = FakeEngine(step_s=0.05, release=False)
    sup = make(eng)
    store.add("probe", "т", {"parts": 1000})
    sup.tick()
    time.sleep(0.1)
    watch.state = BUSY
    sup.tick()
    assert sup.vram_blocked and not sup.yields[-1].released
    watch.state = FREE
    clock.t += 100
    res.used = 5000                                    # видеопамять так и занята
    sup.tick()
    assert sup.mode == WAIT and "видеопамять" in sup.reason and eng.calls.count("start") == 1
    res.used = 500
    sup.tick()
    assert sup.mode == WORK
    sup.shutdown()


def test_game_or_low_ram_blocks_start(env):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    store.add("probe", "т")
    res.game = {"cs2.exe"}
    sup.tick()
    assert sup.mode == WAIT and "игра" in sup.reason
    res.game = set()
    res.ram = 1.0
    sup.tick()
    assert sup.mode == WAIT and "памяти" in sup.reason and eng.calls == []


def test_unknown_job_kind_fails_task_not_crash(env):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    tid = store.add("nonsense", "т")
    sup.tick()
    assert wait_until(lambda: store.get(tid).state == "FAILED")


def test_errand_completion_sends_windows_notification(env):
    """Раздел 10 задания: «поручение готово» — уведомление, не только у других видов задач."""
    store, watch, res, clock, _ = env
    s = config.Settings(segment_s=100, rest_s=50, after_priority_s=30)
    calls = []
    eng = FakeEngine()
    sup = Supervisor(store, watch, eng, res, s, clock=clock, notify=lambda title, msg: calls.append((title, msg)))
    tid = store.add("errand", "Поручение: расскажи о геополитике", {"text": "расскажи о геополитике"})
    sup.tick()
    assert wait_until(lambda: store.get(tid).state == COMPLETED)
    assert calls and calls[0][0] == "Nexus: поручение готово"
    assert calls[0][1] == "Поручение: расскажи о геополитике"


def test_pull_model_job_calls_engine_pull(env):
    store, watch, res, clock, make = env
    eng = FakeEngine()
    sup = make(eng)
    tid = store.add("pull_model", "т", {"model": "qwen3.5:9b"})
    sup.tick()
    assert wait_until(lambda: store.get(tid).state == COMPLETED)
    assert store.get(tid).checkpoint["ok"] is True
    assert ("pull", "qwen3.5:9b") in eng.calls


def test_probe_completion_does_not_notify(env):
    store, watch, res, clock, _ = env
    s = config.Settings(segment_s=100, rest_s=50, after_priority_s=30)
    calls = []
    eng = FakeEngine()
    sup = Supervisor(store, watch, eng, res, s, clock=clock, notify=lambda title, msg: calls.append((title, msg)))
    tid = store.add("probe", "т", {"parts": 1})
    sup.tick()
    assert wait_until(lambda: store.get(tid).state == COMPLETED)
    assert calls == []
