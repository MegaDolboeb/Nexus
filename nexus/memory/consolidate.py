"""Решает, относится ли новый материал к уже известной теме памяти, по смыслу (эмбеддинг bge-m3),
а не только по словам. Код решает пороги и само действие; модель (узкое поручение) только
пересказывает объединённые выводы, когда тема обновляется, — ничего не придумывая о том,
новая это тема или нет.

Пороги (простой, явный выбор, можно будет уточнить по опыту):
  >= MERGE   — тот же случай/тема: обновить существующую запись, сохранив историю;
  >= RELATE  — заметно похоже, но не то же самое: завести новую тему и связать с похожей;
  < RELATE   — новая самостоятельная тема, без связей.
"""
from __future__ import annotations

from ..research.digest import LANGUAGE_INSTRUCTION
from .embeddings import cosine

MERGE_THRESHOLD = 0.86
RELATE_THRESHOLD = 0.72

MERGE, RELATE, NEW = "merge", "relate", "new"


def best_match(embedding: list[float], candidates: list[tuple[int, list[float]]]) -> tuple[int, float] | None:
    """candidates: [(memory_id, embedding), ...]. Возвращает (memory_id, похожесть) самого похожего, если есть."""
    best: tuple[int, float] | None = None
    for mid, vec in candidates:
        sim = cosine(embedding, vec)
        if best is None or sim > best[1]:
            best = (mid, sim)
    return best


def decide(embedding: list[float], candidates: list[tuple[int, list[float]]]) -> tuple[str, int | None, float]:
    match = best_match(embedding, candidates)
    if match is None:
        return NEW, None, 0.0
    mid, sim = match
    if sim >= MERGE_THRESHOLD:
        return MERGE, mid, sim
    if sim >= RELATE_THRESHOLD:
        return RELATE, mid, sim
    return NEW, None, sim


def merge_messages(title: str, old_conclusions: str, new_text: str, language: str = "ru") -> list[dict]:
    lang_rule = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["ru"])
    return [
        {"role": "system", "content": (
            f"Ты ведёшь краткую память по теме. Используй только то, что есть в старых и новых сведениях — "
            f"ничего не добавляй от себя. {lang_rule}")},
        {"role": "user", "content": (
            f"Тема: {title}\n\n"
            f"Прежние выводы:\n{old_conclusions or '(пока пусто)'}\n\n"
            f"Новые сведения:\n{new_text[:3000]}\n\n"
            "Напиши обновлённые выводы по теме: что по-прежнему верно, что нового добавилось, "
            "что устарело или уточнилось. Коротко, списком, без повторов.")},
    ]
