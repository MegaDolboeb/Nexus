"""Короткая общая выжимка по пачке уже готовых материалов (раздел 10 задания: «иначе это ад всё
читать»). Нарочно очень коротко — 5-8 пунктов на всё, не пересказ каждого материала отдельно."""
from __future__ import annotations

MAX_ITEMS = 25
MAX_CHARS_PER_ITEM = 350


def overview_messages(materials: list[dict], language: str = "ru") -> list[dict]:
    from .digest import LANGUAGE_INSTRUCTION
    lang_rule = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["ru"])
    body = "\n\n".join(
        f"[{i + 1}] {m['title']}\n{m['text'][:MAX_CHARS_PER_ITEM]}"
        for i, m in enumerate(materials[:MAX_ITEMS])
    )
    return [
        {"role": "system", "content": (
            f"Ты помогаешь исследователю быстро окинуть взглядом пачку уже готовых материалов. {lang_rule} "
            "Не пересказывай каждый материал по отдельности — слей главное в 5-8 коротких пунктов, "
            "сгруппировав похожее. Используй только то, что есть в текстах ниже, не добавляй фактов "
            "от себя.")},
        {"role": "user", "content": f"Материалы:\n\n{body}\n\nСделай очень короткую общую выжимку."},
    ]
