"""Достоверность (ЗАДАНИЕ.md, раздел 7.1). Статус ставит ПРОГРАММА по правилам, модель не выдумывает:

  ПОДТВЕРЖДЕНО — есть первоисточник (оригинальная публикация, официальное заявление) ИЛИ
                 минимум два независимых надёжных источника;
  ЧАСТИЧНО — один надёжный источник;
  НЕ ПРОВЕРЕНО — только источники с низкой надёжностью;
  ОСПАРИВАЕТСЯ — независимые источники расходятся в фактах.

Материалы об одном и том же сначала группируются по теме и похожести заголовка — дёшево, без модели.
Модель зовётся только когда есть что сравнивать (группа из 2+ материалов из разных источников),
и отвечает на узкий вопрос — тот же случай или нет, расходятся ли факты — а не выдумывает сам статус.

Известное упрощение: группировка жадная (каждый новый материал сравнивается только с «затравкой» группы,
не со всеми её членами) и сравнение расхождения делается по первым двум материалам группы, а не по всем
парам. Для начального объёма материалов этого достаточно; при необходимости можно уточнить.
"""
from __future__ import annotations

import json
import re

CONFIRMED, PARTIAL, UNVERIFIED, DISPUTED = "ПОДТВЕРЖДЕНО", "ЧАСТИЧНО", "НЕ ПРОВЕРЕНО", "ОСПАРИВАЕТСЯ"
LOW_RELIABILITY_BADGE = "НИЗКАЯ НАДЁЖНОСТЬ ИСТОЧНИКА"

WORD = re.compile(r"[\w\-]+", re.U)
MIN_TOKEN_LEN = 4                 # короткие слова («в», «the», «и») не несут смысла для сравнения заголовков
TITLE_SIMILARITY = 0.45
CLUSTER_WINDOW_DAYS = 5.0

DISPUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "same_event": {"type": "boolean"},
        "contradicts": {"type": "boolean"},
        "why": {"type": "string"},
    },
    "required": ["same_event", "contradicts", "why"],
}


def title_signature(title: str) -> set[str]:
    return {w for w in WORD.findall(title.lower()) if len(w) >= MIN_TOKEN_LEN}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(items: list[dict], threshold: float = TITLE_SIMILARITY,
           window_days: float = CLUSTER_WINDOW_DAYS) -> list[list[dict]]:
    """Группирует материалы ОДНОЙ темы по похожести заголовка и близости по времени.
    items: словари с id, title, source_id, published/fetched, topic_id."""
    pool = [dict(it, _sig=title_signature(it["title"]), _t=(it.get("published") or it["fetched"])) for it in items]
    groups: list[list[dict]] = []
    used = [False] * len(pool)
    for i, a in enumerate(pool):
        if used[i]:
            continue
        group = [a]
        used[i] = True
        for j in range(i + 1, len(pool)):
            if used[j]:
                continue
            b = pool[j]
            if b["topic_id"] != a["topic_id"] or abs(b["_t"] - a["_t"]) > window_days * 86400:
                continue
            if jaccard(a["_sig"], b["_sig"]) >= threshold:
                group.append(b)
                used[j] = True
        groups.append(group)
    return groups


def assess(members: list[dict], sources: dict) -> tuple[str, str, bool]:
    """members: словари хотя бы с source_id. sources: {source_id: Source}.
    Возвращает (статус, причина, низкая_ли_надёжность_у_всех)."""
    by_source = {}
    for m in members:
        by_source.setdefault(m["source_id"], sources.get(m["source_id"]))
    srcs = [s for s in by_source.values() if s is not None]
    if any(getattr(s, "primary", False) for s in srcs):
        return CONFIRMED, "это первоисточник (оригинальная публикация или официальное заявление)", False
    reliable = sorted({s.id for s in srcs if s.reliability in ("high", "medium")})
    if len(reliable) >= 2:
        return CONFIRMED, "независимо подтверждено источниками: " + ", ".join(reliable), False
    if len(reliable) == 1:
        return PARTIAL, "один надёжный источник, независимых подтверждений пока нет", False
    return UNVERIFIED, "только источники с низкой надёжностью", bool(srcs)


def dispute_messages(title_a: str, text_a: str, title_b: str, text_b: str) -> list[dict]:
    return [
        {"role": "system", "content": "Ты сравниваешь два материала из разных источников. Отвечай только по-русски, только JSON."},
        {"role": "user", "content": (
            f"Материал 1 ({title_a}):\n{text_a[:1200]}\n\n"
            f"Материал 2 ({title_b}):\n{text_b[:1200]}\n\n"
            "same_event — это один и тот же случай или новость (true/false).\n"
            "contradicts — если same_event=true, расходятся ли они в конкретных фактах "
            "(цифрах, причинах, кто виноват и т.п.); если same_event=false, всегда false.\n"
            "why — одно короткое предложение по-русски.")},
    ]


def parse_dispute(text: str) -> dict:
    d = json.loads(text)
    return {"same_event": bool(d["same_event"]), "contradicts": bool(d["contradicts"]),
           "why": str(d.get("why", "")).strip()[:300]}
