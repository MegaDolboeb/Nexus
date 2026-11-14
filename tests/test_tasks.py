import pytest

from nexus import config
from nexus.tasks import (CANCELLED, COMPLETED, INTERRUPTED, QUEUED, RUNNING, BadTransition, TaskStore)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)            # writable() пускает только в «папку Nexus»
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    s = TaskStore(tmp_path / "t.db")
    yield s
    s.close()


def test_add_and_get(store):
    tid = store.add("probe", "т", {"parts": 3})
    t = store.get(tid)
    assert t.state == QUEUED and t.payload == {"parts": 3} and t.checkpoint == {}


def test_allowed_and_forbidden_transitions(store):
    tid = store.add("probe", "т")
    store.transition(tid, RUNNING, "r")
    store.transition(tid, COMPLETED, "ok")
    with pytest.raises(BadTransition):
        store.transition(tid, RUNNING)
    with pytest.raises(BadTransition):
        store.transition(store.add("probe", "т2"), COMPLETED)     # из очереди сразу в готово нельзя


def test_checkpoint_only_while_running(store):
    tid = store.add("probe", "т")
    with pytest.raises(BadTransition):
        store.save_checkpoint(tid, {"parts": ["a"]})
    store.transition(tid, RUNNING)
    store.save_checkpoint(tid, {"parts": ["a"]})
    store.transition(tid, INTERRUPTED, "занято")
    assert store.get(tid).checkpoint == {"parts": ["a"]}
    assert store.get(tid).reason == "занято"


def test_next_runnable_priority_then_order(store):
    a = store.add("probe", "a")
    b = store.add("probe", "b", priority=5)
    store.add("probe", "c")
    assert store.next_runnable().id == b
    store.transition(b, CANCELLED)
    assert store.next_runnable().id == a


def test_interrupted_is_runnable_and_keeps_checkpoint(store):
    tid = store.add("probe", "т")
    store.transition(tid, RUNNING)
    store.save_checkpoint(tid, {"parts": ["x"]})
    store.transition(tid, INTERRUPTED, "занято")
    t = store.next_runnable()
    assert t.id == tid and t.checkpoint == {"parts": ["x"]}


def test_recent_events_newest_first_across_tasks(store):
    a = store.add("probe", "Задача А")
    b = store.add("errand", "Задача Б")
    store.transition(a, RUNNING, "начал")
    store.transition(b, RUNNING, "начал")
    store.transition(a, COMPLETED, "готово")
    events = store.recent_events()
    assert events[0]["task_id"] == a and events[0]["to_state"] == COMPLETED and events[0]["reason"] == "готово"
    assert events[0]["kind"] == "probe" and events[0]["title"] == "Задача А"
    # порядок: самое новое сверху
    ats = [e["at"] for e in events]
    assert ats == sorted(ats, reverse=True)


def test_recent_events_respects_limit(store):
    for i in range(5):
        store.add("probe", f"т{i}")
    assert len(store.recent_events(limit=3)) == 3


def test_recover_after_restart(store, tmp_path):
    tid = store.add("probe", "т")
    store.transition(tid, RUNNING)
    store.save_checkpoint(tid, {"parts": ["x"]})
    store.close()
    again = TaskStore(tmp_path / "t.db")
    assert again.recover_after_restart() == 1
    t = again.get(tid)
    assert t.state == INTERRUPTED and t.checkpoint == {"parts": ["x"]}
    assert again.history(tid)[-1][1] == INTERRUPTED
    again.close()
