"""Найденные материалы и состояние источников (SQLite). Без повторов: по нормализованной ссылке и по отпечатку заголовка."""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .. import config
from ..safety import writable
from .feeds import Entry

DROP_PARAMS = re.compile(r"^(utm_.*|fbclid|gclid|yclid|ref|ref_src|from|_openstat|mc_cid|mc_eid)$", re.I)
ARXIV_VERSION = re.compile(r"(arxiv\.org/(?:abs|pdf)/[\w.\-/]+?)v\d+(\.pdf)?$", re.I)
MIN_TITLE_FOR_FP = 25                    # короткие заголовки («Новости недели») по отпечатку не сравниваем


def normalize_url(url: str) -> str:
    u = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)
                                    if not DROP_PARAMS.match(k)])
    host = u.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = u.path.rstrip("/") or "/"
    norm = urllib.parse.urlunsplit(("https" if u.scheme in ("http", "https") else u.scheme, host, path, query, ""))
    m = ARXIV_VERSION.search(norm)
    if m:
        norm = norm[:m.start()] + m.group(1).replace("/pdf/", "/abs/")
    return norm


def title_fingerprint(title: str) -> str | None:
    t = re.sub(r"[^\w]+", " ", title.lower()).strip()
    if len(t) < MIN_TITLE_FOR_FP:
        return None
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


@dataclass
class SourceStatus:
    source_id: str
    last_try: float
    last_ok: float
    ok: bool
    error: str
    fails: int
    next_try: float


class ItemStore:
    def __init__(self, path: str | Path | None = None):
        self.path = writable(path or config.DATA_DIR / "nexus.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS items(
                    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL, url_norm TEXT NOT NULL UNIQUE,
                    guid TEXT, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', authors TEXT NOT NULL DEFAULT '',
                    published REAL, fetched REAL NOT NULL, title_fp TEXT, state TEXT NOT NULL DEFAULT 'NEW');
                CREATE INDEX IF NOT EXISTS items_fp ON items(title_fp);
                CREATE INDEX IF NOT EXISTS items_state ON items(state);
                CREATE TABLE IF NOT EXISTS item_topics(
                    item_id INTEGER NOT NULL, topic_id TEXT NOT NULL, score REAL NOT NULL, hits TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(item_id, topic_id));
                CREATE INDEX IF NOT EXISTS item_topics_score ON item_topics(score);
                CREATE TABLE IF NOT EXISTS item_scores(
                    item_id INTEGER PRIMARY KEY, topic_id TEXT NOT NULL, significance INTEGER, novelty INTEGER,
                    relevance INTEGER, complexity INTEGER, why TEXT NOT NULL DEFAULT '', model TEXT, at REAL);
                CREATE TABLE IF NOT EXISTS reports(
                    item_id INTEGER PRIMARY KEY, topic_id TEXT NOT NULL, text TEXT NOT NULL,
                    model TEXT, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS credibility(
                    id INTEGER PRIMARY KEY, topic_id TEXT NOT NULL, status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '', low_reliability INTEGER NOT NULL DEFAULT 0,
                    model TEXT, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS item_credibility(
                    item_id INTEGER PRIMARY KEY, credibility_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS source_status(
                    source_id TEXT PRIMARY KEY, last_try REAL NOT NULL DEFAULT 0, last_ok REAL NOT NULL DEFAULT 0,
                    ok INTEGER NOT NULL DEFAULT 1, error TEXT NOT NULL DEFAULT '', fails INTEGER NOT NULL DEFAULT 0,
                    next_try REAL NOT NULL DEFAULT 0);
            """)

    def close(self):
        self._db.close()

    def add_entries(self, source_id: str, entries: list[Entry], now: float | None = None) -> int:
        """Добавить новые; повторы пропустить. Возвращает число новых."""
        now = now or time.time()
        added = 0
        with self._lock, self._db:
            for e in entries:
                norm = normalize_url(e.url)
                fp = title_fingerprint(e.title)
                if self._db.execute("SELECT 1 FROM items WHERE url_norm=?", (norm,)).fetchone():
                    continue
                if fp and self._db.execute("SELECT 1 FROM items WHERE title_fp=?", (fp,)).fetchone():
                    continue
                self._db.execute(
                    "INSERT INTO items(source_id,url,url_norm,guid,title,summary,authors,published,fetched,title_fp)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (source_id, e.url, norm, e.guid, e.title, e.summary[:4000], ", ".join(e.authors)[:500],
                     e.published, now, fp))
                added += 1
        return added

    def count(self, source_id: str | None = None) -> int:
        with self._lock:
            if source_id:
                return self._db.execute("SELECT COUNT(*) FROM items WHERE source_id=?", (source_id,)).fetchone()[0]
            return self._db.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    def latest(self, limit: int = 10) -> list[tuple]:
        with self._lock:
            return list(self._db.execute(
                "SELECT source_id, title, url, published FROM items ORDER BY COALESCE(published, fetched) DESC LIMIT ?",
                (limit,)))

    # ---------- отбор по темам (Этап 4) ----------
    def items_in_state(self, state: str, limit: int = 100000) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, source_id, url, title, summary, published, fetched FROM items WHERE state=? "
                "ORDER BY id LIMIT ?", (state, limit)).fetchall()
        return [dict(zip(("id", "source_id", "url", "title", "summary", "published", "fetched"), r)) for r in rows]

    def item(self, item_id: int) -> dict:
        with self._lock:
            r = self._db.execute("SELECT id, source_id, url, title, summary, published, fetched, state FROM items "
                                 "WHERE id=?", (item_id,)).fetchone()
        if r is None:
            raise KeyError(item_id)
        return dict(zip(("id", "source_id", "url", "title", "summary", "published", "fetched", "state"), r))

    def set_matches(self, item_id: int, matches: list, state: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM item_topics WHERE item_id=?", (item_id,))
            for m in matches:
                self._db.execute("INSERT INTO item_topics(item_id,topic_id,score,hits) VALUES(?,?,?,?)",
                                 (item_id, m.topic_id, m.score, ", ".join(m.hits)))
            self._db.execute("UPDATE items SET state=? WHERE id=?", (state, item_id))

    def set_state(self, item_id: int, state: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE items SET state=? WHERE id=?", (state, item_id))

    def top_matched(self, limit: int = 20, state: str = "MATCHED") -> list[dict]:
        """Лучшие кандидаты: по лучшему счёту темы."""
        with self._lock:
            rows = self._db.execute(
                "SELECT i.id, i.source_id, i.title, i.url, MAX(t.score) AS s, "
                "(SELECT topic_id FROM item_topics WHERE item_id=i.id ORDER BY score DESC LIMIT 1) "
                "FROM items i JOIN item_topics t ON t.item_id=i.id WHERE i.state=? "
                "GROUP BY i.id ORDER BY s DESC LIMIT ?", (state, limit)).fetchall()
        return [dict(zip(("id", "source_id", "title", "url", "score", "topic_id"), r)) for r in rows]

    def topics_of(self, item_id: int) -> list[tuple[str, float, str]]:
        with self._lock:
            return list(self._db.execute("SELECT topic_id, score, hits FROM item_topics WHERE item_id=? "
                                         "ORDER BY score DESC", (item_id,)))

    def save_score(self, item_id: int, topic_id: str, s: dict, model: str, state: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO item_scores(item_id,topic_id,significance,novelty,relevance,complexity,why,model,at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (item_id, topic_id, s.get("significance"), s.get("novelty"), s.get("relevance"), s.get("complexity"),
                 str(s.get("why", ""))[:500], model, time.time()))
            self._db.execute("UPDATE items SET state=? WHERE id=?", (state, item_id))

    def score_topic(self, item_id: int) -> str | None:
        with self._lock:
            r = self._db.execute("SELECT topic_id FROM item_scores WHERE item_id=?", (item_id,)).fetchone()
        return r[0] if r else None

    def scored(self, state: str | None = None, limit: int = 50) -> list[dict]:
        q = ("SELECT i.id, i.source_id, i.title, i.url, i.state, s.topic_id, s.significance, s.novelty, s.relevance, "
             "s.complexity, s.why FROM items i JOIN item_scores s ON s.item_id=i.id")
        args: tuple = ()
        if state:
            q += " WHERE i.state=?"
            args = (state,)
        q += " ORDER BY s.relevance*s.significance*s.novelty DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, args + (limit,)).fetchall()
        keys = ("id", "source_id", "title", "url", "state", "topic_id", "significance", "novelty", "relevance",
                "complexity", "why")
        return [dict(zip(keys, r)) for r in rows]

    def save_report(self, item_id: int, topic_id: str, text: str, model: str, state: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO reports(item_id,topic_id,text,model,at) VALUES(?,?,?,?,?)",
                             (item_id, topic_id, text, model, time.time()))
            self._db.execute("UPDATE items SET state=? WHERE id=?", (state, item_id))

    def report(self, item_id: int) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT item_id, topic_id, text, model, at FROM reports WHERE item_id=?",
                                 (item_id,)).fetchone()
        return dict(zip(("item_id", "topic_id", "text", "model", "at"), r)) if r else None

    def reports(self, topic_id: str | None = None, limit: int = 50,
               since: float | None = None, until: float | None = None) -> list[dict]:
        q = ("SELECT r.item_id, i.source_id, i.title, i.url, r.topic_id, r.text, r.at FROM reports r "
             "JOIN items i ON i.id=r.item_id")
        where, args = [], []
        if topic_id:
            where.append("r.topic_id=?")
            args.append(topic_id)
        if since is not None:
            where.append("r.at>=?")
            args.append(since)
        if until is not None:
            where.append("r.at<?")
            args.append(until)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY r.at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(q, tuple(args)).fetchall()
        keys = ("item_id", "source_id", "title", "url", "topic_id", "text", "at")
        return [dict(zip(keys, r)) for r in rows]

    # ---------- достоверность (Этап 4, раздел 7.1) ----------
    def digested_items_for_credibility(self) -> list[dict]:
        """Все выжимки: материал + тема, по которой его отобрали, + текст выжимки."""
        with self._lock:
            rows = self._db.execute(
                "SELECT i.id, i.source_id, i.title, i.published, i.fetched, r.topic_id, r.text "
                "FROM items i JOIN reports r ON r.item_id = i.id WHERE i.state='DIGESTED'").fetchall()
        return [dict(zip(("id", "source_id", "title", "published", "fetched", "topic_id", "text"), r))
                for r in rows]

    def save_credibility(self, topic_id: str, status: str, reason: str, low_reliability: bool,
                         item_ids: list[int], model: str | None = None) -> int:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO credibility(topic_id,status,reason,low_reliability,model,at) VALUES(?,?,?,?,?,?)",
                (topic_id, status, reason, int(low_reliability), model, time.time()))
            cred_id = cur.lastrowid
            if item_ids:
                marks = ",".join("?" * len(item_ids))
                self._db.execute(f"DELETE FROM item_credibility WHERE item_id IN ({marks})", item_ids)
                self._db.executemany("INSERT INTO item_credibility(item_id,credibility_id) VALUES(?,?)",
                                     [(i, cred_id) for i in item_ids])
        return cred_id

    def credibility_items(self, credibility_id: int) -> list[int]:
        with self._lock:
            return [r[0] for r in self._db.execute(
                "SELECT item_id FROM item_credibility WHERE credibility_id=?", (credibility_id,))]

    def credibility_of(self, item_id: int) -> dict | None:
        with self._lock:
            r = self._db.execute(
                "SELECT c.id, c.topic_id, c.status, c.reason, c.low_reliability, c.at FROM item_credibility ic "
                "JOIN credibility c ON c.id = ic.credibility_id WHERE ic.item_id=?", (item_id,)).fetchone()
        if r is None:
            return None
        return dict(zip(("id", "topic_id", "status", "reason", "low_reliability", "at"), r))

    def credibility_matches(self, item_ids: list[int]) -> bool:
        """True, если для этой же группы материалов достоверность уже посчитана (ничего не изменилось)."""
        target = set(item_ids)
        if not target:
            return True
        existing = self.credibility_of(next(iter(target)))
        if existing is None:
            return False
        return set(self.credibility_items(existing["id"])) == target

    def credibility_report(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, topic_id, status, reason, low_reliability, at FROM credibility "
                "ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(zip(("id", "topic_id", "status", "reason", "low_reliability", "at"), r))
            with self._lock:
                titles = self._db.execute(
                    "SELECT i.title, i.source_id FROM item_credibility ic JOIN items i ON i.id=ic.item_id "
                    "WHERE ic.credibility_id=?", (d["id"],)).fetchall()
            d["members"] = [{"title": t, "source_id": s} for t, s in titles]
            out.append(d)
        return out

    def counts_by_topic(self, states: tuple[str, ...] = ("SELECTED", "DIGESTED")) -> dict[str, int]:
        """Сколько материалов сейчас отобрано/в выжимке по каждой теме интересов (для панели)."""
        marks = ",".join("?" * len(states))
        with self._lock:
            rows = self._db.execute(
                f"SELECT t.topic_id, COUNT(DISTINCT t.item_id) FROM item_topics t JOIN items i ON i.id = t.item_id "
                f"WHERE i.state IN ({marks}) GROUP BY t.topic_id", states).fetchall()
        return dict(rows)

    def state_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._db.execute("SELECT state, COUNT(*) FROM items GROUP BY state"))

    # ---------- состояние источников ----------
    def status(self, source_id: str) -> SourceStatus:
        with self._lock:
            r = self._db.execute("SELECT * FROM source_status WHERE source_id=?", (source_id,)).fetchone()
        if r is None:
            return SourceStatus(source_id, 0, 0, True, "", 0, 0)
        return SourceStatus(r[0], r[1], r[2], bool(r[3]), r[4], r[5], r[6])

    def set_status(self, st: SourceStatus) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO source_status(source_id,last_try,last_ok,ok,error,fails,next_try) VALUES(?,?,?,?,?,?,?)"
                " ON CONFLICT(source_id) DO UPDATE SET last_try=excluded.last_try, last_ok=excluded.last_ok,"
                " ok=excluded.ok, error=excluded.error, fails=excluded.fails, next_try=excluded.next_try",
                (st.source_id, st.last_try, st.last_ok, int(st.ok), st.error, st.fails, st.next_try))
