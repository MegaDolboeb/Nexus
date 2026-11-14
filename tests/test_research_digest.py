import pytest

from nexus.jobs import DigestJob
from nexus.research.digest import digest_messages
from nexus.research.fetch_article import FetchError, fetch_article_text
from nexus.research.match import Topic
from nexus.research.planner import plan_digest
from nexus.research.select import run_matching
from nexus.sources.collector import Source
from nexus.sources.feeds import Entry
from nexus.sources.store import ItemStore
from nexus.tasks import TaskStore

T_AI = Topic("ai", "ИИ", 1, ["нейросет"], "про ИИ", how_to_present="Пиши коротко, без воды.")


class FakeHTTP:
    """Подменяет urllib.request.urlopen в fetch_article."""

    def __init__(self, body=("<html><body><nav>Меню Меню Меню</nav><script>x()</script>"
                             "<p>" + "Текст статьи про нейросети. " * 30 + "</p></body></html>").encode("utf-8"),
                 content_type="text/html; charset=utf-8"):
        self.body, self.content_type = body, content_type

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=None):
        return self.body

    @property
    def headers(self):
        return {"Content-Type": self.content_type}


def test_fetch_article_strips_nav_and_scripts(monkeypatch):
    import nexus.research.fetch_article as fa
    monkeypatch.setattr(fa.urllib.request, "urlopen", lambda req, timeout=20: FakeHTTP())
    text = fetch_article_text("https://x/1")
    assert "Меню" not in text and "x()" not in text and "Текст статьи" in text


def test_fetch_article_rejects_non_html(monkeypatch):
    import nexus.research.fetch_article as fa
    monkeypatch.setattr(fa.urllib.request, "urlopen",
                        lambda req, timeout=20: FakeHTTP(b"\x89PNG...", "image/png"))
    with pytest.raises(FetchError):
        fetch_article_text("https://x/1")


def test_fetch_article_rejects_too_short(monkeypatch):
    import nexus.research.fetch_article as fa
    monkeypatch.setattr(fa.urllib.request, "urlopen", lambda req, timeout=20: FakeHTTP(b"<html><body>hi</body></html>"))
    with pytest.raises(FetchError, match="JavaScript"):
        fetch_article_text("https://x/1")


def test_fetch_article_rejects_bot_check_page(monkeypatch):
    import nexus.research.fetch_article as fa
    page = ("<html><body><p>" + "Client Challenge A required part of this site couldn't load. " * 10
            + "</p></body></html>")
    monkeypatch.setattr(fa.urllib.request, "urlopen", lambda req, timeout=20: FakeHTTP(page.encode("utf-8")))
    with pytest.raises(FetchError, match="проверки на робота"):
        fetch_article_text("https://x/1")


def test_digest_prompt_includes_how_to_present_and_forbids_invention():
    msgs = digest_messages(T_AI, "Habr", "Заголовок", "Текст статьи")
    sys_text = msgs[0]["content"]
    user_text = msgs[1]["content"]
    assert "не придумывай" in sys_text or "ничего не добавляй" in sys_text
    assert "Пиши коротко, без воды." in user_text and "Текст статьи" in user_text


@pytest.fixture
def stores(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    items, tasks = ItemStore(tmp_path / "n.db"), TaskStore(tmp_path / "n.db")
    yield items, tasks
    items.close()
    tasks.close()


def make_selected(items, title="Нейросеть написала роман целиком сама"):
    items.add_entries("s", [Entry(title, "https://x/1")])
    run_matching(items, [T_AI], [Source("s", "S", "rss")])
    item_id = items.top_matched()[0]["id"]
    items.save_score(item_id, "ai", {"significance": 4, "novelty": 4, "relevance": 5, "complexity": 2, "why": "важно"},
                     "fake", "SELECTED")
    return item_id


class Ctx:
    model = "fake"
    settings = type("S", (), {"research_mode": "balanced", "custom_instruction": ""})()

    def __init__(self, answer="Суть. Факты."):
        self.answer = answer
        self.calls = []

    def chat(self, messages, num_predict=400, fmt=None, temperature=None):
        self.calls.append(messages)
        return self.answer


def test_digest_job_saves_report(stores):
    items, _ = stores
    item_id = make_selected(items)
    job = DigestJob(items, [T_AI], [Source("s", "S", "rss")], fetch_text=lambda url: "Полный текст статьи про нейросети.")
    ctx = Ctx("Суть: нейросеть написала роман. Факты: 1. ...")
    cp, done = job.step(ctx, {"item_ids": [item_id], "topics": {str(item_id): "ai"}}, {})
    assert done and cp["done"] == [item_id]
    assert items.item(item_id)["state"] == "DIGESTED"
    r = items.report(item_id)
    assert r["text"] == ctx.answer and r["topic_id"] == "ai"


def test_digest_job_fetch_failure_is_skipped_not_invented(stores):
    items, _ = stores
    item_id = make_selected(items)

    def boom(url):
        raise FetchError("сайт недоступен")
    job = DigestJob(items, [T_AI], [Source("s", "S", "rss")], fetch_text=boom)
    ctx = Ctx()
    cp, done = job.step(ctx, {"item_ids": [item_id], "topics": {str(item_id): "ai"}}, {})
    assert done and cp["failed"] == [item_id]
    assert items.item(item_id)["state"] == "FETCH_FAILED"
    assert items.report(item_id) is None
    assert ctx.calls == []                                     # модель не звали — нечего пересказывать


def test_digest_job_unknown_topic_skips(stores):
    items, _ = stores
    item_id = make_selected(items)
    job = DigestJob(items, [T_AI], [Source("s", "S", "rss")], fetch_text=lambda u: "текст")
    cp, done = job.step(Ctx(), {"item_ids": [item_id], "topics": {}}, {})
    assert done and items.item(item_id)["state"] == "SKIPPED"


def test_planner_digest_only_for_selected_without_report(stores):
    items, tasks = stores
    assert plan_digest(tasks, items) is None
    item_id = make_selected(items)
    tid = plan_digest(tasks, items)
    assert tid and tasks.get(tid).kind == "digest"
    assert tasks.get(tid).payload["topics"][str(item_id)] == "ai"
    assert plan_digest(tasks, items) is None                   # задача уже в работе
