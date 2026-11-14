"""Эмбеддинги для поиска по смыслу: сериализация вектора и косинусная близость. Без numpy —
векторы короткие партиями по одному, лишняя зависимость не нужна."""
from __future__ import annotations

import json
import math


def dumps(vector: list[float]) -> str:
    return json.dumps(vector)


def loads(text: str) -> list[float]:
    return json.loads(text) if text else []


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
