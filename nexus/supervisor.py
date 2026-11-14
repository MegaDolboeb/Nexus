"""Supervisor — главный в Nexus. Только он разрешает работу. Нейросеть ничего не решает.

Правила:
- Приоритетная программа не FREE (BUSY или UNKNOWN) -> уступить немедленно и ждать.
- После того как она освободилась, подождать ещё after_priority_s.
- Работать отрезками segment_s, между ними пауза rest_s с ВЫКЛЮЧЕННЫМ движком.
- Нет задач -> движок выключен.
- Уступка: запрет новых запросов -> обрыв запроса -> задача INTERRUPTED с последней контрольной точкой
  -> выгрузка модели -> остановка своего движка -> проверка видеопамяти. Пока не подтверждено — новых задач нет.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from . import config, resources
from .engine import Cancelled
from .jobs import JOBS
from .tasks import COMPLETED, FAILED, INTERRUPTED, RUNNING, TaskStore

log = logging.getLogger("nexus.supervisor")

WAIT, WORK, REST = "WAIT", "WORK", "REST"


class Resources:
    """Ресурсы компьютера; в тестах подменяется."""

    def __init__(self, settings: config.Settings):
        self.s = settings

    def gpu(self):
        return resources.gpu()

    def free_ram_gb(self) -> float:
        return resources.free_ram_gb()

    def games(self) -> set[str]:
        import psutil
        return resources.running_games((p.info["name"] or "" for p in psutil.process_iter(["name"])), self.s)


@dataclass
class YieldRecord:
    reason: str
    total_s: float              # от обнаружения до подтверждённой свободной видеопамяти
    released: bool


class _Ctx:
    """То, что видит шаг задачи: только «спроси модель». Перед каждым запросом — проверка приоритетной программы."""

    def __init__(self, sup: "Supervisor"):
        self.sup = sup

    def chat(self, messages, num_predict: int = 400, fmt=None, temperature: float | None = None) -> str:
        sup = self.sup
        if sup._stop.is_set():
            raise Cancelled()
        if not sup.watch.check().may_work:                 # перед каждым запросом к модели
            sup._stop_reason = sup._stop_reason or "приоритетная программа стала занята (проверка перед запросом)"
            raise Cancelled()
        options = dict(sup.s.work_options, num_predict=num_predict)
        if temperature is not None:
            options["temperature"] = temperature
        out = []
        kw = {"fmt": fmt} if fmt is not None else {}
        for piece in sup.engine.chat_stream(sup.s.work_model, messages, options, keep_alive="30m",
                                            on_start=sup._register_generation, **kw):
            out.append(piece)
        sup._register_generation(None)
        return "".join(out)

    def pull(self, model: str) -> None:
        """Скачать модель в свою папку — это просто файл на диск, видеокарту не трогает,
        поэтому, в отличие от chat/embed, ждать свободной приоритетной программы не нужно."""
        sup = self.sup
        if sup._stop.is_set():
            raise Cancelled()
        sup.engine.pull(model)

    @property
    def model(self) -> str:
        return self.sup.s.work_model

    @property
    def settings(self) -> config.Settings:
        """Пресет «как Nexus исследует» и свой стиль — личные настройки (панель → Настройки)."""
        return self.sup.s

    def embed(self, text: str) -> list[float]:
        """Эмбеддинг текста (поиск по смыслу). Та же проверка приоритетной программы перед запросом."""
        sup = self.sup
        if sup._stop.is_set():
            raise Cancelled()
        if not sup.watch.check().may_work:
            sup._stop_reason = sup._stop_reason or "приоритетная программа стала занята (проверка перед запросом)"
            raise Cancelled()
        vectors = sup.engine.embed(sup.s.embed_model, [text], keep_alive="30m")
        return vectors[0] if vectors else []


class Supervisor:
    def __init__(self, store: TaskStore, watch, engine, res=None, settings: config.Settings | None = None,
                 clock=time.monotonic, jobs=None, notify=None):
        self.store, self.watch, self.engine = store, watch, engine
        self.s = settings or config.Settings()
        self.res = res or Resources(self.s)
        self.clock = clock
        self.jobs = jobs or JOBS
        self.notify = notify or (lambda title, message: None)   # раздел 10: Windows-уведомления, необязательно
        self.mode, self.reason = WAIT, "старт"
        self.last_busy = float("-inf")
        self.rest_until = 0.0
        self.segment_end = 0.0
        self.baseline_mb: int | None = None
        self.vram_blocked = False
        self.yields: list[YieldRecord] = []
        self._stop = threading.Event()
        self._stop_reason = ""
        self._gen = None
        self._gen_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    # ---------- главный цикл ----------
    def tick(self) -> None:
        now = self.clock()
        obs = self.watch.check()
        if not obs.may_work:
            self.last_busy = now
            if self._engine_busy():
                self.yield_now("приоритетная программа: " + (", ".join(obs.busy or obs.unknown) or obs.state), detected_at=now)
            self._set(WAIT, "приоритетная программа занята: " + (", ".join(obs.busy or obs.unknown) or obs.state))
            return

        if self.vram_blocked and not self._recheck_vram():
            self._set(WAIT, "видеопамять не подтверждена свободной")
            return

        if now - self.last_busy < self.s.after_priority_s:
            self._set(WAIT, "даём приоритетной программе время после её занятости")
            return

        if self.mode == WORK:
            if not self._worker_alive():
                self.yield_now("задачи закончились", detected_at=now)
                self._set(WAIT, "задач нет")
            elif now >= self.segment_end:
                self.yield_now("конец отрезка работы", detected_at=now)
                self.rest_until = now + self.s.rest_s
                self._set(REST, "пауза между отрезками: движок выключен")
            return

        if self.mode == REST and now < self.rest_until:
            return

        games = self.res.games()
        if games:
            self._set(WAIT, "идёт игра: " + ", ".join(sorted(games)))      # работа на процессоре — Этап 7
            return
        if self.res.free_ram_gb() < self.s.min_free_ram_gb:
            self._set(WAIT, "мало свободной оперативной памяти")
            return
        if self.store.next_runnable() is None:
            self._set(WAIT, "задач нет")
            return
        self._start_segment(now)

    # ---------- отрезок работы ----------
    def _start_segment(self, now: float) -> None:
        g = self.res.gpu()
        if g is None:
            self._set(WAIT, "видеокарта не отвечает")
            return
        self.baseline_mb = g.used_mb
        self.engine.start()
        self._stop.clear()
        self._stop_reason = ""
        self.segment_end = now + self.s.segment_s
        self._worker = threading.Thread(target=self._work, name="nexus-worker", daemon=True)
        self._set(WORK, "отрезок работы")
        self._worker.start()

    def _work(self) -> None:
        ctx = _Ctx(self)
        while not self._stop.is_set():
            task = self.store.next_runnable()
            if task is None:
                return
            if not self.watch.check().may_work:            # перед каждой задачей
                return
            job = self.jobs.get(task.kind)
            if job is None:
                self.store.transition(task.id, RUNNING, "отрезок работы")
                self.store.transition(task.id, FAILED, f"неизвестный вид задачи: {task.kind}")
                continue
            self.store.transition(task.id, RUNNING, "отрезок работы")
            checkpoint = task.checkpoint
            try:
                while True:
                    if self._stop.is_set():
                        raise Cancelled()
                    checkpoint, done = job.step(ctx, task.payload, checkpoint)
                    self.store.save_checkpoint(task.id, checkpoint)      # шаг закончен целиком
                    if done:
                        self.store.transition(task.id, COMPLETED, "готово")
                        if task.kind == "errand":              # раздел 10: «поручение готово»
                            self.notify("Nexus: поручение готово", task.title)
                        break
            except Cancelled:
                self.store.transition(task.id, INTERRUPTED, self._stop_reason or "прервано")
                return
            except Exception as e:                                        # noqa: BLE001
                log.exception("задача %s упала", task.id)
                self.store.transition(task.id, FAILED, f"{type(e).__name__}: {e}"[:300])

    def _register_generation(self, gen) -> None:
        with self._gen_lock:
            self._gen = gen
            if gen is not None and self._stop.is_set():
                gen.cancel()

    # ---------- уступка ----------
    def yield_now(self, reason: str, detected_at: float | None = None) -> YieldRecord:
        t0 = detected_at if detected_at is not None else self.clock()
        self._stop_reason = reason
        self._stop.set()                                   # 1. новых запросов нет
        with self._gen_lock:                               # 2. оборвать текущий запрос
            if self._gen is not None:
                self._gen.cancel()
        if self._worker is not None:                       # 3. задача сама станет INTERRUPTED с последней точкой
            self._worker.join(timeout=15)
        try:                                               # 4. выгрузить свою модель
            if self.engine.alive():
                self.engine.unload_all()
        except Exception:                                  # noqa: BLE001
            log.warning("выгрузка не удалась, движок будет остановлен", exc_info=True)
        self.engine.stop()                                 # 5. остановить СВОЙ движок
        released = False
        if self.baseline_mb is not None:                   # 6. проверить видеопамять
            released = self.engine.wait_vram_released(self.baseline_mb, self.s.vram_tolerance_mb) is not None
        self.vram_blocked = not released
        rec = YieldRecord(reason, self.clock() - t0, released)
        self.yields.append(rec)
        log.info("уступка: %s; за %.1f с; видеопамять %s", reason, rec.total_s,
                 "свободна" if released else "НЕ ПОДТВЕРЖДЕНА")
        return rec

    def _recheck_vram(self) -> bool:
        g = self.res.gpu()
        if g is not None and self.baseline_mb is not None and not self.engine.alive() \
                and g.used_mb <= self.baseline_mb + self.s.vram_tolerance_mb:
            self.vram_blocked = False
            return True
        return False

    # ---------- служебное ----------
    def _worker_alive(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _engine_busy(self) -> bool:
        return self._worker_alive() or self.engine.alive()

    def is_busy(self) -> bool:
        """Публичный доступ к тому же вопросу — нужен панели, чтобы решить, стоит ли вообще уступать."""
        return self._engine_busy()

    def _set(self, mode: str, reason: str) -> None:
        if (mode, reason) != (self.mode, self.reason):
            log.info("%s: %s", mode, reason)
        self.mode, self.reason = mode, reason

    def shutdown(self, reason: str = "Nexus выключается") -> None:
        if self._engine_busy():
            self.yield_now(reason)
