"""Личные настройки: файл, загрузка, сохранение, и то, что пресеты реально меняют поведение задач."""
import json

import pytest

from nexus import config
from nexus.jobs import CredibilityJob, DigestJob, ErrandJob
from nexus.research.match import Topic


@pytest.fixture
def root(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    monkeypatch.setattr(config, "PERSONAL_DIR", tmp_path / "personal")
    return tmp_path


def test_load_settings_without_file_is_defaults(root):
    s = config.load_settings(root / "no-such-file.json")
    assert s.research_mode == "balanced" and s.custom_instruction == "" and s.segment_s == 25 * 60


def test_load_settings_applies_overrides(root):
    p = root / "settings.json"
    p.write_text(json.dumps({"segment_min": 10, "rest_min": 2, "after_priority_min": 1,
                             "research_mode": "fast", "custom_instruction": "  коротко  "}), encoding="utf-8")
    s = config.load_settings(p)
    assert s.segment_s == 600 and s.rest_s == 120 and s.after_priority_s == 60
    assert s.research_mode == "fast" and s.custom_instruction == "коротко"


def test_load_settings_applies_model_overrides(root):
    p = root / "settings.json"
    p.write_text(json.dumps({"work_model": "qwen3.5:9b", "cpu_model": "qwen3.5:4b", "embed_model": "bge-m3"}),
                encoding="utf-8")
    s = config.load_settings(p)
    assert s.work_model == "qwen3.5:9b" and s.cpu_model == "qwen3.5:4b" and s.embed_model == "bge-m3"


def test_load_settings_ignores_blank_model_overrides(root):
    p = root / "settings.json"
    p.write_text(json.dumps({"work_model": "   "}), encoding="utf-8")
    s = config.load_settings(p)
    assert s.work_model == "qwen3.5:9b"       # по умолчанию — пустое значение не подставляется


def test_load_settings_ignores_unknown_mode(root):
    p = root / "settings.json"
    p.write_text(json.dumps({"research_mode": "сверхбыстро-непонятно"}), encoding="utf-8")
    assert config.load_settings(p).research_mode == "balanced"


def test_load_settings_survives_broken_json(root):
    p = root / "settings.json"
    p.write_text("{не json вовсе", encoding="utf-8")
    s = config.load_settings(p)
    assert s.research_mode == "balanced"


def test_save_settings_overrides_roundtrip(root):
    p = root / "personal" / "settings.json"
    config.save_settings_overrides({"segment_min": 15, "research_mode": "thorough"}, p)
    s = config.load_settings(p)
    assert s.segment_s == 900 and s.research_mode == "thorough"


def test_save_settings_overrides_respects_safety(tmp_path, monkeypatch):
    import nexus.safety as safety
    from nexus.safety import ForbiddenWrite
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    with pytest.raises(ForbiddenWrite):
        config.save_settings_overrides({"segment_min": 1}, tmp_path.parent / "outside.json")


# ---------- пресеты реально меняют поведение ----------

T_AI = Topic("ai", "ИИ", 1, [], how_to_present="коротко")


class RecordingCtx:
    model = "fake"

    def __init__(self, mode="balanced", custom="", answer="ответ"):
        self.settings = type("S", (), {"research_mode": mode, "custom_instruction": custom})()
        self.answer = answer
        self.calls = []

    def chat(self, messages, num_predict=400, fmt=None, temperature=None):
        self.calls.append({"messages": messages, "num_predict": num_predict, "fmt": fmt})
        return self.answer


def test_digest_job_uses_mode_predict_length(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.sources.feeds import Entry
    from nexus.sources.collector import Source
    from nexus.sources.store import ItemStore
    items = ItemStore(tmp_path / "n.db")
    items.add_entries("s", [Entry("Заголовок", "https://s/1")])
    iid = items.items_in_state("NEW")[0]["id"]
    items.set_matches(iid, [], "SELECTED")
    job = DigestJob(items, [T_AI], [Source("s", "S", "rss")], fetch_text=lambda u: "текст статьи")

    fast = RecordingCtx(mode="fast")
    job.step(fast, {"item_ids": [iid], "topics": {str(iid): "ai"}}, {})
    assert fast.calls[0]["num_predict"] == config.RESEARCH_MODES["fast"]["digest_predict"]


def test_digest_job_adds_custom_instruction(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.sources.feeds import Entry
    from nexus.sources.collector import Source
    from nexus.sources.store import ItemStore
    items = ItemStore(tmp_path / "n.db")
    items.add_entries("s", [Entry("Заголовок", "https://s/1")])
    iid = items.items_in_state("NEW")[0]["id"]
    items.set_matches(iid, [], "SELECTED")
    job = DigestJob(items, [T_AI], [Source("s", "S", "rss")], fetch_text=lambda u: "текст статьи")
    ctx = RecordingCtx(custom="пиши стихами")
    job.step(ctx, {"item_ids": [iid], "topics": {str(iid): "ai"}}, {})
    assert "пиши стихами" in ctx.calls[0]["messages"][0]["content"]


def test_errand_job_uses_mode_predict_and_style():
    job = ErrandJob()
    good = json.dumps({"verdict": "allow", "why": "ок"})

    class AllowCtx(RecordingCtx):
        def chat(self, messages, num_predict=400, fmt=None, temperature=None):
            self.calls.append({"messages": messages, "num_predict": num_predict})
            return good if fmt is not None else self.answer
    ctx = AllowCtx(mode="thorough", custom="без воды")
    cp, done = job.step(ctx, {"text": "расскажи о геополитике"}, {})
    assert done and cp["decision"] == "allow"
    answer_call = ctx.calls[-1]
    assert answer_call["num_predict"] == config.RESEARCH_MODES["thorough"]["digest_predict"]
    assert "без воды" in answer_call["messages"][0]["content"]


def test_credibility_job_skips_dispute_check_in_fast_mode(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    from nexus.sources.feeds import Entry
    from nexus.sources.collector import Source
    from nexus.sources.store import ItemStore
    items = ItemStore(tmp_path / "n.db")
    items.add_entries("high", [Entry("Boston Dynamics adds wheels to Atlas humanoid robot", "https://a/1")])
    items.add_entries("high2", [Entry("Boston Dynamics gives Atlas humanoid robot new wheels", "https://b/1")])
    ids = [r["id"] for r in items.items_in_state("NEW")]
    for i in ids:
        items.save_report(i, "ai", "т", "fake", "DIGESTED")
    high = Source("high", "H", "rss", reliability="high")
    high2 = Source("high2", "H2", "rss", reliability="high")
    job = CredibilityJob(items, [high, high2])
    ctx = RecordingCtx(mode="fast")
    job.step(ctx, {"clusters": [{"topic_id": "ai", "item_ids": ids}]}, {})
    assert ctx.calls == []                                            # в быстром режиме модель вообще не звали
