"""Планировщик: создаёт задачи для модели, только когда есть что изучать (ЗАДАНИЕ.md, раздел 7).
Нет интересного — нет задач, модель не запускается «ради работы»."""
from __future__ import annotations

from ..tasks import INTERRUPTED, QUEUED, RUNNING, TaskStore
from ..sources.store import ItemStore
from .credibility import assess, cluster

TRIAGE_BATCH = 20
DIGEST_BATCH = 10
MEMORY_BATCH = 10


def _busy_kinds(tasks: TaskStore) -> set[str]:
    return {t.kind for t in tasks.all() if t.state in (QUEUED, RUNNING, INTERRUPTED)}


def plan(tasks: TaskStore, items: ItemStore, batch: int = TRIAGE_BATCH) -> int | None:
    """Добавить задачу оценки, если такой ещё нет в работе и есть кандидаты. Возвращает id новой задачи или None."""
    if "triage" in _busy_kinds(tasks):
        return None
    cands = items.top_matched(limit=batch)
    if not cands:
        return None
    return tasks.add("triage", f"Оценка {len(cands)} материалов", {"item_ids": [c["id"] for c in cands]})


def plan_digest(tasks: TaskStore, items: ItemStore, batch: int = DIGEST_BATCH) -> int | None:
    """Добавить задачу выжимки для отобранных (SELECTED) материалов без выжимки."""
    if "digest" in _busy_kinds(tasks):
        return None
    sel = items.items_in_state("SELECTED", limit=batch)
    if not sel:
        return None
    topics = {}
    for it in sel:
        tid = items.score_topic(it["id"])                 # тема, по которой материал реально отобрали
        if tid:
            topics[str(it["id"])] = tid
    return tasks.add("digest", f"Выжимка {len(sel)} материалов",
                     {"item_ids": [it["id"] for it in sel], "topics": topics})


def plan_credibility(tasks: TaskStore, items: ItemStore, sources: list) -> int | None:
    """Группирует выжимки по темам и похожести заголовка; одиночные группы (и группы с первоисточником)
    считает сразу, без модели; для групп из 2+ материалов разных источников — заводит задачу модели.
    Уже посчитанные (без изменений в составе) группы пропускает."""
    if "credibility" in _busy_kinds(tasks):
        return None
    by_source = {s.id: s for s in sources}
    pool = items.digested_items_for_credibility()
    by_topic: dict[str, list[dict]] = {}
    for it in pool:
        by_topic.setdefault(it["topic_id"], []).append(it)
    multi: list[dict] = []
    for topic_id, lst in by_topic.items():
        for group in cluster(lst):
            ids = sorted(m["id"] for m in group)
            if items.credibility_matches(ids):
                continue
            distinct_sources = {m["source_id"] for m in group}
            if len(group) >= 2 and len(distinct_sources) >= 2:
                multi.append({"topic_id": topic_id, "item_ids": ids})
            else:
                status, reason, low = assess(group, by_source)
                items.save_credibility(topic_id, status, reason, low, ids)
    if not multi:
        return None
    return tasks.add("credibility", f"Достоверность: {len(multi)} групп", {"clusters": multi})


def plan_memory(tasks: TaskStore, items: ItemStore, memory, batch: int = MEMORY_BATCH) -> int | None:
    """Память (Этап 5): только материалы, для которых уже посчитана достоверность и которых ещё нет
    в памяти. Порядок «сначала достоверность, потом память» держится на этой проверке, а не на коде."""
    if "memory" in _busy_kinds(tasks):
        return None
    ids = []
    for it in items.digested_items_for_credibility():
        if len(ids) >= batch:
            break
        if items.credibility_of(it["id"]) is not None and memory.item_memory_id(it["id"]) is None:
            ids.append(it["id"])
    if not ids:
        return None
    return tasks.add("memory", f"Память: {len(ids)} материалов", {"item_ids": ids})
