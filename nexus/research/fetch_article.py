"""Получение полного текста статьи по ссылке: просто HTML -> простой текст, без заголовков/меню/скриптов.

Лучшее, что можно сделать без отдельной библиотеки парсинга: вырезать явно служебные блоки
(script, style, nav, header, footer, aside, form), затем снять теги. Получается не идеально (иногда
остаётся «похожее по теме» или реклама), поэтому модель всегда получает явную инструкцию не придумывать
то, чего в тексте нет (research.digest).
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

from ..sources.feeds import USER_AGENT, html_to_text

MAX_BYTES = 3 * 1024 * 1024
MAX_CHARS = 12000                      # ограничение контекста модели — не весь текст, а разумный кусок
STRIP_BLOCKS = re.compile(
    r"<(script|style|nav|header|footer|aside|form|noscript)\b[^>]*>.*?</\1>", re.I | re.S)

# Известные признаки страницы проверки на робота вместо настоящей статьи (Cloudflare и похожие).
# Без этого модель получила бы текст заглушки и либо честно отказалась бы (как было один раз на деле),
# либо, если не повезёт, попыталась бы сделать выжимку из неё. Лучше не доводить до модели вовсе.
BOT_CHECK_MARKERS = (
    "client challenge", "checking your browser", "enable javascript and cookies",
    "attention required! | cloudflare", "needs to review the security of your connection",
    "verify you are a human", "are you a robot", "cf-chl-", "captcha",
)


class FetchError(Exception):
    pass


def fetch_article_text(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "xml" not in ctype and ctype:
                raise FetchError(f"не html-страница: {ctype}")
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.URLError as e:                               # noqa: BLE001
        raise FetchError(f"{type(e).__name__}: {e}") from e
    if len(raw) > MAX_BYTES:
        raise FetchError("страница больше 3 МБ")
    html = raw.decode("utf-8", errors="replace")
    html = STRIP_BLOCKS.sub(" ", html)
    text = html_to_text(html)
    if len(text) < 200:
        raise FetchError("после очистки почти ничего не осталось (возможно, страница требует JavaScript)")
    low = text.lower()
    if any(m in low for m in BOT_CHECK_MARKERS):
        raise FetchError("сайт отдал страницу проверки на робота вместо статьи")
    return text[:MAX_CHARS]
