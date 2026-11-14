"""Задачи Nexus в SQLite: состояние, причина, контрольная точка, история переходов."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .safety import writable

QUEUED, RUNNING, PAUSED, INTERRUPTED, COMPLETED, FAILED, CANCELLED = (
    "QUEUED", "RUNNING", "PAUSED", "INTERRUPTED", "COMPLETED", "FAILED", "CANCELLED")

ALLOWED = {
    QUEUED: {RUNNING, PAUSED, CANCELLED},
    RUNNING: {PAUSED, INTERRUPTED, COMPLETED, FAILED, CANCELLED},
    PAUSED: {QUEUED, CANCELLED},
    INTERRUPTED: {RUNNING, PAUSED, CANCELLED},
    FAILED: {QUEUED, CANCELLED},
    COMPLETED: set(),
    CANCELLED: set(),
}
RUNNABLE = (QUEUED, INTERRUPTED)


class BadTransition(Exception):
    pass


@dataclass
class Task:
    id: int
    kind: str
    title: str
    payload: dict
    state: str
    reason: str
    priority: int
    checkpoint: dict
    created: float
    updated: float


class TaskStore:
    def __init__(self, path: str | Path | None = None):
        self.path = writable(path or config.DATA_DIR / "nexus.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks(
                    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 0,
                    checkpoint TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS task_events(
                    id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, at REAL NOT NULL,
                    from_state TEXT, to_state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '');
            """)

    def close(self):
        self._db.close()

    def _row(self, r) -> Task:
        return Task(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5], r[6], json.loads(r[7]), r[8], r[9])

    def add(self, kind: str, title: str, payload: dict | None = None, priority: int = 0) -> int:
        now = time.time()
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO tasks(kind,title,payload,state,priority,created,updated) VALUES(?,?,?,?,?,?,?)",
                (kind, title, json.dumps(payload or {}, ensure_ascii=False), QUEUED, priority, now, now))
            self._db.execute("INSERT INTO task_events(task_id,at,from_state,to_state,reason) VALUES(?,?,?,?,?)",
                             (cur.lastrowid, now, None, QUEUED, "добавлена"))
            return cur.lastrowid

    def get(self, task_id: int) -> Task:
        with self._lock:
            r = self._db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if r is None:
            raise KeyError(task_id)
        return self._row(r)

    def all(self) -> list[Task]:
        with self._lock:
            return [self._row(r) for r in self._db.execute("SELECT * FROM tasks ORDER BY id")]

    def transition(self, task_id: int, to: str, reason: str = "") -> None:
        now = time.time()
        with self._lock, self._db:
            r = self._db.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
            if r is None:
                raise KeyError(task_id)
            if to not in ALLOWED[r[0]]:
                raise BadTransition(f"задача {task_id}: {r[0]} -> {to} нельзя")
            self._db.execute("UPDATE tasks SET state=?, reason=?, updated=? WHERE id=?", (to, reason, now, task_id))
            self._db.execute("INSERT INTO task_events(task_id,at,from_state,to_state,reason) VALUES(?,?,?,?,?)",
                             (task_id, now, r[0], to, reason))

    def save_checkpoint(self, task_id: int, checkpoint: dict) -> None:
        """Только у работающей задачи, целиком (одна транзакция)."""
        with self._lock, self._db:
            r = self._db.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
            if r is None or r[0] != RUNNING:
                raise BadTransition(f"контрольная точка только у RUNNING (задача {task_id})")
            self._db.execute("UPDATE tasks SET checkpoint=?, updated=? WHERE id=?",
                             (json.dumps(checkpoint, ensure_ascii=False), time.time(), task_id))

    def next_runnable(self) -> Task | None:
        with self._lock:
            r = self._db.execute(
                f"SELECT * FROM tasks WHERE state IN ({','.join('?' * len(RUNNABLE))}) "
                "ORDER BY priority DESC, id LIMIT 1", RUNNABLE).fetchone()
        return self._row(r) if r else None

    def recover_after_restart(self) -> int:
        """Задачи, которые «работали», когда Nexus выключился, становятся прерванными. Возвращает их число."""
        with self._lock:
            ids = [r[0] for r in self._db.execute("SELECT id FROM tasks WHERE state=?", (RUNNING,))]
        for i in ids:
            self.transition(i, INTERRUPTED, "Nexus был выключен во время работы")
        return len(ids)

    def history(self, task_id: int) -> list[tuple[str | None, str, str]]:
        with self._lock:
            return list(self._db.execute(
                "SELECT from_state,to_state,reason FROM task_events WHERE task_id=? ORDER BY id", (task_id,)))

    def recent_events(self, limit: int = 100) -> list[dict]:
        """Журнал: что и когда делал Nexus, по всем задачам сразу — для прозрачности (раздел 11 задания)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT e.at, e.from_state, e.to_state, e.reason, t.id, t.kind, t.title "
                "FROM task_events e JOIN tasks t ON t.id = e.task_id "
                "ORDER BY e.at DESC, e.id DESC LIMIT ?", (limit,)).fetchall()
        keys = ("at", "from_state", "to_state", "reason", "task_id", "kind", "title")
        return [dict(zip(keys, r)) for r in rows]
