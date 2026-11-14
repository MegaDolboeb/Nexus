import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from nexus import config
from nexus.engine import Cancelled, Engine, EngineBusy, EngineError, EngineLock, ProcInfo, is_our_engine


class FakeOllama(BaseHTTPRequestHandler):
    models = ["qwen3.5:4b"]
    calls: list = []
    embed_only = set()

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    pull_error = ""

    def do_GET(self):
        if self.path == "/api/version":
            self._json(200, {"version": "fake"})
        elif self.path == "/api/ps":
            self._json(200, {"models": [{"name": m} for m in self.models]})
        elif self.path == "/api/tags":
            self._json(200, {"models": [{"name": m} for m in self.models]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.calls.append((self.path, body))
        if self.path == "/api/generate":
            if body["model"] in self.embed_only:
                return self._json(400, {"error": "does not support generate"})
            self._json(200, {"done": True})
        elif self.path == "/api/embed":
            self._json(200, {"embeddings": []})
        elif self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            if self.pull_error:
                self.wfile.write(json.dumps({"error": self.pull_error}).encode() + b"\n")
            else:
                self.wfile.write(json.dumps({"status": "pulling"}).encode() + b"\n")
                self.wfile.write(json.dumps({"status": "success"}).encode() + b"\n")
        elif self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            try:
                for i in range(body["options"].get("parts", 3)):
                    self.wfile.write(json.dumps({"message": {"content": f"p{i} "}, "done": False}).encode() + b"\n")
                    self.wfile.flush()
                    time.sleep(body["options"].get("delay", 0.0))
                self.wfile.write(json.dumps({"done": True, "eval_count": 3}).encode() + b"\n")
            except OSError:
                pass


@pytest.fixture
def engine():
    FakeOllama.calls = []
    FakeOllama.models = ["qwen3.5:4b"]
    FakeOllama.embed_only = set()
    FakeOllama.pull_error = ""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield Engine(config.Settings(engine_port=srv.server_address[1]))
    srv.shutdown()


def test_alive_and_loaded(engine):
    assert engine.alive()
    assert engine.loaded() == ["qwen3.5:4b"]


def test_not_alive_when_nothing_listens():
    assert not Engine(config.Settings(engine_port=1)).alive()


@pytest.mark.parametrize("port", [11434, 11435])
def test_engine_refuses_priority_ports(port):
    with pytest.raises(EngineError):
        Engine(config.Settings(engine_port=port, priority_ports=(11434, 11435)))


def test_stream_gives_text_and_stats(engine):
    parts = list(engine.chat_stream("m", [], {"parts": 3}))
    assert "".join(parts) == "p0 p1 p2 "
    assert parts[-1].stats["eval_count"] == 3


def test_list_models_reads_tags(engine):
    assert engine.list_models() == ["qwen3.5:4b"]


def test_pull_refuses_when_lock_set_but_not_held(engine, tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    engine.lock = EngineLock(tmp_path / "e.lock")      # замок задан, но не взят (как в start/stop)
    with pytest.raises(EngineBusy):
        engine.pull("qwen3.5:9b")


def test_pull_succeeds_with_lock(engine, tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    engine.lock = EngineLock(tmp_path / "e.lock").acquire()
    try:
        engine.pull("qwen3.5:9b")    # не бросило исключение — успех
    finally:
        engine.lock.release()


def test_pull_raises_on_stream_error(engine, tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    FakeOllama.pull_error = "модель не найдена"
    engine.lock = EngineLock(tmp_path / "e.lock").acquire()
    try:
        with pytest.raises(EngineError, match="не найдена"):
            engine.pull("нет-такой-модели")
    finally:
        engine.lock.release()


def test_cancel_from_other_thread_is_fast(engine):
    handle = {}
    got = []
    t0 = time.monotonic()
    threading.Timer(0.3, lambda: handle["g"].cancel()).start()
    with pytest.raises(Cancelled):
        for p in engine.chat_stream("m", [], {"parts": 100, "delay": 0.1}, on_start=lambda g: handle.setdefault("g", g)):
            got.append(p)
    assert time.monotonic() - t0 < 1.5
    assert 0 < len(got) < 100


def test_unload_all_uses_keep_alive_zero(engine):
    engine.unload_all()
    assert ("/api/generate", {"model": "qwen3.5:4b", "keep_alive": 0}) in FakeOllama.calls


def test_unload_embedding_model_falls_back_to_embed(engine):
    FakeOllama.models = ["bge-m3"]
    FakeOllama.embed_only = {"bge-m3"}
    engine.unload_all()
    assert FakeOllama.calls[-1] == ("/api/embed", {"model": "bge-m3", "input": [], "keep_alive": 0})


@pytest.mark.parametrize("info,excluded,ok", [
    (ProcInfo(1, "ollama.exe", "ollama.exe serve", {11436}), frozenset(), True),
    (ProcInfo(1, "ollama.exe", "ollama.exe serve", {11434}), frozenset(), False),
    (ProcInfo(1, "ollama.exe", "ollama.exe serve", {11436, 11435}), frozenset({11435}), False),  # слушает чужой порт
    (ProcInfo(1, "ollama.exe", "ollama.exe runner", {11436}), frozenset(), False),
    (ProcInfo(1, "python.exe", "python serve", {11436}), frozenset(), False),
    (ProcInfo(1, "ollama.exe", "ollama.exe serve", set()), frozenset(), False),
])
def test_is_our_engine(info, excluded, ok):
    assert is_our_engine(info, 11436, excluded) is ok


def test_engine_lock_only_one_owner(tmp_path, monkeypatch):
    import nexus.safety as safety
    from nexus.engine import EngineBusy, EngineLock
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    a = EngineLock(tmp_path / "e.lock").acquire()
    with pytest.raises(EngineBusy):
        EngineLock(tmp_path / "e.lock").acquire()
    a.release()
    b = EngineLock(tmp_path / "e.lock").acquire()      # после освобождения — можно
    b.release()


def test_start_prefers_bundled_ollama_over_path(tmp_path, monkeypatch):
    import nexus.safety as safety
    from nexus.engine import EngineLock
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    bundled_dir = tmp_path / "ollama"
    bundled_dir.mkdir()
    (bundled_dir / "ollama.exe").write_bytes(b"")
    monkeypatch.setattr("shutil.which", lambda name: r"C:\somewhere\ollama.exe")

    captured = {}

    class FakePopen:
        def __init__(self, args, **kw):
            captured["exe"] = args[0]
            self.pid = 123

        def poll(self):
            return None

    monkeypatch.setattr("subprocess.Popen", FakePopen)
    eng = Engine(config.Settings(), models_dir=tmp_path / "models")
    eng.lock = EngineLock(tmp_path / "e.lock").acquire()
    alive_calls = {"n": 0}

    def fake_alive():
        alive_calls["n"] += 1
        return alive_calls["n"] > 1       # первый раз «ещё не запущен», со второго — «уже отвечает»
    monkeypatch.setattr(eng, "alive", fake_alive)
    try:
        eng.start()
    finally:
        eng.lock.release()
    assert captured["exe"] == str(bundled_dir / "ollama.exe")


def test_engine_without_lock_refuses_start_and_stop(engine, tmp_path, monkeypatch):
    import nexus.safety as safety
    from nexus.engine import EngineBusy, EngineLock
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    engine.lock = EngineLock(tmp_path / "e.lock")      # замок задан, но не взят
    for action in (engine.start, engine.stop, engine.unload_all):
        with pytest.raises(EngineBusy):
            action()


def test_is_our_engine_never_for_excluded_port():
    assert not is_our_engine(ProcInfo(1, "ollama.exe", "ollama.exe serve", {11435}), 11435,
                             excluded_ports=frozenset({11435}))
