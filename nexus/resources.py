"""Ресурсы компьютера: видеокарта, память, игры, сидит ли Давид за компьютером. Только чтение."""
from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes
from dataclasses import dataclass

from . import config

NO_WINDOW = 0x08000000


@dataclass
class Gpu:
    util: int        # %
    used_mb: int
    free_mb: int
    total_mb: int


def gpu(timeout: float = 10.0) -> Gpu | None:
    """None, если nvidia-smi не ответила."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.free,memory.total",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=timeout, creationflags=NO_WINDOW).stdout
        util, used, free, total = (int(x) for x in out.strip().splitlines()[0].split(","))
        return Gpu(util, used, free, total)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def free_ram_gb() -> float:
    import psutil
    return psutil.virtual_memory().available / 2 ** 30


def idle_seconds() -> float:
    """Сколько секунд Давид не трогал мышь и клавиатуру."""
    class LastInput(ctypes.Structure):
        _fields_ = [("size", wintypes.UINT), ("time", wintypes.DWORD)]
    info = LastInput()
    info.size = ctypes.sizeof(LastInput)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.time) & 0xFFFFFFFF) / 1000.0


def running_games(process_names, settings: config.Settings | None = None) -> set[str]:
    """games — встроенный список, extra_pause_programs — свои программы Давида (раздел 10 задания)."""
    s = settings or config.Settings()
    names = {n.lower() for n in process_names}
    watched = set(s.games) | set(s.extra_pause_programs)
    return {g for g in watched if g in names}
