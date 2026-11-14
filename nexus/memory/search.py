"""Поиск по памяти: по смыслу (эмбеддинг запроса) вместе с поиском по словам (раздел 8 задания).
Если запрос неоднозначный — решение видно по самим результатам (две непохожие друг на друга темы
с близкими оценками), и код прямо сообщает об этом, вместо того чтобы наугад выбрать одну.
"""
from __future__ import annotations

from dataclasses import dataclass

from .embeddings import cosine
from .store import MemoryStore, MemoryTopic

AMBIGUOUS_GAP = 0.05       # насколько близко должны быть первые две разные темы, чтобы счесть запрос неоднозначным


@dataclass
class SearchResult:
    topic: MemoryTopic
    score: float
    via: str          # "смысл" | "слова" | "смысл и слова"


@dataclass
class SearchOutcome:
    results: list[SearchResult]
    ambiguous: bool
    question: str = ""


def search(store: MemoryStore, query: str, query_embedding: list[float] | None, limit: int = 5) -> SearchOutcome:
    semantic: dict[int, float] = {}
    if query_embedding:
        for t in store.all(limit=100000):
            sim = cosine(query_embedding, t.embedding)
            if sim > 0:
                semantic[t.id] = sim
    by_words = {t.id: t for t in store.search_text(query, limit=100)}

    scored: dict[int, SearchResult] = {}
    for mid, sim in semantic.items():
        scored[mid] = SearchResult(store.get(mid), sim, "смысл")
    for mid, t in by_words.items():
        if mid in scored:
            scored[mid].via = "смысл и слова"
            scored[mid].score = max(scored[mid].score, 0.5)       # по словам считаем «уверенным» совпадением
        else:
            scored[mid] = SearchResult(t, 0.5, "слова")

    ranked = sorted(scored.values(), key=lambda r: -r.score)[:limit]
    ambiguous, question = False, ""
    if len(ranked) >= 2 and ranked[0].score - ranked[1].score < AMBIGUOUS_GAP and \
            ranked[0].topic.title != ranked[1].topic.title:
        ambiguous = True
        titles = " или ".join(f"«{r.topic.title}»" for r in ranked[:2])
        question = f"Непонятно, что именно вы ищете: {titles}? Уточните, пожалуйста."
    return SearchOutcome(ranked, ambiguous, question)
