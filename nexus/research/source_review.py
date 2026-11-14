"""Проверка нового источника перед добавлением (раздел 10 задания): Давид описывает источник
своими словами, модель даёт короткую подсказку по тому, что мы ей показали (название, ссылка,
пример заголовков из ленты) — она не ищет репутацию источника в интернете сама и не выдаёт
окончательный вердикт. Добавлять источник или нет — решает только Давид."""
from __future__ import annotations

import json

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["good", "caution", "unclear"]},
        "why": {"type": "string"},
    },
    "required": ["verdict", "why"],
}


def review_messages(name: str, url: str, note: str, sample_titles: list[str]) -> list[dict]:
    titles = "\n".join(f"- {t}" for t in sample_titles[:8]) or "(не удалось получить примеры заголовков)"
    return [
        {"role": "system", "content": (
            'Ты помогаешь оценить источник новостей/статей перед добавлением в список Nexus. '
            'Отвечай строго JSON: {"verdict": "good"|"caution"|"unclear", "why": "..."}. '
            "good — источник похож на солидный/профильный по тому, что видно; caution — есть повод "
            "насторожиться (желтизна, анонимность, узкая пропаганда, непонятный домен); unclear — по "
            "этим данным не распознать. Не выдумывай репутацию, которой не знаешь наверняка — тогда "
            "честно unclear. Пиши коротко, 1-3 предложения, по-русски.")},
        {"role": "user", "content": (
            f"Название источника: {name}\nСсылка: {url}\n"
            f"Почему Давид хочет его добавить: {note or '(не указано)'}\n\n"
            f"Примеры заголовков из его ленты:\n{titles}")},
    ]


def parse_verdict(raw: str) -> dict:
    d = json.loads(raw)
    verdict = d.get("verdict")
    if verdict not in ("good", "caution", "unclear"):
        verdict = "unclear"
    return {"verdict": verdict, "why": str(d.get("why", ""))[:500]}
