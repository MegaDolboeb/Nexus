import json

import pytest

from nexus.jobs import CredibilityJob
from nexus.research.credibility import (CONFIRMED, DISPUTED, LOW_RELIABILITY_BADGE, PARTIAL, UNVERIFIED,
                                         assess, cluster, dispute_messages, jaccard, parse_dispute,
                                         title_signature)
from nexus.research.planner import plan_credibility
from nexus.research.select import run_matching
from nexus.research.match import Topic
from nexus.sources.collector import Source
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore
from nexus.tasks import TaskStore

HIGH = Source("high", "Надёжный", "rss", reliability="high")
HIGH2 = Source("high2", "Другой надёжный", "rss", reliability="high")
LOW = Source("low", "Форум", "rss", reliability="low")
LOW2 = Source("low2", "Другой форум", "rss", reliability="low")
PRIMARY = Source("arxiv_ai", "arXiv", "arxiv", reliability="medium", primary=True)
SRC = {s.id: s for s in (HIGH, HIGH2, LOW, LOW2, PRIMARY)}


def test_title_signature_and_jaccard():
    a = title_signature("Boston Dynamics adds wheels to Atlas humanoid robot")
    b = title_signature("Boston Dynamics gives Atlas humanoid robot new wheels")
    c = title_signature("Квантовый компьютер побил рекорд")
    assert jaccard(a, b) > 0.4
    assert jaccard(a, c) == 0.0


def it(id_, title, source_id, topic_id="ai", t=1_800_000_000.0):
    return {"id": id_, "title": title, "source_id": source_id, "topic_id": topic_id, "published": t, "fetched": t}


def test_cluster_groups_similar_within_topic_and_window():
    items = [
        it(1, "Boston Dynamics adds wheels to Atlas humanoid robot", "a"),
        it(2, "Boston Dynamics gives Atlas humanoid robot new wheels", "b", t=1_800_000_000.0 + 3600),
        it(3, "Квантовый компьютер побил рекорд скорости", "c"),                       # другая тема по сути, но topic_id совпасть может
        it(4, "Boston Dynamics adds wheels to Atlas humanoid robot", "d", t=1_800_000_000.0 + 10 * 86400),  # далеко по времени
    ]
    groups = cluster(items)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 1, 2]
    big = next(g for g in groups if len(g) == 2)
    assert {m["id"] for m in big} == {1, 2}


def test_cluster_respects_topic_id():
    items = [it(1, "Нейросеть обыграла человека", "a", topic_id="ai"),
             it(2, "Нейросеть обыграла человека", "b", topic_id="robotics")]
    groups = cluster(items)
    assert len(groups) == 2


@pytest.mark.parametrize("members,expected,low", [
    ([{"source_id": "arxiv_ai"}], CONFIRMED, False),                                    # первоисточник один — достаточно
    ([{"source_id": "high"}, {"source_id": "high2"}], CONFIRMED, False),                 # 2 независимых надёжных
    ([{"source_id": "high"}], PARTIAL, False),
    ([{"source_id": "low"}, {"source_id": "low2"}], UNVERIFIED, True),                   # только низкая надёжность
    ([{"source_id": "high"}, {"source_id": "high"}], PARTIAL, False),                    # тот же источник дважды — не в счёт
])
def test_assess(members, expected, low):
    status, reason, low_flag = assess(members, SRC)
    assert status == expected and low_flag == low and reason


def test_parse_dispute_validates():
    ok = parse_dispute('{"same_event": true, "contradicts": false, "why": " ок "}')
    assert ok == {"same_event": True, "contradicts": False, "why": "ок"}
    with pytest.raises((ValueError, KeyError)):
        parse_dispute('{"same_event": true}')


def test_dispute_messages_contain_both_texts():
    msgs = dispute_messages("Заголовок А", "Текст А", "Заголовок Б", "Текст Б")
    assert "Текст А" in msgs[1]["content"] and "Текст Б" in msgs[1]["content"]


@pytest.fixture
def stores(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    items, tasks = ItemStore(tmp_path / "n.db"), TaskStore(tmp_path / "n.db")
    yield items, tasks
    items.close()
    tasks.close()


def digest(items, item_id, topic_id, text):
    items.save_report(item_id, topic_id, text, "fake", "DIGESTED")


def test_single_source_group_counted_without_model(stores):
    items, tasks = stores
    items.add_entries("arxiv_ai", [Entry("Новая модель бьёт рекорды в бенчмарках ИИ", "https://x/1")])
    iid = items.items_in_state("NEW")[0]["id"]
    digest(items, iid, "ai", "текст выжимки")
    assert plan_credibility(tasks, items, [PRIMARY]) is None            # одиночка — без задачи модели
    c = items.credibility_of(iid)
    assert c["status"] == CONFIRMED


def test_two_sources_without_contradiction_creates_task_then_confirms(stores):
    items, tasks = stores
    items.add_entries("high", [Entry("Boston Dynamics adds wheels to Atlas humanoid robot", "https://a/1")])
    items.add_entries("high2", [Entry("Boston Dynamics gives Atlas humanoid robot new wheels", "https://b/1")])
    ids = [r["id"] for r in items.items_in_state("NEW")]
    digest(items, ids[0], "ai", "Описание события А")
    digest(items, ids[1], "ai", "Описание события А, тоже самое")
    tid = plan_credibility(tasks, items, [HIGH, HIGH2])
    assert tid is not None
    job = CredibilityJob(items, [HIGH, HIGH2])

    class Ctx:
        model = "fake"
        settings = type("S", (), {"research_mode": "balanced", "custom_instruction": ""})()

        def chat(self, messages, num_predict=200, fmt=None, temperature=None):
            return json.dumps({"same_event": True, "contradicts": False, "why": "совпадают"})
    cp, done = job.step(Ctx(), tasks.get(tid).payload, {})
    assert done
    c = items.credibility_of(ids[0])
    assert c["status"] == CONFIRMED and c["id"] == items.credibility_of(ids[1])["id"]


def test_contradiction_sets_disputed(stores):
    items, tasks = stores
    items.add_entries("high", [Entry("Опрос показал: число жертв наводнения выросло вдвое за сутки", "https://a/2")])
    items.add_entries("high2", [Entry("Опрос показал: число жертв наводнения не изменилось за сутки", "https://b/2")])
    ids = [r["id"] for r in items.items_in_state("NEW")]
    digest(items, ids[0], "geo", "В отчёте говорится о росте числа пострадавших")
    digest(items, ids[1], "geo", "Источник утверждает, что цифры не изменились")
    tid = plan_credibility(tasks, items, [HIGH, HIGH2])
    job = CredibilityJob(items, [HIGH, HIGH2])

    class Ctx:
        model = "fake"
        settings = type("S", (), {"research_mode": "balanced", "custom_instruction": ""})()

        def chat(self, messages, num_predict=200, fmt=None, temperature=None):
            return json.dumps({"same_event": True, "contradicts": True, "why": "цифры расходятся"})
    job.step(Ctx(), tasks.get(tid).payload, {})
    assert items.credibility_of(ids[0])["status"] == DISPUTED


def test_bad_model_answer_keeps_counted_status(stores):
    items, tasks = stores
    items.add_entries("high", [Entry("Boston Dynamics adds wheels to Atlas humanoid robot", "https://a/3")])
    items.add_entries("high2", [Entry("Boston Dynamics gives Atlas humanoid robot new wheels", "https://b/3")])
    ids = [r["id"] for r in items.items_in_state("NEW")]
    digest(items, ids[0], "ai", "т")
    digest(items, ids[1], "ai", "т")
    tid = plan_credibility(tasks, items, [HIGH, HIGH2])
    job = CredibilityJob(items, [HIGH, HIGH2])

    class Ctx:
        model = "fake"
        settings = type("S", (), {"research_mode": "balanced", "custom_instruction": ""})()

        def chat(self, messages, num_predict=200, fmt=None, temperature=None):
            return "не json"
    job.step(Ctx(), tasks.get(tid).payload, {})
    assert items.credibility_of(ids[0])["status"] == CONFIRMED         # счётный статус не потерян


def test_recompute_skips_unchanged_group(stores):
    items, tasks = stores
    items.add_entries("arxiv_ai", [Entry("Новая модель бьёт рекорды в бенчмарках ИИ", "https://x/4")])
    iid = items.items_in_state("NEW")[0]["id"]
    digest(items, iid, "ai", "текст")
    plan_credibility(tasks, items, [PRIMARY])
    first = items.credibility_of(iid)["id"]
    assert plan_credibility(tasks, items, [PRIMARY]) is None
    assert items.credibility_of(iid)["id"] == first                    # не пересчитано заново
