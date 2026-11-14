"""Свой движок Nexus: отдельный процесс Ollama, по умолчанию на 127.0.0.1:11436, с собственной
папкой моделей. Порты приоритетной программы (Settings.priority_ports) этот модуль НИКОГДА не
останавливает и ни о чём не просит: все запросы идут только на свой порт, а остановить можно
только процесс, который проверенно наш (ollama ... serve, слушает наш порт и не слушает её порты).
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

from . import config, resources
from .safety import writable

NO_WINDOW = 0x08000000


class EngineError(Exception):
    pass


class EngineBusy(EngineError):
    """Движком уже пользуется другая программа Nexus (сам Nexus или инструмент замера)."""


class EngineLock:
    """Один владелец движка за раз. Замок держится, пока программа жива, и снимается сам при её завершении."""

    def __init__(self, path=None):
        self.path = writable(path or config.DATA_DIR / "engine.lock")
        self._fh = None

    def acquire(self) -> "EngineLock":
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            raise EngineBusy("движком уже пользуется другая программа Nexus") from None
        self._fh = fh
        return self

    def release(self) -> None:
        import msvcrt
        if self._fh is not None:
            try:
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self._fh.close()
            self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


class Cancelled(Exception):
    """Генерация прервана (приоритетная программа стала занята или пауза)."""


@dataclass
class ProcInfo:
    pid: int
    name: str
    cmdline: str
    ports: set[int]


def is_our_engine(info: ProcInfo, port: int, excluded_ports: frozenset[int] = frozenset()) -> bool:
    """Только наш движок можно останавливать. Любое сомнение = не наш.
    excluded_ports — порты приоритетной программы (Settings.priority_ports): их не трогаем никогда."""
    if port in excluded_ports:
        return False
    if not info.name.lower().startswith("ollama"):
        return False
    if "serve" not in info.cmdline.lower():
        return False
    if port not in info.ports or info.ports & excluded_ports:
        return False
    return True


class Generation:
    """Один потоковый запрос. cancel() можно звать из другого потока: соединение рвётся сразу."""

    def __init__(self, conn: http.client.HTTPConnection):
        self._conn = conn
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        sock = self._conn.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self._conn.close()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()


class Engine:
    def __init__(self, settings: config.Settings | None = None, models_dir=None, exe: str | None = None,
                 host: str = "127.0.0.1"):
        self.s = settings or config.Settings()
        if self.s.engine_port in self.s.priority_ports:
            raise EngineError("порт движка Nexus совпадает с портом приоритетной программы")
        self.host = host
        self.port = self.s.engine_port
        self.models_dir = models_dir or config.MODELS_DIR
        self.exe = exe
        self.pid_file = writable(config.DATA_DIR / "engine.pid")
        self._proc: subprocess.Popen | None = None
        self.lock: EngineLock | None = None      # если задан: start/stop только у владельца замка

    def _require_lock(self):
        if self.lock is not None and not self.lock.held:
            raise EngineBusy("нет замка движка")

    def claim(self) -> "Engine":
        """Стать единственным владельцем движка (EngineBusy, если он уже занят другой программой Nexus)."""
        self.lock = EngineLock().acquire()
        return self

    # ---------- HTTP ----------
    def _request(self, method: str, path: str, body=None, timeout: float = 10.0):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            data = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, data, {"Content-Type": "application/json"})
            r = conn.getresponse()
            raw = r.read()
            if r.status >= 400:
                raise EngineError(f"{path}: HTTP {r.status} {raw[:200]!r}")
            return json.loads(raw.decode("utf-8")) if raw else {}
        finally:
            conn.close()

    def alive(self) -> bool:
        try:
            self._request("GET", "/api/version", timeout=2.0)
            return True
        except (OSError, EngineError, ValueError):
            return False

    def loaded(self) -> list[str]:
        """Какие модели сейчас загружены в наш движок."""
        return [m.get("name", "?") for m in self._request("GET", "/api/ps", timeout=3.0).get("models", [])]

    def list_models(self) -> list[str]:
        """Какие модели уже скачаны в свою папку — движок должен быть запущен."""
        return [m.get("name", "?") for m in self._request("GET", "/api/tags", timeout=5.0).get("models", [])]

    def pull(self, model: str, timeout: float = 1800.0) -> None:
        """Скачивает модель в свою папку моделей, не трогая другие установки Ollama.
        Блокирует поток до конца — звать из фоновой задачи, не из запроса панели."""
        self._require_lock()
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            conn.request("POST", "/api/pull", json.dumps({"model": model, "stream": True}).encode("utf-8"),
                        {"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status >= 400:
                raise EngineError(f"/api/pull: HTTP {r.status} {r.read()[:300]!r}")
            last_error = ""
            while True:
                line = r.readline()
                if not line:
                    break
                part = json.loads(line)
                if part.get("error"):
                    last_error = part["error"]
            if last_error:
                raise EngineError(last_error)
        finally:
            conn.close()

    # ---------- процесс ----------
    def start(self, timeout: float = 20.0) -> None:
        self._require_lock()
        if self.alive():
            return
        bundled = config.ROOT / "ollama" / "ollama.exe"      # своя копия рядом с собой (сборка .exe)
        exe = self.exe or (str(bundled) if bundled.exists() else None) or shutil.which("ollama")
        if not exe:
            raise EngineError("ollama.exe не найдена")
        env = dict(os.environ, OLLAMA_HOST=f"{self.host}:{self.port}", OLLAMA_MODELS=str(writable(self.models_dir)),
                   OLLAMA_KEEP_ALIVE="0")
        logs = writable(config.LOGS_DIR)
        logs.mkdir(parents=True, exist_ok=True)
        err = open(writable(logs / "engine.err.log"), "ab")
        self._proc = subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=err,
                                      creationflags=NO_WINDOW)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(self._proc.pid), encoding="utf-8")
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.alive():
                return
            if self._proc.poll() is not None:
                raise EngineError(f"движок завершился сразу, код {self._proc.returncode}")
            time.sleep(0.25)
        raise EngineError("движок не ответил вовремя")

    def _proc_info(self, pid: int) -> ProcInfo | None:
        import psutil
        try:
            p = psutil.Process(pid)
            ports = {c.laddr.port for c in p.net_connections(kind="tcp") if c.status == psutil.CONN_LISTEN}
            return ProcInfo(pid, p.name(), " ".join(p.cmdline()), ports)
        except (psutil.Error, OSError):
            return None

    def our_pid(self) -> int | None:
        """PID нашего движка, только если он проверенно наш."""
        pid = self._proc.pid if self._proc else None
        if pid is None:
            try:
                pid = int(self.pid_file.read_text(encoding="utf-8-sig").strip())
            except (OSError, ValueError):
                return None
        info = self._proc_info(pid)
        return pid if info and is_our_engine(info, self.port, frozenset(self.s.priority_ports)) else None

    def stop(self, timeout: float = 10.0) -> bool:
        """Остановить СВОЙ движок (вместе с его дочерними процессами модели). True, если остановлен."""
        import psutil
        self._require_lock()
        pid = self.our_pid()
        if pid is None:
            return not self.alive()
        try:
            parent = psutil.Process(pid)
            family = parent.children(recursive=True) + [parent]
            for p in family:
                p.terminate()
            _, rest = psutil.wait_procs(family, timeout=timeout)
            for p in rest:
                p.kill()
        except psutil.Error:
            pass
        self._proc = None
        return not self.alive()

    # ---------- модели ----------
    def unload_all(self) -> None:
        self._require_lock()
        for name in self.loaded():
            try:
                self._request("POST", "/api/generate", {"model": name, "keep_alive": 0}, timeout=30.0)
            except EngineError:
                # у моделей для поиска по смыслу нет generate
                self._request("POST", "/api/embed", {"model": name, "input": [], "keep_alive": 0}, timeout=30.0)

    def wait_vram_released(self, baseline_used_mb: int, tolerance_mb: int = 300, timeout: float = 30.0) -> float | None:
        """Ждать, пока наш движок пуст и видеопамять вернулась к уровню до загрузки.
        Возвращает секунды ожидания или None, если не дождались (тогда новые задачи запрещены)."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                empty = not self.loaded()
            except (OSError, EngineError, ValueError):
                empty = not self.alive()          # движок выключен = в нём ничего нет
            g = resources.gpu()
            if empty and g is not None and g.used_mb <= baseline_used_mb + tolerance_mb:
                return time.monotonic() - t0
            time.sleep(0.25)
        return None

    def embed(self, model: str, texts: list[str], keep_alive="5m") -> list[list[float]]:
        return self._request("POST", "/api/embed", {"model": model, "input": texts, "keep_alive": keep_alive},
                             timeout=300.0).get("embeddings", [])

    def chat_stream(self, model: str, messages: list[dict], options: dict | None = None, keep_alive="5m",
                    on_start=None, timeout: float = 600.0, fmt=None):
        """Генератор кусочков текста. on_start(Generation) получает ручку для мгновенной отмены.
        При отмене бросает Cancelled."""
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        gen = Generation(conn)
        if on_start:
            on_start(gen)
        body = {"model": model, "messages": messages, "stream": True, "think": False, "keep_alive": keep_alive,
                "options": options or {}}
        if fmt is not None:
            body["format"] = fmt                 # "json" или JSON-схема: ответ строго в этом виде
        try:
            conn.request("POST", "/api/chat", json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status >= 400:
                raise EngineError(f"/api/chat: HTTP {r.status} {r.read()[:200]!r}")
            while True:
                if gen.cancelled:
                    raise Cancelled()
                line = r.readline()
                if not line:
                    break
                part = json.loads(line)
                if part.get("error"):
                    raise EngineError(part["error"])
                text = (part.get("message") or {}).get("content", "")
                if text:
                    yield text
                if part.get("done"):
                    yield _Done(part)
                    break
        except (OSError, http.client.HTTPException, ValueError) as e:
            if gen.cancelled:
                raise Cancelled() from e
            raise
        finally:
            conn.close()
        if gen.cancelled:
            raise Cancelled()


class _Done(str):
    """Последний кусочек потока: пустая строка с итоговыми цифрами Ollama в .stats."""

    def __new__(cls, stats):
        obj = super().__new__(cls, "")
        obj.stats = stats
        return obj
