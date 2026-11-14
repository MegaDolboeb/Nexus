"""Отбор: дешёвый (по ключевым словам, без модели) и оценка кандидатов моделью (узкое поручение, ответ JSON).

Состояния материала: NEW -> MATCHED | SKIPPED (без модели) -> SELECTED | REJECTED (после оценки).
Решение «изучать или нет» принимает код по оценкам, а не модель.
"""
from __future__ import annotations

import json
import time

from ..sources.collector import Source
from ..sources.store import ItemStore
from .match import Topic, match_item

MIN_MATCH_SCORE = 0.3          # ниже — материал по темам почти не задевает
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "significance": {"type": "integer", "minimum": 1, "maximum": 5},
        "novelty": {"type": "integer", "minimum": 1, "maximum": 5},
        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
        "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
        "why": {"type": "string"},
    },
    "required": ["significance", "novelty", "relevance", "complexity", "why"],
}


def run_matching(store: ItemStore, topics: list[Topic], sources: list[Source], now: float | None = None,
                 min_score: float = MIN_MATCH_SCORE) -> dict[str, int]:
    now = now or time.time()
    rel = {s.id: s.reliability for s in sources}
    counts = {"MATCHED": 0, "SKIPPED": 0}
    for it in store.items_in_state("NEW"):
        age = (now - (it["published"] or it["fetched"])) / 86400
        ms = [m for m in match_item(it["title"], it["summary"], topics, rel.get(it["source_id"], "medium"), age)
              if m.score >= min_score]
        state = "MATCHED" if ms else "SKIPPED"
        store.set_matches(it["id"], ms, state)
        counts[state] += 1
    return counts


PRACTICAL_TOPICS = {"business"}      # здесь ценна практическая польза, а не новизна (профиль Давида, п. 9)


def decide(s: dict, topic_id: str = "") -> str:
    """Код решает по оценкам: изучать, если материал про тему и не пустяк."""
    need_novelty = topic_id not in PRACTICAL_TOPICS
    if s["relevance"] >= 4 and s["significance"] >= 3 and (not need_novelty or s["novelty"] >= 3):
        return "SELECTED"
    return "REJECTED"


def triage_messages(topic: Topic, source_name: str, title: str, summary: str) -> list[dict]:
    return [
        {"role": "system", "content": "Ты оцениваешь материал для личного исследователя. Отвечай только JSON."},
        {"role": "user", "content": (
            f"Тема: {topic.name}. Что интересно в этой теме: {topic.about}\n\n"
            f"Материал (источник: {source_name}):\n{title}\n{summary[:1500]}\n\n"
            "Оцени строго, числами от 1 до 5. Большинство материалов — обычные, им ставь 2–3. "
            "5 ставь редко: только настоящему прорыву, какой бывает раз в месяц.\n"
            "significance — важность для темы: 1 — пустяк или реклама; 2 — мелкая новость; "
            "3 — обычная полезная новость; 4 — заметное событие в области; 5 — прорыв.\n"
            "novelty — новизна: 1 — пересказ давно известного; 3 — небольшой шаг вперёд; 5 — совсем новое.\n"
            "relevance — насколько материал именно про эту тему: 1 — почти не про неё; 3 — частично; "
            "5 — прямо про неё.\n"
            "complexity — сложность (1 — просто, 5 — нужны глубокие специальные знания).\n"
            "why — одно короткое предложение по-русски: почему стоит или не стоит изучать.")},
    ]


def parse_scores(text: str) -> dict:
    s = json.loads(text)
    for k in ("significance", "novelty", "relevance", "complexity"):
        v = int(s[k])
        if not 1 <= v <= 5:
            raise ValueError(f"{k}={v}")
        s[k] = v
    s["why"] = str(s.get("why", "")).strip()
    return s
