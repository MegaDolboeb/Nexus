"""Смотритель приоритетной программы: занята ли она прямо сейчас. ТОЛЬКО ЧТЕНИЕ, ничего не меняет.

Состояния: BUSY, FREE, UNKNOWN (= считается BUSY). Настраивается в Settings.priority_* (панель →
Настройки → «Приоритетная программа»). Если priority_name пустой — функция выключена: всегда FREE,
никого не ждём.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config

BUSY = "BUSY"
FREE = "FREE"
UNKNOWN = "UNKNOWN"


@dataclass
class Proc:
    name: str                        # в нижнем регистре
    cmdline: str                     # в нижнем регистре, может быть пустой


@dataclass
class Observation:
    state: str
    busy: list[str] = field(default_factory=list)      # почему занята
    unknown: list[str] = field(default_factory=list)   # что не удалось проверить
    at: float = 0.0
    took_ms: float = 0.0

    @property
    def may_work(self) -> bool:
        return self.state == FREE


class SystemProbe:
    """Настоящий компьютер. В тестах подменяется."""

    def processes(self) -> list[Proc]:
        import psutil
        result = []
        for p in psutil.process_iter(["name", "cmdline"]):
            info = p.info
            cmd = info.get("cmdline") or []
            result.append(Proc((info.get("name") or "").lower(), " ".join(cmd).lower()))
        return result

    def listening_ports(self) -> set[int]:
        import psutil
        return {c.laddr.port for c in psutil.net_connections(kind="tcp")
                if c.status == psutil.CONN_LISTEN and c.laddr}

    def http_json(self, url: str, timeout: float):
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def read_text(self, path) -> str:
        with open(path, "r", encoding="utf-8") as f:       # только чтение
            return f.read()

    def now(self) -> float:
        return time.time()

    def sleep(self, s: float) -> None:
        time.sleep(s)


class PriorityWatch:
    def __init__(self, probe=None, settings: config.Settings | None = None):
        self.probe = probe or SystemProbe()
        self.s = settings or config.Settings()

    def check(self) -> Observation:
        t0 = time.perf_counter()
        if not self.s.priority_name:
            return Observation(FREE, [], [], self.probe.now(), (time.perf_counter() - t0) * 1000)

        busy: list[str] = []
        unknown: list[str] = []

        procs = None
        try:
            procs = self.probe.processes()
        except Exception as e:                                  # noqa: BLE001
            unknown.append(f"список процессов не получен: {type(e).__name__}")
        if procs is not None and self.s.priority_processes:
            running = sorted({p.name for p in procs if p.name in self.s.priority_processes})
            for name in running:
                busy.append(f"открыта программа: {name}")

        ports = None
        try:
            ports = self.probe.listening_ports()
        except Exception as e:                                  # noqa: BLE001
            unknown.append(f"список портов не получен: {type(e).__name__}")
        if ports is not None:
            for port in self.s.priority_ports:
                if port in ports:
                    busy.append(f"занят порт {port}")

        if self.s.priority_status_file:
            self._check_status_file(busy, unknown)

        if busy:
            state = BUSY
        elif unknown:
            state = UNKNOWN
        else:
            state = FREE
        return Observation(state, busy, unknown, self.probe.now(), (time.perf_counter() - t0) * 1000)

    def _check_status_file(self, busy, unknown):
        data = None
        for attempt in range(2):                                # файл может как раз заменяться: ещё раз через секунду
            try:
                data = json.loads(self.probe.read_text(self.s.priority_status_file))
                break
            except (OSError, ValueError):
                if attempt == 0:
                    self.probe.sleep(1.0)
        if not isinstance(data, dict):
            unknown.append("файл состояния не читается")
            return
        updated = data.get("updated")
        if not isinstance(updated, (int, float)) or self.probe.now() - updated > self.s.priority_status_stale_s:
            unknown.append("файл состояния устарел")
            return
        state = data.get("state")
        if state not in self.s.priority_status_free_values:
            busy.append(f"файл состояния: {state}")


if __name__ == "__main__":
    o = PriorityWatch().check()
    print(o.state)
    for r in o.busy:
        print("  занята:", r)
    for r in o.unknown:
        print("  не проверено:", r)
    print(f"  проверка заняла {o.took_ms:.0f} мс")
