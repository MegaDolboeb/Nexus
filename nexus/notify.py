"""Уведомления Windows (ЗАДАНИЕ.md, раздел 10): через иконку в трее (pystray), без новых
зависимостей — у pystray на Windows уже есть всплывающее уведомление (balloon).

Не критично: если иконки ещё нет (панель без окна, тесты) или показать не вышло, Nexus просто
логирует и работает дальше — уведомление никогда не должно уронить настоящую работу."""
from __future__ import annotations

import logging

log = logging.getLogger("nexus.notify")

_icon = None


def set_icon(icon) -> None:
    """Вызывает nexus.panel.window при создании иконки трея."""
    global _icon
    _icon = icon


def send(title: str, message: str) -> None:
    if _icon is None:
        log.info("уведомление (трея ещё нет): %s — %s", title, message)
        return
    try:
        _icon.notify(message, title)
    except Exception as e:                                      # noqa: BLE001 - уведомление не критично
        log.warning("не удалось показать уведомление «%s»: %s", title, e)
