"""Фото приоритетной программы и страницы «подробно» — материал и тема памяти."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from nexus.panel import data as panel_data
from nexus.panel.server import app
from nexus.research.match import Topic
from nexus.sources.collector import Source
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    items = ItemStore(tmp_path / "n.db")
    yield tmp_path, items
    items.close()


# ---------- фото ----------

def test_save_priority_photo_roundtrip(ctx):
    tmp_path, _ = ctx
    data_url = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
    panel_data.save_priority_photo(data_url)
    info = panel_data.priority_photo_path()
    assert info is not None
    path, mime = info
    assert path.exists() and mime == "image/png" and path.read_bytes() == TINY_PNG


def test_save_priority_photo_rejects_bad_mime(ctx):
    with pytest.raises(ValueError, match="PNG, JPEG"):
        panel_data.save_priority_photo("data:image/gif;base64,AAAA")       # image/*, но не из разрешённых


def test_save_priority_photo_rejects_non_image(ctx):
    with pytest.raises(ValueError, match="непонятный формат"):
        panel_data.save_priority_photo("data:application/pdf;base64,AAAA")


def test_save_priority_photo_rejects_malformed(ctx):
    with pytest.raises(ValueError, match="непонятный формат"):
        panel_data.save_priority_photo("не data url вообще")


def test_save_priority_photo_rejects_too_big(ctx, monkeypatch):
    monkeypatch.setattr(panel_data, "MAX_PHOTO_BYTES", 10)
    data_url = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
    with pytest.raises(ValueError, match="8 МБ"):
        panel_data.save_priority_photo(data_url)


def test_priority_photo_path_none_without_setting(ctx):
    assert panel_data.priority_photo_path() is None


# ---------- material_detail / memory_detail ----------

T_AI = Topic("ai", "ИИ", 1, [])


def test_material_detail_unknown_id_is_none(ctx, monkeypatch):
    tmp_path, items = ctx
    monkeypatch.setattr(panel_data, "ItemStore", lambda: items)
    from nexus.memory.store import MemoryStore
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: MemoryStore(tmp_path / "n.db"))
    assert panel_data.material_detail(999) is None


def test_material_detail_full_fields(ctx, monkeypatch):
    tmp_path, items = ctx
    monkeypatch.setattr(panel_data, "ItemStore", lambda: items)
    monkeypatch.setattr(panel_data, "load_sources", lambda: [Source("s", "Источник", "rss")])
    monkeypatch.setattr(panel_data, "load_topics", lambda: [T_AI])
    from nexus.memory.store import MemoryStore
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: MemoryStore(tmp_path / "n.db"))
    items.add_entries("s", [Entry("Заголовок материала", "https://s/1")])
    iid = items.items_in_state("NEW")[0]["id"]
    items.save_report(iid, "ai", "Полный текст выжимки.", "fake", "DIGESTED")
    items.save_credibility("ai", "ЧАСТИЧНО", "причина", False, [iid])
    m = panel_data.material_detail(iid)
    assert m["title"] == "Заголовок материала" and m["text"] == "Полный текст выжимки."
    assert m["source"] == "Источник" and m["topic"] == "ИИ" and m["status"] == "Частично"
    assert m["reason"] == "причина" and m["memory_id"] is None


def test_memory_detail_unknown_id_is_none(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.memory.store import MemoryStore
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: MemoryStore(tmp_path / "n.db"))
    assert panel_data.memory_detail(999) is None


def test_memory_detail_full_fields(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.memory.store import MemoryStore
    mem = MemoryStore(tmp_path / "n.db")
    mid = mem.create("ai", "Тема", "суть", "выводы v1", "отчёт", "ЧАСТИЧНО", True, [], item_id=1)
    mem.update(mid, "суть", "выводы v2", "отчёт обновлён", "ПОДТВЕРЖДЕНО", False, [], item_id=2, reason="новое")
    monkeypatch.setattr(panel_data, "load_topics", lambda: [T_AI])
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: mem)
    d = panel_data.memory_detail(mid)
    assert d["conclusions"] == "выводы v2" and d["report"] == "отчёт обновлён"
    assert d["topic"] == "ИИ" and d["status"] == "Подтверждено" and d["low_reliability"] is False
    assert len(d["links"]) == 2 and d["history"][0]["reason"] == "новое"


# ---------- маршруты ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus import config
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    import nexus.panel.token as tok
    monkeypatch.setattr(tok, "TOKEN_FILE", tmp_path / "secrets" / "panel_token.txt")
    items = ItemStore(tmp_path / "n.db")
    monkeypatch.setattr(panel_data, "PriorityWatch", lambda settings=None: type("W", (), {"check": lambda self: type(
        "O", (), {"state": "FREE", "busy": [], "unknown": [], "may_work": True})()})())
    monkeypatch.setattr(panel_data, "Engine", lambda *a, **k: type("E", (), {"alive": lambda self: False})())
    monkeypatch.setattr(panel_data, "ItemStore", lambda: items)
    monkeypatch.setattr(panel_data, "TaskStore", lambda: __import__("nexus.tasks", fromlist=["TaskStore"]).TaskStore(tmp_path / "n.db"))
    monkeypatch.setattr(panel_data, "load_topics", lambda: [T_AI])
    monkeypatch.setattr(panel_data, "load_sources", lambda: [Source("s", "Источник", "rss")])
    from nexus.memory.store import MemoryStore
    monkeypatch.setattr(panel_data, "MemoryStore", lambda: MemoryStore(tmp_path / "n.db"))

    class FakeRuntime:
        state = "stopped"
        reason = ""

        def start(self): pass

        def pause(self): pass

        def stop(self): pass
    monkeypatch.setattr(panel_data, "get_runtime", lambda: FakeRuntime())
    from nexus.panel.token import get_token
    token = get_token(tmp_path / "secrets" / "panel_token.txt")
    return TestClient(app), items, tmp_path, token


def test_material_route_404_when_missing(client):
    c, _, _, token = client
    assert c.get("/material/999", params={"token": token}).status_code == 404


def test_material_route_renders_full_text(client):
    c, items, _, token = client
    items.add_entries("s", [Entry("Заголовок материала", "https://s/1")])
    iid = items.items_in_state("NEW")[0]["id"]
    items.save_report(iid, "ai", "Полный текст выжимки, которого нет в кратком списке.", "fake", "DIGESTED")
    items.save_credibility("ai", "ЧАСТИЧНО", "x", False, [iid])
    r = c.get(f"/material/{iid}", params={"token": token})
    assert r.status_code == 200 and "Полный текст выжимки, которого нет в кратком списке." in r.text


def test_memory_route_404_and_200(client):
    c, _, tmp_path, token = client
    assert c.get("/memory/999", params={"token": token}).status_code == 404
    from nexus.memory.store import MemoryStore
    mem = MemoryStore(tmp_path / "n.db")
    mid = mem.create("ai", "Тема памяти", "суть", "полные выводы темы", "", "ЧАСТИЧНО", False, [], item_id=1)
    r = c.get(f"/memory/{mid}", params={"token": token})
    assert r.status_code == 200 and "полные выводы темы" in r.text


def test_photo_asset_requires_token_and_404_without_photo(client):
    c, _, _, token = client
    assert c.get("/assets/priority").status_code == 401
    assert c.get("/assets/priority", params={"token": token}).status_code == 404


def test_photo_upload_route_then_served(client):
    c, _, _, token = client
    data_url = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
    r = c.post("/api/settings/photo", headers={"X-Nexus-Token": token}, json={"data_url": data_url})
    assert r.status_code == 200 and r.json()["ok"] is True
    got = c.get("/assets/priority", params={"token": token})
    assert got.status_code == 200 and got.content == TINY_PNG and got.headers["content-type"] == "image/png"


def test_photo_upload_route_rejects_bad_input(client):
    c, _, _, token = client
    r = c.post("/api/settings/photo", headers={"X-Nexus-Token": token}, json={"data_url": "мусор"})
    assert r.status_code == 400
