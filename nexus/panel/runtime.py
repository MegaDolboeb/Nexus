"""Один общий процесс: и панель, и сама работа Nexus. Кнопки «Запустить/Пауза/Остановить»
управляют ЭТИМ же объектом, который крутит Supervisor в фоновом потоке — поэтому они по-настоящему
действуют, а не притворяются. Уступка приоритетной программе (yield_now) работает ровно так же, как
обычная пауза и остановка — это то же самое прерывание, что и её занятость, только причина другая.
"""
from __future__ import annotations

import logging
import threading
import time

from .. import backup, config, integrity
from .. import notify as notify_module
from ..engine import Engine, EngineBusy
from ..jobs import make_jobs
from ..memory.store import MemoryStore
from ..priority_watch import PriorityWatch
from ..research.match import load_topics
from ..research.planner import plan, plan_credibility, plan_digest, plan_memory
from ..research.select import run_matching
from ..sources.collector import Collector, load_sources
from ..sources.store import ItemStore
from ..supervisor import Supervisor
from ..tasks import TaskStore

log = logging.getLogger("nexus.panel.runtime")

RUNNING, PAUSED, STOPPED = "running", "paused", "stopped"
COLLECT_EVERY_S = 60.0


class Runtime:
    """Всё собрано здесь, чтобы и панель, и фоновый цикл смотрели на одни и те же объекты.
    Параметры можно подставить свои — для тестов, без настоящего движка."""

    def __init__(self, settings: config.Settings | None = None, store=None, watch=None, engine=None,
                items=None, sources=None, topics=None, memory=None, supervisor=None, collector=None,
                clock=time.monotonic, sleep=time.sleep):
        self.s = settings or config.load_settings()
        self.store = store or TaskStore()
        n = self.store.recover_after_restart()
        if n:
            log.info("после перезапуска прерванных задач: %d (продолжатся с контрольной точки)", n)
        self.watch = watch or PriorityWatch(settings=self.s)
        self.engine = engine or Engine(self.s).claim()
        self.items = items or ItemStore()
        self.sources = sources if sources is not None else load_sources()
        self.topics = topics if topics is not None else load_topics()
        self.memory = memory or MemoryStore()
        self.supervisor = supervisor or Supervisor(
            self.store, self.watch, self.engine, settings=self.s,
            jobs=make_jobs(self.items, self.topics, self.sources, self.memory),
            notify=notify_module.send)
        self.collector = collector or Collector(self.items, self.sources)
        self.clock, self.sleep = clock, sleep

        self._lock = threading.Lock()
        self._state = STOPPED
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_collect = 0.0
        self.last_error = ""
        self.engine_alive_cached = False
        self.integrity_changed = integrity.check()      # замок с сигнализацией (раздел 10), не стоп-кран
        if self.integrity_changed:
            log.warning("защищённый код изменён с последней проверки: %s", ", ".join(self.integrity_changed))

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    # ---------- управление: то же самое, что три кнопки на Главной ----------
    def start(self) -> None:
        """И «Запустить» с нуля, и возобновление после паузы — одна и та же кнопка."""
        with self._lock:
            if self._state == RUNNING:
                return
            was_stopped = self._state == STOPPED
            self._state = RUNNING
            if was_stopped:
                self._stop_event.clear()
        if was_stopped and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, daemon=True, name="nexus-runtime")
            self._thread.start()
        log.info("Nexus запущен")

    def pause(self) -> None:
        with self._lock:
            if self._state != RUNNING:
                return
            self._state = PAUSED
        self.supervisor.shutdown("Давид поставил Nexus на паузу")
        log.info("Nexus на паузе")

    def stop(self) -> None:
        with self._lock:
            if self._state == STOPPED:
                return
            self._state = STOPPED
        self.supervisor.shutdown("Давид остановил Nexus")
        log.info("Nexus остановлен, контрольная точка сохранена")

    def shutdown_process(self) -> None:
        """Для полного выхода (трей → Выход): остановить и дождаться фонового потока."""
        self.stop()
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    # ---------- фоновый цикл ----------
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._refresh_engine_alive()
                if self.state == RUNNING:
                    self.supervisor.tick()
                    if self.clock() >= self._next_collect:
                        self._next_collect = self.clock() + COLLECT_EVERY_S
                        self._collect_once()
            except Exception:                                      # noqa: BLE001 — фон не должен падать молча
                log.exception("ошибка в фоновом цикле Nexus")
                self.last_error = "ошибка в фоновом цикле — смотри logs/nexus.log"
            self.sleep(self.s.watch_every_s)

    def _refresh_engine_alive(self) -> None:
        """Проверка движка — здесь, раз в отрезок, а не на каждый клик по панели.
        Раньше эту сетевую проверку делала каждая страница заново (до 2 секунд на клик,
        особенно с VPN); теперь панель просто читает уже готовое значение."""
        try:
            self.engine_alive_cached = self.engine.alive()
        except Exception:                                           # noqa: BLE001
            self.engine_alive_cached = False

    def _collect_once(self) -> None:
        self.collector.run_due(lambda: self.watch.check().may_work)
        run_matching(self.items, self.topics, self.sources)
        plan(self.store, self.items)
        plan_digest(self.store, self.items)
        plan_credibility(self.store, self.items, self.sources)
        plan_memory(self.store, self.items, self.memory)
        if backup.due():
            backup.backup_now()


class Unavailable:
    """Подставляется вместо Runtime, если свой движок занят (например, уже работает второй Nexus).
    Панель продолжает показывать данные, просто без управления — честно, без притворства."""

    state = "недоступно"

    def __init__(self, reason: str):
        self.reason = reason

    def start(self) -> None:
        log.warning("не могу запустить: %s", self.reason)

    def pause(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def shutdown_process(self) -> None:
        pass


_runtime = None
_runtime_lock = threading.Lock()


def get_runtime():
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            try:
                _runtime = Runtime()
            except EngineBusy as e:
                _runtime = Unavailable(str(e))
        return _runtime
