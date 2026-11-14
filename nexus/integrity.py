"""«Замок с сигнализацией» для кода, от которого зависит уважение к приоритетной программе.

По-честному: раз файлы лежат на диске в открытом виде, никто не может сделать их физически
неизменяемыми — тот, кто владеет компьютером, всегда может их отредактировать (через нейросеть
или сам). Это НЕ защита от этого, а тамп-эвиденс: контрольные суммы по известному списку файлов,
записанные в config/integrity.lock.json. Если хоть один разошёлся — Nexus громко предупредит при
запуске (баннер в панели), а не продолжит молча работать с подменённым кодом.

Обновлять замок (python -m nexus lock-integrity) нужно после ЛЮБОГО настоящего изменения этих
файлов — иначе собственная правка тоже будет считаться подозрительной, и так и должно быть.
"""
from __future__ import annotations

import hashlib
import json
import sys

from . import config

PROTECTED_FILES = (
    "nexus/safety.py",
    "nexus/priority_watch.py",
    "nexus/supervisor.py",
    "nexus/config.py",
)
LOCK_FILE = config.ROOT / "config" / "integrity.lock.json"


def _hash_file(rel: str) -> str | None:
    p = config.ROOT / rel
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compute() -> dict[str, str]:
    return {rel: h for rel in PROTECTED_FILES if (h := _hash_file(rel)) is not None}


def write_lock() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps(compute(), ensure_ascii=False, indent=1), encoding="utf-8")


def check() -> list[str]:
    """Файлы, чья контрольная сумма разошлась с записанной (включая пропавшие/новые из списка).
    Пустой список — всё совпадает. Нет файла замка вообще — ничего не проверяем (не пугаем раньше
    первого python -m nexus lock-integrity). В собранном .exe (PyInstaller) исходники .py упакованы
    внутрь, а не лежат рядом отдельными файлами — сверять их так нечем, поэтому там не проверяем."""
    if getattr(sys, "frozen", False):
        return []
    if not LOCK_FILE.exists():
        return []
    try:
        saved = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    current = compute()
    return [rel for rel in saved if current.get(rel) != saved[rel]]
