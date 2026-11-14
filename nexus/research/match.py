"""Дешёвый отбор без модели: какие материалы относятся к каким темам и насколько.

Ключевое слово — начало слова («нейросет» ловит «нейросети»). Несколько частей через пробел —
подряд идущие слова («языков модел» ловит «языковые модели»). Короткие (до 3 букв) — почти целое слово,
чтобы «ген» не ловил «агент» и «генерал».
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .. import config

WORD = re.compile(r"[\w\-]+", re.U)
PRIORITY_WEIGHT = {1: 1.0, 2: 0.7, 3: 0.5}
RELIABILITY_WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.6}


@dataclass
class Topic:
    id: str
    name: str
    priority: int
    keywords: list[str]
    about: str = ""
    how_to_present: str = ""
    enabled: bool = True


def load_all_topics(path: str | Path | None = None) -> list[Topic]:
    """Все темы, включая выключенные — для страницы настроек, где их включают обратно."""
    data = json.loads(Path(path or config.personal_or_example("interests.json")).read_text(encoding="utf-8"))
    return [Topic(t["id"], t["name"], int(t.get("priority", 2)), [k.lower() for k in t.get("keywords", [])],
                 t.get("about", ""), t.get("how_to_present", ""), t.get("enabled", True)) for t in data["topics"]]


def load_topics(path: str | Path | None = None) -> list[Topic]:
    """Только включённые — то, чем на самом деле пользуется отбор материалов."""
    return [t for t in load_all_topics(path) if t.enabled]


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _word_hits(kw: str, w: str) -> bool:
    if len(kw) <= 3:
        return w == kw or (w.startswith(kw) and len(w) <= len(kw) + 2)
    return w.startswith(kw)


def keyword_in(kw: str, ws: list[str]) -> bool:
    parts = kw.split()
    if len(parts) == 1:
        return any(_word_hits(kw, w) for w in ws)
    n = len(parts)
    for i in range(len(ws) - n + 1):
        if all(_word_hits(p, ws[i + j]) for j, p in enumerate(parts)):
            return True
    return False


@dataclass
class Match:
    topic_id: str
    score: float
    hits: list[str]


def match_item(title: str, summary: str, topics: list[Topic], reliability: str = "medium",
               age_days: float = 0.0) -> list[Match]:
    """Темы материала со счётом. Заголовок весит вдвое больше описания."""
    tw, sw = words(title), words(summary)
    out = []
    for t in topics:
        in_title = [k for k in t.keywords if keyword_in(k, tw)]
        in_summary = [k for k in t.keywords if k not in in_title and keyword_in(k, sw)]
        if not in_title and not in_summary:
            continue
        raw = 2 * len(in_title) + len(in_summary)
        score = math.log1p(raw) * PRIORITY_WEIGHT.get(t.priority, 0.5) * RELIABILITY_WEIGHT.get(reliability, 0.85)
        score *= 0.5 ** (max(age_days, 0) / 7)                   # свежесть: каждые 7 дней вдвое меньше
        out.append(Match(t.id, round(score, 4), in_title + in_summary))
    return sorted(out, key=lambda m: -m.score)
