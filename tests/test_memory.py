import json
import sqlite3

import pytest

from nexus.jobs import MemoryJob
from nexus.memory.consolidate import MERGE, NEW, RELATE, best_match, decide, merge_messages
from nexus.memory.embeddings import cosine, dumps, loads
from nexus.memory.search import search
from nexus.memory.store import MemoryStore
from nexus.research.match import Topic
from nexus.research.planner import plan_memory
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore
from nexus.tasks import TaskStore

T_AI = Topic("ai", "ИИ", 1, ["нейросет"])


def test_cosine_and_serialize_roundtrip():
    a, b = [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]
    assert cosine(a, b) == pytest.approx(1.0)
    assert cosine(a, [0.0, 1.0, 0.0]) == pytest.approx(0.0)
    assert cosine(a, []) == 0.0
    assert loads(dumps([0.1, 0.2, 0.3])) == [0.1, 0.2, 0.3]
    assert loads("") == []


@pytest.mark.parametrize("sim,expected", [(0.9, MERGE), (0.8, RELATE), (0.5, NEW)])
def test_decide_thresholds(sim, expected):
    base = [1.0, 0.0]
    import math
    angle = math.acos(min(1.0, sim))
    other = [math.cos(angle), math.sin(angle)]
    action, mid, got_sim = decide(base, [(7, other)])
    assert action == expected and got_sim == pytest.approx(sim, abs=1e-6)
    assert (mid == 7) == (action != NEW)


def test_decide_with_no_candidates_is_new():
    assert decide([1.0, 0.0], []) == (NEW, None, 0.0)


def test_best_match_picks_highest():
    assert best_match([1.0, 0.0], [(1, [0.0, 1.0]), (2, [1.0, 0.0]), (3, [0.7, 0.7])])[0] == 2


def test_merge_messages_include_old_and_new():
    msgs = merge_messages("Тема", "старый вывод", "новый текст")
    assert "старый вывод" in msgs[1]["content"] and "новый текст" in msgs[1]["content"]
    assert "ничего не добавляй" in msgs[0]["content"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    s = MemoryStore(tmp_path / "m.db")
    yield s
    s.close()


def test_create_and_get(store):
    mid = store.create("ai", "Заголовок", "суть", "выводы", "отчёт", "ЧАСТИЧНО", False, [1.0, 0.0], item_id=1)
    t = store.get(mid)
    assert t.title == "Заголовок" and t.links == [1] and t.credibility_status == "ЧАСТИЧНО"
    assert not t.deleted and t.created == t.updated


def test_update_keeps_history_and_merges_links(store):
    mid = store.create("ai", "Т", "с1", "в1", "о1", None, False, [1.0, 0.0], item_id=1)
    store.update(mid, "с1", "в2 объединённые", "о1\nо2", "ПОДТВЕРЖДЕНО", False, [1.0, 0.1], item_id=2,
                reason="новое сведение")
    t = store.get(mid)
    assert t.conclusions == "в2 объединённые" and t.credibility_status == "ПОДТВЕРЖДЕНО"
    assert set(t.links) == {1, 2}
    hist = store.history(mid)
    assert len(hist) == 1 and hist[0][2] == "в1" and hist[0][3] == "новое сведение"


def test_update_unknown_id_raises(store):
    with pytest.raises(KeyError):
        store.update(999, "a", "b", "c", None, False, [], item_id=1, reason="x")


def test_related_links_are_bidirectional(store):
    a = store.create("ai", "A", "", "", "", None, False, [1.0, 0.0], item_id=1)
    b = store.create("ai", "B", "", "", "", None, False, [1.0, 0.0], item_id=2)
    store.link_related(a, b)
    assert store.get(a).related == [b] and store.get(b).related == [a]


def test_soft_delete_excludes_from_listing_but_keeps_data(store):
    mid = store.create("ai", "Т", "", "", "", None, False, [1.0], item_id=1)
    store.soft_delete(mid)
    assert mid not in {t.id for t in store.all()}
    assert mid in {t.id for t in store.all(include_deleted=True)}
    assert store.get(mid).title == "Т"                          # данные не стёрты


def test_search_text_requires_all_words(store):
    store.create("ai", "Квантовые компьютеры бьют рекорды", "", "суперпозиция и запутанность", "", None, False,
                [], item_id=1)
    assert len(store.search_text("квантовые рекорды")) == 1
    assert len(store.search_text("квантовые динозавры")) == 0


def test_item_memory_id(store):
    mid = store.create("ai", "Т", "", "", "", None, False, [1.0], item_id=42)
    assert store.item_memory_id(42) == mid
    assert store.item_memory_id(43) is None


def test_search_combines_semantic_and_words_and_flags_ambiguous(store):
    store.create("ai", "Роботы Boston Dynamics учатся ходить", "", "", "", None, False, [1.0, 0.0], item_id=1)
    store.create("ai", "Квантовые компьютеры и суперпозиция", "", "", "", None, False, [0.99, 0.01], item_id=2)
    out = search(store, "роботы", [1.0, 0.0], limit=5)
    assert out.results[0].topic.title.startswith("Роботы")
    assert out.ambiguous and "или" in out.question                 # близкие по смыслу, но разные темы


def test_search_without_embedding_falls_back_to_words(store):
    store.create("ai", "Нейросеть обыграла чемпиона", "", "", "", None, False, [], item_id=1)
    out = search(store, "нейросеть чемпиона", None, limit=5)
    assert len(out.results) == 1 and out.results[0].via == "слова"


# ---------- MemoryJob ----------

class Ctx:
    model = "fake"

    def __init__(self, embedding, chat_answer="обновлённые выводы"):
        self.embedding = embedding
        self.chat_answer = chat_answer
        self.chat_calls = 0

    def embed(self, text):
        return self.embedding

    def chat(self, messages, num_predict=400, fmt=None, temperature=None):
        self.chat_calls += 1
        return self.chat_answer


@pytest.fixture
def item_stores(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    items, memory, tasks = ItemStore(tmp_path / "n.db"), MemoryStore(tmp_path / "n.db"), TaskStore(tmp_path / "n.db")
    yield items, memory, tasks
    items.close(); memory.close(); tasks.close()


def digested(items, title, source="s", topic_id="ai", status="ЧАСТИЧНО", low=False):
    items.add_entries(source, [Entry(title, f"https://{source}/{abs(hash(title + source))}")])
    iid = items.items_in_state("NEW")[-1]["id"]
    items.save_report(iid, topic_id, f"текст про {title}", "fake", "DIGESTED")
    items.save_credibility(topic_id, status, "причина", low, [iid])
    return iid


def test_memory_job_creates_new_topic(item_stores):
    items, memory, _ = item_stores
    iid = digested(items, "Boston Dynamics показал нового робота")
    job = MemoryJob(items, memory, [T_AI])
    ctx = Ctx(embedding=[1.0, 0.0])
    cp, done = job.step(ctx, {"item_ids": [iid]}, {})
    assert done and cp["done"] == [iid]
    assert memory.item_memory_id(iid) is not None
    t = memory.get(memory.item_memory_id(iid))
    assert t.credibility_status == "ЧАСТИЧНО" and ctx.chat_calls == 0        # новой теме merge не нужен


def test_memory_job_merges_similar_into_existing(item_stores):
    items, memory, _ = item_stores
    first = digested(items, "Boston Dynamics показал нового робота")
    job = MemoryJob(items, memory, [T_AI])
    job.step(Ctx(embedding=[1.0, 0.0]), {"item_ids": [first]}, {})
    mid_before = memory.item_memory_id(first)

    second = digested(items, "Новый робот Boston Dynamics, подробности", status="ПОДТВЕРЖДЕНО")
    ctx = Ctx(embedding=[0.99, 0.01], chat_answer="итоговые выводы")
    job.step(ctx, {"item_ids": [second]}, {})
    assert ctx.chat_calls == 1                                              # для объединения модель вызвана
    mid_after = memory.item_memory_id(second)
    assert mid_after == mid_before
    t = memory.get(mid_before)
    assert t.conclusions == "итоговые выводы" and set(t.links) == {first, second}
    assert t.credibility_status == "ПОДТВЕРЖДЕНО"
    assert len(memory.history(mid_before)) == 1


def test_memory_job_relates_but_does_not_merge(item_stores):
    items, memory, _ = item_stores
    first = digested(items, "Тема А")
    job = MemoryJob(items, memory, [T_AI])
    job.step(Ctx(embedding=[1.0, 0.0]), {"item_ids": [first]}, {})
    mid_a = memory.item_memory_id(first)

    second = digested(items, "Тема Б")
    import math
    angle = math.acos(0.8)
    ctx = Ctx(embedding=[math.cos(angle), math.sin(angle)])
    job.step(ctx, {"item_ids": [second]}, {})
    mid_b = memory.item_memory_id(second)
    assert mid_b != mid_a and ctx.chat_calls == 0
    assert mid_a in memory.get(mid_b).related


def test_memory_job_skips_unknown_topic_but_advances(item_stores):
    items, memory, _ = item_stores
    items.add_entries("s", [Entry("Что-то без темы в выжимке", "https://s/x")])
    iid = items.items_in_state("NEW")[-1]["id"]
    items.save_report(iid, "no-such-topic", "текст", "fake", "DIGESTED")
    items.save_credibility("no-such-topic", "ЧАСТИЧНО", "x", False, [iid])
    job = MemoryJob(items, memory, [T_AI])
    cp, done = job.step(Ctx(embedding=[1.0]), {"item_ids": [iid]}, {})
    assert done
    t = memory.get(memory.item_memory_id(iid))
    assert t.interest_topic_id == "no-such-topic"                            # тему не потеряли, просто её нет в списке интересов сейчас


def test_plan_memory_waits_for_credibility_and_skips_already_remembered(item_stores):
    items, memory, tasks = item_stores
    items.add_entries("s", [Entry("Материал без оценки достоверности пока", "https://s/1")])
    iid = items.items_in_state("NEW")[-1]["id"]
    items.save_report(iid, "ai", "текст", "fake", "DIGESTED")
    assert plan_memory(tasks, items, memory) is None                        # достоверность ещё не посчитана

    items.save_credibility("ai", "ЧАСТИЧНО", "x", False, [iid])
    tid = plan_memory(tasks, items, memory)
    assert tid and tasks.get(tid).payload["item_ids"] == [iid]
    assert plan_memory(tasks, items, memory) is None                        # задача уже в работе


def test_plan_memory_skips_items_already_in_memory(item_stores):
    items, memory, tasks = item_stores
    iid = digested(items, "Уже в памяти")
    memory.create("ai", "Т", "", "", "", "ЧАСТИЧНО", False, [1.0], item_id=iid)
    assert plan_memory(tasks, items, memory) is None
