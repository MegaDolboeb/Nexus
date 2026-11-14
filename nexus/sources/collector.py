"""Сборщик: дёшево, без модели. Каждый источник проверяется отдельно; ошибка одного не мешает другим.
При ошибках источник проверяется всё реже (до раза в сутки) и помечается недоступным.
Пока приоритетная программа не свободна — ничего не собирает.
"""
from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from . import feeds
from .store import ItemStore, SourceStatus

log = logging.getLogger("nexus.sources")

MAX_BACKOFF_S = 24 * 3600
ARXIV_GAP_S = 3.0                     # arXiv просит не чаще одного запроса в 3 секунды
ARXIV_API = "https://export.arxiv.org/api/query?"


@dataclass
class Source:
    id: str
    name: str
    kind: str                         # rss | arxiv
    lang: str = "en"
    reliability: str = "medium"       # high | medium | low (нужно Этапу 4)
    every_min: float = 60
    url: str = ""
    categories: list[str] = field(default_factory=list)
    enabled: bool = True
    note: str = ""                    # что важно знать об источнике (показывается рядом с материалом)
    max_age_days: float = 30          # старее — не брать (у некоторых лент сотни старых записей)
    primary: bool = False             # первоисточник (сама публикация/официальное заявление) — для достоверности (Этап 4)

    def feed_url(self) -> str:
        if self.kind == "rss":
            return self.url
        if self.kind == "arxiv":
            q = " OR ".join(f"cat:{c}" for c in self.categories)
            return ARXIV_API + urllib.parse.urlencode({"search_query": q, "sortBy": "submittedDate",
                                                       "sortOrder": "descending", "max_results": 50})
        raise ValueError(f"неизвестный вид источника: {self.kind}")


def load_sources(path: str | Path | None = None) -> list[Source]:
    data = json.loads(Path(path or config.personal_or_example("sources.json")).read_text(encoding="utf-8"))
    known = Source.__dataclass_fields__.keys()
    return [Source(**{k: v for k, v in s.items() if k in known}) for s in data["sources"]]


def is_network_error(e: Exception) -> bool:
    return isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)) and \
        not isinstance(e, urllib.error.HTTPError)


class Collector:
    def __init__(self, store: ItemStore, sources: list[Source], fetch=feeds.fetch, clock=time.time,
                 sleep=time.sleep):
        self.store, self.sources = store, sources
        self.fetch, self.clock, self.sleep = fetch, clock, sleep
        self._last_arxiv = 0.0

    def due(self) -> list[Source]:
        now = self.clock()
        return [s for s in self.sources if s.enabled and self.store.status(s.id).next_try <= now]

    def run_due(self, may_work=lambda: True) -> dict[str, str]:
        """Проверить источники, которым пора. may_work() зовётся перед каждым: занято — стоп."""
        report: dict[str, str] = {}
        for s in self.due():
            if not may_work():
                report["_stopped"] = "приоритетная программа занята — сбор остановлен"
                break
            report[s.id] = self.run_one(s)
        return report

    def run_one(self, s: Source) -> str:
        now = self.clock()
        st = self.store.status(s.id)
        st.last_try = now
        try:
            if s.kind == "arxiv":
                wait = ARXIV_GAP_S - (time.monotonic() - self._last_arxiv)
                if wait > 0:
                    self.sleep(wait)
                self._last_arxiv = time.monotonic()
            entries = feeds.parse_feed(self.fetch(s.feed_url()))
            oldest = now - s.max_age_days * 86400
            entries = [e for e in entries if e.published is None or e.published >= oldest]
            added = self.store.add_entries(s.id, entries, now)
            st.ok, st.error, st.fails, st.last_ok = True, "", 0, now
            st.next_try = now + s.every_min * 60
            msg = f"ok: {len(entries)} в ленте, новых {added}"
        except Exception as e:                                     # noqa: BLE001 - один источник не валит остальные
            st.fails += 1
            st.ok = False
            kind = "временно недоступен (сеть)" if is_network_error(e) else "ошибка"
            st.error = f"{kind}: {type(e).__name__}: {e}"[:300]
            st.next_try = now + min(s.every_min * 60 * 2 ** st.fails, MAX_BACKOFF_S)
            msg = st.error
            log.warning("источник %s: %s", s.id, st.error)
        self.store.set_status(st)
        return msg
