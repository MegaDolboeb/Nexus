"""Хранилище памяти: темы с сутью, выводами, подробным отчётом, достоверностью, связями и историей
изменений. SQLite, тот же файл, что у остальных частей Nexus (data/nexus.db).

«Удаление» — мягкое (deleted=1): данные не стираются насовсем, пока Давид не попросит явно (раздел 8,
и общее правило 10: данные защищены от случайного удаления).
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..safety import writable
from .embeddings import dumps, loads


@dataclass
class MemoryTopic:
    id: int
    interest_topic_id: str
    title: str
    gist: str
    conclusions: str
    report: str
    credibility_status: str | None
    low_reliability: bool
    embedding: list[float]
    created: float
    updated: float
    deleted: bool
    links: list[int] = field(default_factory=list)       # id материалов (items), давших эту тему
    related: list[int] = field(default_factory=list)      # id связанных тем памяти


class MemoryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = writable(path or config.DATA_DIR / "nexus.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS memory_topics(
                    id INTEGER PRIMARY KEY, interest_topic_id TEXT NOT NULL, title TEXT NOT NULL,
                    gist TEXT NOT NULL DEFAULT '', conclusions TEXT NOT NULL DEFAULT '',
                    report TEXT NOT NULL DEFAULT '', credibility_status TEXT, low_reliability INTEGER NOT NULL DEFAULT 0,
                    embedding TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS memory_topics_interest ON memory_topics(interest_topic_id);
                CREATE TABLE IF NOT EXISTS memory_links(
                    item_id INTEGER NOT NULL, memory_id INTEGER NOT NULL, PRIMARY KEY(item_id, memory_id));
                CREATE TABLE IF NOT EXISTS memory_related(
                    memory_id INTEGER NOT NULL, related_id INTEGER NOT NULL, PRIMARY KEY(memory_id, related_id));
                CREATE TABLE IF NOT EXISTS memory_history(
                    id INTEGER PRIMARY KEY, memory_id INTEGER NOT NULL, at REAL NOT NULL,
                    gist TEXT NOT NULL, conclusions TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '');
            """)

    def close(self):
        self._db.close()

    # ---------- создание и обновление (новые сведения обновляют тему, история сохраняется) ----------
    def create(self, interest_topic_id: str, title: str, gist: str, conclusions: str, report: str,
              credibility_status: str | None, low_reliability: bool, embedding: list[float],
              item_id: int) -> int:
        now = time.time()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO memory_topics(interest_topic_id,title,gist,conclusions,report,credibility_status,"
                "low_reliability,embedding,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (interest_topic_id, title, gist, conclusions, report, credibility_status, int(low_reliability),
                 dumps(embedding), now, now))
            mid = cur.lastrowid
            self._db.execute("INSERT OR IGNORE INTO memory_links(item_id,memory_id) VALUES(?,?)", (item_id, mid))
        return mid

    def update(self, memory_id: int, gist: str, conclusions: str, report: str, credibility_status: str | None,
              low_reliability: bool, embedding: list[float], item_id: int, reason: str) -> None:
        """Записывает прошлую версию в историю, затем заменяет текущую. Данные не теряются."""
        now = time.time()
        with self._lock, self._db:
            old = self._db.execute("SELECT gist, conclusions FROM memory_topics WHERE id=?", (memory_id,)).fetchone()
            if old is None:
                raise KeyError(memory_id)
            self._db.execute("INSERT INTO memory_history(memory_id,at,gist,conclusions,reason) VALUES(?,?,?,?,?)",
                             (memory_id, now, old[0], old[1], reason))
            self._db.execute(
                "UPDATE memory_topics SET gist=?, conclusions=?, report=?, credibility_status=?, low_reliability=?,"
                " embedding=?, updated=? WHERE id=?",
                (gist, conclusions, report, credibility_status, int(low_reliability), dumps(embedding), now,
                 memory_id))
            self._db.execute("INSERT OR IGNORE INTO memory_links(item_id,memory_id) VALUES(?,?)", (item_id, memory_id))

    def link_related(self, a_id: int, b_id: int) -> None:
        if a_id == b_id:
            return
        with self._lock, self._db:
            self._db.execute("INSERT OR IGNORE INTO memory_related(memory_id,related_id) VALUES(?,?)", (a_id, b_id))
            self._db.execute("INSERT OR IGNORE INTO memory_related(memory_id,related_id) VALUES(?,?)", (b_id, a_id))

    def soft_delete(self, memory_id: int) -> None:
        """Только по явному решению Давида. Данные не стираются, просто перестают участвовать в поиске."""
        with self._lock, self._db:
            self._db.execute("UPDATE memory_topics SET deleted=1, updated=? WHERE id=?", (time.time(), memory_id))

    # ---------- чтение ----------
    def _row(self, r) -> MemoryTopic:
        mid = r[0]
        with self._lock:
            links = [x[0] for x in self._db.execute("SELECT item_id FROM memory_links WHERE memory_id=?", (mid,))]
            related = [x[0] for x in self._db.execute(
                "SELECT related_id FROM memory_related WHERE memory_id=?", (mid,))]
        return MemoryTopic(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7]), loads(r[8]), r[9], r[10],
                          bool(r[11]), links, related)

    def get(self, memory_id: int) -> MemoryTopic:
        with self._lock:
            r = self._db.execute("SELECT * FROM memory_topics WHERE id=?", (memory_id,)).fetchone()
        if r is None:
            raise KeyError(memory_id)
        return self._row(r)

    def all_for_interest(self, interest_topic_id: str, include_deleted: bool = False) -> list[MemoryTopic]:
        q = "SELECT * FROM memory_topics WHERE interest_topic_id=?"
        if not include_deleted:
            q += " AND deleted=0"
        with self._lock:
            rows = self._db.execute(q, (interest_topic_id,)).fetchall()
        return [self._row(r) for r in rows]

    def all(self, include_deleted: bool = False, limit: int = 1000) -> list[MemoryTopic]:
        q = "SELECT * FROM memory_topics"
        if not include_deleted:
            q += " WHERE deleted=0"
        q += " ORDER BY updated DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def history(self, memory_id: int) -> list[tuple[float, str, str, str]]:
        with self._lock:
            return list(self._db.execute(
                "SELECT at, gist, conclusions, reason FROM memory_history WHERE memory_id=? ORDER BY id", (memory_id,)))

    def item_memory_id(self, item_id: int) -> int | None:
        with self._lock:
            r = self._db.execute("SELECT memory_id FROM memory_links WHERE item_id=?", (item_id,)).fetchone()
        return r[0] if r else None

    def search_text(self, query: str, limit: int = 20) -> list[MemoryTopic]:
        """Обычный поиск по словам (без смысла): все слова запроса должны встретиться хоть где-то.
        Регистр сравнивается в Python: у SQLite встроенный lower()/LIKE опускает регистр только
        у латиницы, а не у кириллицы."""
        words = [w for w in query.lower().split() if w]
        if not words:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM memory_topics WHERE deleted=0 ORDER BY updated DESC").fetchall()
        out = []
        for r in rows:
            haystack = f"{r[2]} {r[3]} {r[4]}".lower()               # title, gist, conclusions
            if all(w in haystack for w in words):
                out.append(self._row(r))
                if len(out) >= limit:
                    break
        return out
