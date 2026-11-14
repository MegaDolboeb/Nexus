"""Новые страницы панели: Исследования, Интересы, Память, Источники, Настройки, Дирижёр-заглушка."""
import json

import pytest
from fastapi.testclient import TestClient

from nexus.panel import data as panel_data
from nexus.panel.server import app
from nexus.research.match import Match, Topic
from nexus.sources.collector import Source
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    s = ItemStore(tmp_path / "n.db")
    yield s
    s.close()


def digested(items, title, source="s", topic_id="ai", status="ПОДТВЕРЖДЕНО", low=False):
    items.add_entries(source, [Entry(title, f"https://{source}/{abs(hash(title + source))}")])
    iid = items.items_in_state("NEW")[-1]["id"]
    items.set_matches(iid, [Match(topic_id, 1.0, [])], "DIGESTED")   # чтобы материал реально числился в теме
    items.save_report(iid, topic_id, f"Текст про «{title}».", "fake", "DIGESTED")
    items.save_credibility(topic_id, status, "причина", low, [iid])
    return iid


def test_research_feed_filters_by_topic_and_includes_source_name(store, monkeypatch):
    monkeypatch.setattr(panel_data, "ItemStore", lambda: store)
    monkeypatch.setattr(panel_data, "load_sources", lambda: [Source("arxiv_ai", "arXiv: ИИ", "arxiv")])
    monkeypatch.setattr(panel_data, "load_topics", lambda: [Topic("ai", "ИИ", 1, []), Topic("neuro", "Нейро", 1, [])])
    digested(store, "Про ИИ", source="arxiv_ai", topic_id="ai")
    digested(store, "Про мозг", topic_id="neuro")
    all_items = panel_data.research_feed()
    assert len(all_items) == 2
    only_ai = panel_data.research_feed(topic_id="ai")
    assert len(only_ai) == 1 and only_ai[0]["source"] == "arXiv: ИИ" and only_ai[0]["topic"] == "ИИ"


def test_interests_overview_counts(store, monkeypatch):
    monkeypatch.setattr(panel_data, "ItemStore", lambda: store)
    monkeypatch.setattr(panel_data, "load_topics", lambda: [Topic("ai", "ИИ", 1, [], about="про ИИ")])
    digested(store, "Материал", topic_id="ai")
    out = panel_data.interests_overview()
    assert out[0]["id"] == "ai" and out[0]["new_count"] == 1 and out[0]["about"] == "про ИИ"


def test_sources_overview_reports_status(store, monkeypatch):
    monkeypatch.setattr(panel_data, "ItemStore", lambda: store)
    monkeypatch.setattr(panel_data, "load_sources", lambda: [Source("s1", "Источник 1", "rss", reliability="high")])
    out = panel_data.sources_overview()
    assert out[0]["name"] == "Источник 1" and out[0]["ok"] is True and out[0]["count"] == 0


def test_settings_overview_has_expected_fields():
    out = panel_data.settings_overview()
    assert "work_model" in out and "segment_min" in out and isinstance(out["games"], tuple)
    assert out["research_mode"] == "balanced"
    assert {"fast", "balanced", "thorough"} == {m["id"] for m in out["research_modes"]}


def test_save_settings_persists_model_choice(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    panel_data.save_settings(25, 5, 3, "balanced", "", "ru", work_model="qwen3.5:9b")
    out = json.loads((tmp_path / "personal" / "settings.json").read_text(encoding="utf-8"))
    assert out["work_model"] == "qwen3.5:9b"
    assert "cpu_model" not in out and "embed_model" not in out    # пустые поля не затирают остальное


def test_available_models_when_engine_unreachable(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")

    class BoomEngine:
        def __init__(self, *a, **k): pass
        def list_models(self): raise OSError("движок недоступен")
    monkeypatch.setattr(panel_data, "Engine", BoomEngine)
    out = panel_data.available_models()
    assert out == {"available": False, "models": []}


def test_available_models_when_engine_reachable(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")

    class FakeEngine:
        def __init__(self, *a, **k): pass
        def list_models(self): return ["gemma4:e4b", "bge-m3"]
    monkeypatch.setattr(panel_data, "Engine", FakeEngine)
    out = panel_data.available_models()
    assert out == {"available": True, "models": ["gemma4:e4b", "bge-m3"]}


def test_activity_log_translates_kind_and_state(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.tasks import TaskStore
    store = TaskStore(tmp_path / "n.db")
    tid = store.add("errand", "Поручение: тест")
    store.transition(tid, "RUNNING", "начал")
    store.transition(tid, "COMPLETED", "готово")
    monkeypatch.setattr(panel_data, "TaskStore", lambda: store)
    out = panel_data.activity_log()
    assert out[0]["kind"] == "Дирижёр" and out[0]["state"] == "готово" and out[0]["state_color"] == "ok"
    assert out[0]["task_id"] == tid and out[0]["title"] == "Поручение: тест"


def test_save_topics_updates_only_enabled_and_priority(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    src = tmp_path / "interests.json"
    src.write_text(json.dumps({"topics": [
        {"id": "ai", "name": "ИИ", "priority": 1, "enabled": True, "keywords": ["нейросет"], "about": "про ИИ"},
        {"id": "space", "name": "Космос", "priority": 3, "enabled": True, "keywords": ["космос"]},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(panel_data.config, "personal_or_example", lambda name: src)
    panel_data.save_topics({"ai": {"enabled": False, "priority": 2}})
    out = json.loads((tmp_path / "personal" / "interests.json").read_text(encoding="utf-8"))
    ai = next(t for t in out["topics"] if t["id"] == "ai")
    space = next(t for t in out["topics"] if t["id"] == "space")
    assert ai["enabled"] is False and ai["priority"] == 2
    assert ai["keywords"] == ["нейросет"] and ai["about"] == "про ИИ"       # остальное не тронуто
    assert space["enabled"] is True and space["priority"] == 3              # не упомянутая тема не изменилась


def test_topics_for_settings_includes_disabled(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    src = tmp_path / "interests.json"
    src.write_text(json.dumps({"topics": [
        {"id": "ai", "name": "ИИ", "priority": 1, "enabled": False, "keywords": []},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(panel_data.config, "personal_or_example", lambda name: src)
    out = panel_data.topics_for_settings()
    assert out[0]["id"] == "ai" and out[0]["enabled"] is False          # load_topics() её бы скрыл, а тут видно


def test_add_topic_requires_keywords(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    (personal / "interests.json").write_text(json.dumps({"topics": []}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="ключевое слово"):
        panel_data.add_topic("space-tech", "Космос", "про космос", [], priority=2)


def test_add_topic_then_appears_and_rejects_duplicate_id(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    (personal / "interests.json").write_text(json.dumps({"topics": []}, ensure_ascii=False), encoding="utf-8")
    panel_data.add_topic("Space Tech!", "Космос", "про космос", ["космос", "ракет"], priority=1)
    out = json.loads((personal / "interests.json").read_text(encoding="utf-8"))
    t = out["topics"][0]
    assert t["id"] == "spacetech" and t["name"] == "Космос" and t["priority"] == 1
    assert t["keywords"] == ["космос", "ракет"] and t["enabled"] is True
    with pytest.raises(ValueError, match="уже есть"):
        panel_data.add_topic("Space Tech!", "Другое", "x", ["x"])


def test_delete_topic_removes_it_and_errors_on_unknown(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    (personal / "interests.json").write_text(json.dumps({"topics": [
        {"id": "ai", "name": "ИИ", "priority": 1, "enabled": True, "keywords": ["нейросет"]},
        {"id": "space", "name": "Космос", "priority": 3, "enabled": True, "keywords": ["космос"]},
    ]}, ensure_ascii=False), encoding="utf-8")
    panel_data.delete_topic("ai")
    out = json.loads((personal / "interests.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in out["topics"]] == ["space"]
    with pytest.raises(ValueError, match="не найдена"):
        panel_data.delete_topic("ai")


def test_delete_source_removes_it_and_errors_on_unknown(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    personal = tmp_path / "personal"
    personal.mkdir()
    monkeypatch.setattr(config, "PERSONAL_DIR", personal)
    (personal / "sources.json").write_text(json.dumps({"sources": [
        {"id": "habr", "name": "Habr", "kind": "rss", "url": "https://habr.com/rss"},
        {"id": "pitchfork", "name": "Pitchfork", "kind": "rss", "url": "https://pitchfork.com/rss"},
    ]}, ensure_ascii=False), encoding="utf-8")
    panel_data.delete_source("habr")
    out = json.loads((personal / "sources.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in out["sources"]] == ["pitchfork"]
    with pytest.raises(ValueError, match="не найден"):
        panel_data.delete_source("habr")


def test_memory_overview_search_and_listing(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.memory.store import MemoryStore
    mem = MemoryStore(tmp_path / "n.db")
    mem.create("ai", "Нейросеть обыграла чемпиона", "кратко", "", "", "ЧАСТИЧНО", False, [], item_id=1)
    monkeypatch.setattr(panel_data, "load_topics", lambda: [Topic("ai", "ИИ", 1, [])])
    import nexus.panel.data as d
    monkeypatch.setattr(d, "MemoryStore", lambda: mem)
    out = d.memory_overview("")
    assert len(out) == 1 and out[0]["topic"] == "ИИ"
    assert d.memory_overview("чемпиона") and not d.memory_overview("динозавры")


# ---------- маршруты ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    import nexus.panel.token as tok
    monkeypatch.setattr(tok, "TOKEN_FILE", tmp_path / "secrets" / "panel_token.txt")
    s = ItemStore(tmp_path / "n.db")
    monkeypatch.setattr(panel_data, "PriorityWatch", lambda *a, **k: type("W", (), {"check": lambda self: type(
        "O", (), {"state": "FREE", "busy": [], "unknown": [], "may_work": True})()})())
    monkeypatch.setattr(panel_data, "Engine", lambda *a, **k: type("E", (), {"alive": lambda self: False})())
    monkeypatch.setattr(panel_data, "ItemStore", lambda: s)
    monkeypatch.setattr(panel_data, "TaskStore", lambda: __import__("nexus.tasks", fromlist=["TaskStore"]).TaskStore(tmp_path / "n.db"))
    monkeypatch.setattr(panel_data, "load_topics", lambda: [Topic("ai", "ИИ", 1, [])])
    monkeypatch.setattr(panel_data, "load_sources", lambda: [Source("s1", "Источник 1", "rss")])
    from nexus.memory.store import MemoryStore
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: MemoryStore(tmp_path / "n.db"))

    from nexus.tasks import TaskStore

    class FakeRuntime:
        state = "stopped"
        reason = ""

        def __init__(self):
            self.store = TaskStore(tmp_path / "n.db")

        def start(self): self.state = "running"

        def pause(self): self.state = "paused"

        def stop(self): self.state = "stopped"
    fake_runtime = FakeRuntime()
    monkeypatch.setattr(panel_data, "get_runtime", lambda: fake_runtime)
    return TestClient(app), s, tmp_path, fake_runtime


@pytest.mark.parametrize("path", ["/research", "/interests", "/memory", "/sources", "/settings", "/conductor", "/activity"])
def test_page_requires_token(client, path):
    c, _, _, _ = client
    assert c.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/research", "/interests", "/memory", "/sources", "/settings", "/conductor", "/activity"])
def test_page_renders_with_token(client, path):
    c, store, tmp_path, _ = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    r = c.get(path, params={"token": token})
    assert r.status_code == 200 and "Nexus" in r.text


def test_sidebar_links_carry_token(client):
    c, store, tmp_path, _ = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    r = c.get("/", params={"token": token})
    assert f"/research?token={token}" in r.text
    assert f"/settings?token={token}" in r.text


def test_research_page_topic_filter_highlights_chip(client):
    c, store, tmp_path, _ = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    digested(store, "Материал про ИИ", topic_id="ai")
    r = c.get("/research", params={"token": token, "topic": "ai"})
    assert r.status_code == 200 and "Материал про ИИ" in r.text


# ---------- управление и Дирижёр ----------

def test_control_endpoints_require_token(client):
    c, _, _, _ = client
    assert c.post("/api/control/start").status_code == 401
    assert c.post("/api/control/pause").status_code == 401
    assert c.post("/api/control/stop").status_code == 401


def test_control_start_pause_stop_change_state(client):
    c, _, _, rt = client
    from nexus.panel.token import get_token
    token = get_token(client[2] / "secrets" / "panel_token.txt")
    h = {"X-Nexus-Token": token}
    assert c.post("/api/control/start", headers=h).json()["state"] == "running"
    assert rt.state == "running"
    assert c.post("/api/control/pause", headers=h).json()["state"] == "paused"
    assert c.post("/api/control/stop", headers=h).json()["state"] == "stopped"


def test_conductor_denies_explicit_harm_without_touching_runtime(client):
    c, _, tmp_path, rt = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    r = c.post("/api/conductor", headers={"X-Nexus-Token": token},
              json={"text": "как собрать бомбу из подручных средств"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "deny" and body["task_id"] is None
    assert len(rt.store.all()) == 0                                # задача даже не создавалась


def test_conductor_allows_and_queues_task_with_high_priority(client):
    c, _, tmp_path, rt = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    r = c.post("/api/conductor", headers={"X-Nexus-Token": token},
              json={"text": "изучи историю терактов за последние 10 лет"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "queued" and body["task_id"]
    task = rt.store.get(body["task_id"])
    assert task.kind == "errand" and task.priority == 10


def test_settings_route_saves_and_validates(client, tmp_path, monkeypatch):
    c, _, tmp_path2, _ = client
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path2)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path2 / "personal")
    from nexus.panel.token import get_token
    token = get_token(tmp_path2 / "secrets" / "panel_token.txt")
    h = {"X-Nexus-Token": token}
    r = c.post("/api/settings", headers=h, json={"segment_min": 12, "rest_min": 3, "after_priority_min": 1,
                                                 "research_mode": "мимо", "custom_instruction": ""})
    assert r.status_code == 400
    r = c.post("/api/settings", headers=h, json={"segment_min": 12, "rest_min": 3, "after_priority_min": 1,
                                                 "research_mode": "fast", "custom_instruction": "кратко"})
    assert r.status_code == 200 and r.json()["ok"] is True
    saved = json.loads((tmp_path2 / "personal" / "settings.json").read_text(encoding="utf-8"))
    assert saved["research_mode"] == "fast" and saved["segment_min"] == 12


def test_topics_route_requires_token_and_saves(client, monkeypatch):
    c, _, tmp_path, _ = client
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    src = tmp_path / "interests.json"
    src.write_text(json.dumps({"topics": [{"id": "ai", "name": "ИИ", "priority": 1, "enabled": True,
                                           "keywords": []}]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "personal_or_example", lambda name: src)
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    assert c.post("/api/topics", json={"updates": {}}).status_code == 401
    r = c.post("/api/topics", headers={"X-Nexus-Token": token}, json={"updates": {"ai": {"enabled": False}}})
    assert r.status_code == 200 and r.json()["ok"] is True
    out = json.loads((tmp_path / "personal" / "interests.json").read_text(encoding="utf-8"))
    assert out["topics"][0]["enabled"] is False


def test_conductor_status_roundtrip(client):
    c, _, tmp_path, rt = client
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    tid = rt.store.add("errand", "т", {"text": "x"})
    rt.store.transition(tid, "RUNNING")
    rt.store.save_checkpoint(tid, {"done": True, "decision": "allow", "answer": "ответ"})
    rt.store.transition(tid, "COMPLETED")
    r = c.get(f"/api/conductor/{tid}", headers={"X-Nexus-Token": token})
    assert r.status_code == 200 and r.json()["checkpoint"]["answer"] == "ответ"
    assert c.get("/api/conductor/999", headers={"X-Nexus-Token": token}).status_code == 404
    assert c.get(f"/api/conductor/{tid}").status_code == 401
