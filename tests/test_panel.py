import pytest
from fastapi.testclient import TestClient

from nexus.panel import data as panel_data
from nexus.panel.server import app
from nexus.panel.token import get_token
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore
from nexus.research.match import Topic


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    return tmp_path / "secrets" / "panel_token.txt"


def test_token_is_created_once_and_reused(secrets):
    t1 = get_token(secrets)
    t2 = get_token(secrets)
    assert t1 == t2 and len(t1) == 48               # token_hex(24) -> 48 hex chars
    assert secrets.exists()


def test_token_is_random_per_file(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    a = get_token(tmp_path / "secrets" / "a.txt")
    b = get_token(tmp_path / "secrets" / "b.txt")
    assert a != b


def test_token_outside_root_is_forbidden(tmp_path, monkeypatch):
    import nexus.safety as safety
    from nexus.safety import ForbiddenWrite
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    with pytest.raises(ForbiddenWrite):
        get_token(tmp_path.parent / "outside.txt")


# ---------- data.py ----------

@pytest.fixture
def item_store(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    s = ItemStore(tmp_path / "n.db")
    yield s
    s.close()


def test_priority_status_labels(tmp_path, monkeypatch):
    class FakeObs:
        def __init__(self, state, busy=None, unknown=None):
            self.state, self.busy, self.unknown = state, busy or [], unknown or []
            self.may_work = state == "FREE"

    class FakeWatch:
        def __init__(self, state):
            self.state = state

        def check(self):
            return FakeObs(self.state, busy=["открыта программа"] if self.state == "BUSY" else [])

    import nexus.panel.data as d
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    (personal / "settings.json").write_text('{"priority_name": "Компаньон"}', encoding="utf-8")

    monkeypatch.setattr(d, "PriorityWatch", lambda settings=None: FakeWatch("FREE"))
    assert d.priority_status()["text"] == "Работа идёт — Компаньон сейчас свободна"
    monkeypatch.setattr(d, "PriorityWatch", lambda settings=None: FakeWatch("BUSY"))
    out = d.priority_status()
    assert out["text"] == "Работа прекращена — Компаньон сейчас занята" and out["reasons"] == ["открыта программа"]
    monkeypatch.setattr(d, "PriorityWatch", lambda settings=None: FakeWatch("UNKNOWN"))
    assert "ждёт" in d.priority_status()["text"]


def test_priority_status_when_not_configured(tmp_path, monkeypatch):
    import nexus.panel.data as d
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    out = d.priority_status()
    assert out["state"] == "NOT_CONFIGURED" and out["may_work"] is True


def test_engine_status_uses_runtime_cache_without_a_network_call(monkeypatch):
    import nexus.panel.data as d

    def boom(*a, **k):
        raise AssertionError("не должен был звать Engine напрямую — есть кэш Runtime")
    monkeypatch.setattr(d, "Engine", boom)
    monkeypatch.setattr(d, "get_runtime", lambda: type("RT", (), {"engine_alive_cached": True})())
    assert d.engine_status()["alive"] is True


def test_engine_status_falls_back_without_runtime_cache(monkeypatch):
    import nexus.panel.data as d
    monkeypatch.setattr(d, "get_runtime", lambda: object())         # нет engine_alive_cached
    monkeypatch.setattr(d, "Engine", lambda *a, **k: type("E", (), {"alive": lambda self: True})())
    assert d.engine_status()["alive"] is True


def test_engine_status_never_raises(monkeypatch):
    import nexus.panel.data as d

    class Boom:
        def __init__(self, *a, **k):
            pass

        def alive(self):
            raise RuntimeError("видеокарта недоступна")
    monkeypatch.setattr(d, "Engine", Boom)
    monkeypatch.setattr(d, "get_runtime", lambda: object())        # нет engine_alive_cached — прямая проверка
    out = d.engine_status()
    assert out["alive"] is False


def test_topics_with_counts_orders_by_priority_then_volume(item_store, monkeypatch):
    import nexus.panel.data as d
    monkeypatch.setattr(d, "load_topics", lambda: [
        Topic("business", "Бизнес", 1, []), Topic("ai", "ИИ", 1, []), Topic("space", "Космос", 3, [])])
    monkeypatch.setattr(d, "ItemStore", lambda: item_store)
    monkeypatch.setattr(item_store, "counts_by_topic", lambda: {"ai": 5, "business": 1})
    out = d.topics_with_counts()
    assert [t["id"] for t in out] == ["ai", "business", "space"]
    assert out[0]["count"] == 5 and out[2]["count"] == 0


def test_recent_reports_includes_credibility_and_badge(item_store, monkeypatch):
    import nexus.panel.data as d
    monkeypatch.setattr(d, "ItemStore", lambda: item_store)
    item_store.add_entries("habr", [Entry("Заголовок материала", "https://habr.ru/1")])
    iid = item_store.items_in_state("NEW")[0]["id"]
    item_store.save_report(iid, "ai", "текст", "fake", "DIGESTED")
    item_store.save_credibility("ai", "НЕ ПРОВЕРЕНО", "только низкая надёжность", True, [iid])
    out = d.recent_reports()
    assert out[0]["status"] == "Не проверено" and out[0]["low_reliability"] is True


# ---------- server.py ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    import nexus.panel.token as tok
    monkeypatch.setattr(tok, "TOKEN_FILE", tmp_path / "secrets" / "panel_token.txt")
    import nexus.panel.data as d
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir(parents=True, exist_ok=True)
    (personal / "settings.json").write_text('{"priority_name": "Компаньон"}', encoding="utf-8")
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    monkeypatch.setattr(d, "PriorityWatch", lambda settings=None: type("W", (), {"check": lambda self: type(
        "O", (), {"state": "FREE", "busy": [], "unknown": [], "may_work": True})()})())
    monkeypatch.setattr(d, "Engine", lambda *a, **k: type("E", (), {"alive": lambda self: False})())
    monkeypatch.setattr(d, "ItemStore", lambda: ItemStore(tmp_path / "n.db"))
    monkeypatch.setattr(d, "TaskStore", lambda: __import__("nexus.tasks", fromlist=["TaskStore"]).TaskStore(tmp_path / "n.db"))
    monkeypatch.setattr(d, "load_topics", lambda: [])

    class FakeRuntime:
        state = "stopped"

        def start(self): pass

        def pause(self): pass

        def stop(self): pass
    monkeypatch.setattr(d, "get_runtime", lambda: FakeRuntime())
    return TestClient(app)


def test_root_requires_correct_token(client, tmp_path):
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    assert client.get("/").status_code == 401
    assert client.get("/", params={"token": "неверный"}).status_code == 401
    r = client.get("/", params={"token": token})
    assert r.status_code == 200 and "Nexus" in r.text and token in r.text


def test_api_home_requires_header_token(client, tmp_path):
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    assert client.get("/api/home").status_code == 401
    assert client.get("/api/home", headers={"X-Nexus-Token": "wrong-token"}).status_code == 401
    r = client.get("/api/home", headers={"X-Nexus-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["priority"]["text"] == "Работа идёт — Компаньон сейчас свободна" and "generated" in body
