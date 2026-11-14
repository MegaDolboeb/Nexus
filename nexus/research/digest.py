"""Выжимка отобранного материала: Nexus читает саму статью (не только заголовок/описание из ленты)
и пересказывает её по правилу подачи темы (`how_to_present` из personal/interests.json).

Модель получает узкое поручение и явный запрет добавлять факты, которых нет в тексте
(раздел 7.1 задания: достоверность — по правилам, не по мнению модели; здесь — просто не выдумывать).
"""
from __future__ import annotations

from .match import Topic

MAX_ARTICLE_CHARS = 9000

# Новые материалы пишутся на этом языке (настройка «Язык» в панели); старые не переводятся задним числом.
LANGUAGE_INSTRUCTION = {
    "ru": "Отвечай только по-русски.",
    "en": "Answer only in English.",
}


def digest_messages(topic: Topic, source_name: str, title: str, article_text: str,
                    custom_instruction: str = "", language: str = "ru") -> list[dict]:
    how = topic.how_to_present or "Коротко и по делу."
    extra = f"\n\nЛичное пожелание Давида о том, как писать: {custom_instruction}" if custom_instruction else ""
    lang_rule = LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["ru"])
    return [
        {"role": "system", "content": (
            f"Ты помогаешь исследователю разобраться в материале. {lang_rule} "
            "Используй только то, что есть в тексте статьи — ничего не добавляй от себя и не придумывай фактов. "
            "Если в статье чего-то не хватает для вывода, так и скажи, а не предполагай." + extra)},
        {"role": "user", "content": (
            f"Тема: {topic.name}. Как подавать материал по этой теме: {how}\n\n"
            f"Источник: {source_name}. Заголовок: {title}\n\n"
            "СТАТЬЯ:\n" + article_text[:MAX_ARTICLE_CHARS] + "\n\n"
            "Сделай выжимку:\n1) Суть в одном-двух предложениях.\n2) 3–6 главных фактов списком.\n"
            "Следуй правилу подачи темы выше там, где оно применимо.")},
    ]
