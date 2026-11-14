"""Регулярная резервная копия базы и настроек (ЗАДАНИЕ.md, разделы 8 и 11).

Копирует data/nexus.db через sqlite3 .backup() — это безопасно делать даже пока файл используется —
и личные настройки (personal/*.json) в backups/ГГГГ-ММ-ДД/. Старые копии, кроме последних KEEP, удаляются.
Это не отменяет ручную осторожность перед рискованным шагом (правило 10) — просто подстраховка на каждый день.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

from . import config
from .safety import writable

KEEP_DAYS = 14


def backup_now(db_path: Path | None = None, personal_dir: Path | None = None,
               backups_root: Path | None = None) -> Path:
    db_path = db_path or (config.DATA_DIR / "nexus.db")
    personal_dir = personal_dir or config.PERSONAL_DIR
    backups_root = backups_root or (config.ROOT / "backups")
    out = writable(backups_root / time.strftime("%Y-%m-%d"))
    out.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        src = sqlite3.connect(db_path)
        try:
            dst = sqlite3.connect(out / "nexus.db")
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    if personal_dir.exists():
        for f in personal_dir.glob("*.json"):
            shutil.copy2(f, out / f.name)
    _prune(backups_root)
    return out


def _prune(backups_root: Path, keep: int = KEEP_DAYS) -> None:
    if not backups_root.exists():
        return
    days = sorted((p for p in backups_root.iterdir() if p.is_dir()), key=lambda p: p.name)
    for p in days[:-keep] if len(days) > keep else []:
        shutil.rmtree(p, ignore_errors=True)


def due(backups_root: Path | None = None) -> bool:
    """Пора ли делать новую копию (сегодняшней ещё нет)."""
    backups_root = backups_root or (config.ROOT / "backups")
    return not (backups_root / time.strftime("%Y-%m-%d")).exists()
