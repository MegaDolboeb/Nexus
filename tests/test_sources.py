import urllib.error

import pytest

from nexus.sources import feeds
from nexus.sources.collector import Collector, Source, load_sources
from nexus.sources.feeds import Entry, html_to_text, parse_date, parse_feed
from nexus.sources.store import ItemStore, normalize_url, title_fingerprint

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>T</title>
<item><title>Робот сделал сальто без гидравлики впервые</title><link>https://example.ru/a?utm_source=rss</link>
<description>&lt;p&gt;Китайский &lt;b&gt;робот&lt;/b&gt; сделал&lt;/p&gt;</description>
<pubDate>Thu, 13 Nov 2026 10:00:00 +0300</pubDate><guid>a1</guid><dc:creator>Иван</dc:creator></item>
<item><title>Без ссылки</title></item>
</channel></rss>""".encode("utf-8")

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2611.00001v2</id><title>A New  Model
 of Things</title><summary>We show <i>things</i>.</summary><published>2026-11-12T18:00:00Z</published>
<link href="http://arxiv.org/abs/2611.00001v2" rel="alternate" type="text/html"/>
<link title="pdf" href="http://arxiv.org/pdf/2611.00001v2" rel="related" type="application/pdf"/>
<author><name>A. Author</name></author><author><name>B. Author</name></author></entry></feed>"""

RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<item rdf:about="https://n.com/1"><title>Nature thing happened in the lab today</title><link>https://n.com/1</link>
<description>d</description><dc:date>2026-11-12</dc:date></item></rdf:RDF>"""


def test_parse_rss():
    es = parse_feed(RSS)
    assert len(es) == 1
    e = es[0]
    assert e.summary == "Китайский робот сделал" and e.authors == ["Иван"] and e.published


def test_parse_atom_arxiv():
    e = parse_feed(ATOM)[0]
    assert e.title == "A New Model of Things"
    assert e.url == "http://arxiv.org/abs/2611.00001v2"
    assert e.summary == "We show things." and e.authors == ["A. Author", "B. Author"]


def test_parse_rdf():
    e = parse_feed(RDF)[0]
    assert e.url == "https://n.com/1" and e.published


def test_not_a_feed():
    with pytest.raises(ValueError, match="проверка на робота"):
        parse_feed(b"<!DOCTYPE html><html><body>bot check</body></html>")
    with pytest.raises(ValueError):
        parse_feed(b"<svg></svg>")


def test_rdf_description_fallback():
    data = RDF.replace(b"<description>d</description>",
                       b"<dc:description>from dc</dc:description>")
    assert parse_feed(data)[0].summary == "from dc"


def test_dates():
    assert parse_date("Thu, 13 Nov 2026 07:00:00 GMT") == parse_date("2026-11-13T07:00:00Z")
    assert parse_date("вчера") is None


def test_html_to_text_drops_scripts():
    assert html_to_text("<p>a</p><script>x()</script><p>b &amp; c</p>") == "a b & c"


@pytest.mark.parametrize("a,b", [
    ("https://www.example.ru/a/?utm_source=x&id=5#top", "https://example.ru/a?id=5"),
    ("http://arxiv.org/abs/2611.00001v3", "https://arxiv.org/abs/2611.00001"),
    ("https://arxiv.org/pdf/2611.00001v1.pdf", "https://arxiv.org/abs/2611.00001"),
])
def test_normalize_url(a, b):
    assert normalize_url(a) == b


def test_short_titles_have_no_fingerprint():
    assert title_fingerprint("Новости недели") is None
    assert title_fingerprint("Робот сделал сальто!") is None
    assert title_fingerprint("Робот сделал сальто без гидравлики") == title_fingerprint("робот сделал сальто, без гидравлики")


@pytest.fixture
def store(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    s = ItemStore(tmp_path / "i.db")
    yield s
    s.close()


def test_dedup_by_url_and_title(store):
    e1 = Entry("Робот сделал сальто без гидравлики впервые", "https://a.ru/1?utm_source=x")
    e2 = Entry("Другое название совсем другой новости", "https://a.ru/1")                 # та же ссылка
    e3 = Entry("Робот сделал сальто без гидравлики впервые", "https://b.ru/copy")          # тот же заголовок
    e4 = Entry("Новости недели", "https://a.ru/2")
    e5 = Entry("Новости недели", "https://a.ru/3")                                           # короткий: не повтор
    assert store.add_entries("s", [e1, e2, e3, e4, e5]) == 3
    assert store.add_entries("s", [e1]) == 0                                                 # повторный проход


def test_arxiv_new_version_is_not_new(store):
    assert store.add_entries("arxiv", [Entry("A very long arxiv paper title here", "http://arxiv.org/abs/2611.1v1")]) == 1
    assert store.add_entries("arxiv", [Entry("A very long arxiv paper title, v2!", "http://arxiv.org/abs/2611.1v2")]) == 0


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def make(store, fetch, clock=None):
    srcs = [Source("good", "G", "rss", url="https://good/rss", every_min=60),
            Source("bad", "B", "rss", url="https://bad/rss", every_min=60)]
    return Collector(store, srcs, fetch=fetch, clock=clock or Clock(), sleep=lambda s: None)


def test_one_broken_source_does_not_stop_others(store):
    def fetch(url):
        if "bad" in url:
            raise urllib.error.URLError("нет сети")
        return RSS
    rep = make(store, fetch).run_due()
    assert rep["good"].startswith("ok") and "временно недоступен" in rep["bad"]
    assert store.count("good") == 1 and not store.status("bad").ok


def test_backoff_grows_and_resets(store):
    clock = Clock()
    state = {"fail": True}

    def fetch(url):
        if "bad" in url and state["fail"]:
            raise ValueError("сломанный XML")
        return RSS
    c = make(store, fetch, clock)
    c.run_due()
    first = store.status("bad").next_try - clock.t
    clock.t = store.status("bad").next_try
    c.run_due()
    second = store.status("bad").next_try - clock.t
    assert second == 2 * first and store.status("bad").fails == 2
    state["fail"] = False
    clock.t = store.status("bad").next_try
    c.run_due()
    st = store.status("bad")
    assert st.ok and st.fails == 0 and st.next_try - clock.t == 3600


def test_not_due_until_interval(store):
    clock = Clock()
    c = make(store, lambda url: RSS, clock)
    assert set(c.run_due()) == {"good", "bad"}
    clock.t += 59 * 60
    assert c.run_due() == {}
    clock.t += 60
    assert set(c.run_due()) == {"good", "bad"}


def test_priority_app_busy_stops_collection(store):
    calls = []
    c = make(store, lambda url: calls.append(url) or RSS)
    rep = c.run_due(may_work=lambda: False)
    assert calls == [] and "_stopped" in rep


def test_old_entries_skipped(store):
    clock = Clock()
    old = RSS.replace(b"Thu, 13 Nov 2026 10:00:00 +0300", b"Mon, 01 Jan 2024 10:00:00 +0000")
    c = Collector(store, [Source("s", "S", "rss", url="u", max_age_days=30)], fetch=lambda u: old,
                  clock=lambda: 1_794_550_000.0, sleep=lambda s: None)       # 13.11.2026
    assert "новых 0" in c.run_one(c.sources[0])


def test_example_sources_load():
    from nexus import config
    srcs = load_sources(config.ROOT / "config" / "sources.example.json")
    assert srcs and all(s.reliability in ("high", "medium", "low") for s in srcs)


def test_example_interests_load():
    """Свежая установка без personal/ — обязана быть, иначе первый же запуск падает."""
    from nexus import config
    from nexus.research.match import load_all_topics
    topics = load_all_topics(config.ROOT / "config" / "interests.example.json")
    assert topics and all(t.keywords for t in topics)


def test_arxiv_url_and_config_loads():
    s = Source("x", "X", "arxiv", categories=["cs.AI", "cs.RO"])
    assert "cat%3Acs.AI+OR+cat%3Acs.RO" in s.feed_url()
    srcs = load_sources()
    assert len({x.id for x in srcs}) == len(srcs) and all(x.reliability in ("high", "medium", "low") for x in srcs)
