"""Защита: Nexus пишет файлы ТОЛЬКО внутри своей собственной папки.

Каждая запись Nexus проходит через writable(): путь вне папки Nexus — ошибка.
"""
from __future__ import annotations

from pathlib import Path

from .config import ROOT


class ForbiddenWrite(Exception):
    pass


def writable(path: str | Path) -> Path:
    """Вернуть путь, если в него можно писать, иначе ForbiddenWrite."""
    p = Path(path).resolve()
    root = ROOT.resolve()
    if p != root and root not in p.parents:
        raise ForbiddenWrite(f"Nexus пишет только в {root}, а не в {p}")
    return p
