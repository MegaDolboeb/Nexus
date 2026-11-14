import json

import pytest

from nexus.jobs import TriageJob
from nexus.research.match import Topic, keyword_in, load_topics, match_item, words
from nexus.research.planner import plan
from nexus.research.select import decide, parse_scores, run_matching
from nexus.sources.collector import Source
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore
from nexus.tasks import TaskStore

T_AI = Topic("ai", "ИИ", 1, ["нейросет", "языков модел", "llm"], "про ИИ")
T_GEN = Topic("genetics", "Генетика", 2, ["ген", "crispr"], "про гены")


@pytest.mark.parametrize("kw,text,ok", [
    ("нейросет", "Новые нейросети учатся быстрее", True),
    ("языков модел", "большие языковые модели растут", True),
    ("языков модел", "языковые и другие модели", False),          # не подряд
    ("ген", "учёные изменили гены мышей", True),
    ("ген", "ИИ-агент генерал агентство", False),                  # «ген» не ловит чужие слова
    ("llm", "LLM routing", True),
])
def test_keyword_in(kw, text, ok):
    assert keyword_in(kw, words(text)) is ok


def test_match_title_counts_more_and_freshness():
    a = match_item("Нейросеть обыграла людей", "", [T_AI])
    b = match_item("Новость дня", "нейросеть обыграла людей", [T_AI])
    assert a[0].score > b[0].score
    old = match_item("Нейросеть обыграла людей", "", [T_AI], age_days=14)
    assert old[0].score == pytest.approx(a[0].score / 4, rel=1e-3)


def test_match_respects_reliability_and_priority():
    hi = match_item("CRISPR вылечил болезнь", "", [T_GEN], reliability="high")[0].score
    lo = match_item("CRISPR вылечил болезнь", "", [T_GEN], reliability="low")[0].score
    assert hi > lo
    assert match_item("Погода в Москве", "дожди", [T_AI, T_GEN]) == []


def test_personal_topics_load():
    ts = load_topics()
    assert len(ts) >= 1 and all(t.keywords for t in ts)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    items, tasks = ItemStore(tmp_path / "n.db"), TaskStore(tmp_path / "n.db")
    yield items, tasks
    items.close()
    tasks.close()


def add(items, *titles, src="s"):
    items.add_entries(src, [Entry(t, f"https://x/{i}-{abs(hash(t))}") for i, t in enumerate(titles)])


def test_run_matching_states(stores):
    items, _ = stores
    add(items, "Нейросеть написала роман целиком сама", "Погода на выходные обещает быть тёплой")
    counts = run_matching(items, [T_AI], [Source("s", "S", "rss")])
    assert counts == {"MATCHED": 1, "SKIPPED": 1}
    assert run_matching(items, [T_AI], []) == {"MATCHED": 0, "SKIPPED": 0}       # повторно не трогает


@pytest.mark.parametrize("s,expected", [
    ({"relevance": 4, "significance": 4, "novelty": 3}, "SELECTED"),
    ({"relevance": 3, "significance": 5, "novelty": 5}, "REJECTED"),
    ({"relevance": 5, "significance": 3, "novelty": 2}, "REJECTED"),
    ({"relevance": 5, "significance": 2, "novelty": 5}, "REJECTED"),
    ({"relevance": 5, "significance": 5, "novelty": 1}, "REJECTED"),
])
def test_decide(s, expected):
    assert decide(s) == expected


def test_business_values_practice_not_novelty():
    s = {"relevance": 4, "significance": 3, "novelty": 2}
    assert decide(s, "business") == "SELECTED" and decide(s, "ai") == "REJECTED"


def test_parse_scores_rejects_bad():
    ok = parse_scores('{"significance":4,"novelty":3,"relevance":5,"complexity":2,"why":" да "}')
    assert ok["why"] == "да"
    for bad in ('{"significance":9,"novelty":3,"relevance":5,"complexity":2,"why":""}', "не json", '{"novelty":3}'):
        with pytest.raises((ValueError, KeyError)):
            parse_scores(bad)


class Ctx:
    model = "fake"

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, messages, num_predict=400, fmt=None, temperature=None):
        self.calls.append((messages, fmt))
        return self.answers.pop(0)


def test_triage_job_scores_decides_and_handles_garbage(stores):
    items, tasks = stores
    add(items, "Нейросеть написала роман целиком сама", "Языковые модели научились считать")
    run_matching(items, [T_AI], [Source("s", "S", "rss")])
    ids = [c["id"] for c in items.top_matched()]
    job = TriageJob(items, [T_AI], [Source("s", "S", "rss")])
    good = json.dumps({"significance": 4, "novelty": 4, "relevance": 5, "complexity": 2, "why": "важно"})
    ctx = Ctx([good, "мусор вместо json"])
    cp, done = job.step(ctx, {"item_ids": ids}, {})
    assert not done and cp["done"] == [ids[0]]
    assert ctx.calls[0][1]["required"]                                 # модели передана схема ответа
    cp, done = job.step(ctx, {"item_ids": ids}, cp)
    assert done and cp["failed"] == [ids[1]]
    assert items.item(ids[0])["state"] == "SELECTED"
    assert items.item(ids[1])["state"] == "TRIAGE_FAILED"


def test_planner_only_when_needed(stores):
    items, tasks = stores
    assert plan(tasks, items) is None                                  # нечего изучать — задач нет
    add(items, "Нейросеть написала роман целиком сама")
    run_matching(items, [T_AI], [Source("s", "S", "rss")])
    tid = plan(tasks, items)
    assert tid and tasks.get(tid).kind == "triage"
    assert plan(tasks, items) is None                                  # одна задача оценки за раз
