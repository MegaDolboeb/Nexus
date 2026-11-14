import json
from pathlib import Path

import pytest

from nexus import config
from nexus.priority_watch import BUSY, FREE, UNKNOWN, PriorityWatch, Proc

NOW = 1_800_000_000.0


class FakeProbe:
    def __init__(self, procs=(), ports=(), status=None, status_errors=0, proc_error=None, port_error=None):
        self.procs = list(procs)
        self.ports = set(ports)
        self.status = status
        self.status_errors = status_errors
        self.proc_error = proc_error
        self.port_error = port_error
        self.slept = 0.0

    def processes(self):
        if self.proc_error:
            raise self.proc_error
        return self.procs

    def listening_ports(self):
        if self.port_error:
            raise self.port_error
        return self.ports

    def read_text(self, path):
        if self.status_errors > 0:
            self.status_errors -= 1
            raise OSError("заменяется")
        if self.status is None:
            raise FileNotFoundError(path)
        return json.dumps(self.status)

    def now(self):
        return NOW

    def sleep(self, s):
        self.slept += s


def status(state, age=5.0):
    return {"state": state, "updated": NOW - age}


def watch(**overrides):
    s = config.Settings(priority_name="Companion", priority_processes=("app.exe",),
                        priority_ports=(11111,), **overrides)
    return s


def test_disabled_when_name_empty():
    s = config.Settings(priority_name="", priority_processes=("app.exe",))
    o = PriorityWatch(FakeProbe(procs=[Proc("app.exe", "")]), s).check()
    assert o.state == FREE and o.busy == []     # имя пустое — функция выключена, процесс не важен


def test_all_quiet_is_free():
    o = PriorityWatch(FakeProbe(), watch()).check()
    assert o.state == FREE


def test_configured_process_running_is_busy():
    o = PriorityWatch(FakeProbe(procs=[Proc("app.exe", "")]), watch()).check()
    assert o.state == BUSY and any("app.exe" in r for r in o.busy)


def test_other_process_running_is_still_free():
    o = PriorityWatch(FakeProbe(procs=[Proc("unrelated.exe", "")]), watch()).check()
    assert o.state == FREE


def test_configured_port_busy_is_busy():
    o = PriorityWatch(FakeProbe(ports=[11111]), watch()).check()
    assert o.state == BUSY and any("11111" in r for r in o.busy)


def test_process_list_error_is_unknown():
    o = PriorityWatch(FakeProbe(proc_error=PermissionError()), watch()).check()
    assert o.state == UNKNOWN


def test_port_list_error_is_unknown():
    o = PriorityWatch(FakeProbe(port_error=TimeoutError()), watch()).check()
    assert o.state == UNKNOWN


def test_busy_wins_over_unknown():
    o = PriorityWatch(FakeProbe(procs=[Proc("app.exe", "")], proc_error=None, port_error=TimeoutError()),
                      watch()).check()
    assert o.state == BUSY and o.unknown


def test_status_file_idle_fresh_is_free():
    s = watch(priority_status_file="status.json")
    o = PriorityWatch(FakeProbe(status=status("idle")), s).check()
    assert o.state == FREE


@pytest.mark.parametrize("state", ["thinking", "busy", "something new", None])
def test_status_file_not_free_value_is_busy(state):
    s = watch(priority_status_file="status.json")
    o = PriorityWatch(FakeProbe(status=status(state)), s).check()
    assert o.state == BUSY


def test_status_file_stale_is_unknown():
    s = watch(priority_status_file="status.json")
    o = PriorityWatch(FakeProbe(status=status("idle", age=181)), s).check()
    assert o.state == UNKNOWN


def test_status_file_missing_is_unknown():
    s = watch(priority_status_file="status.json")
    o = PriorityWatch(FakeProbe(status=None), s).check()
    assert o.state == UNKNOWN


def test_status_file_retried_once_after_a_second():
    probe = FakeProbe(status=status("idle"), status_errors=1)
    s = watch(priority_status_file="status.json")
    assert PriorityWatch(probe, s).check().state == FREE
    assert probe.slept == 1.0


def test_status_file_ignored_when_not_configured():
    o = PriorityWatch(FakeProbe(status=status("thinking")), watch()).check()
    assert o.state == FREE


def test_custom_free_values_respected():
    s = watch(priority_status_file="status.json", priority_status_free_values=("resting", "asleep"))
    assert PriorityWatch(FakeProbe(status=status("resting")), s).check().state == FREE
    assert PriorityWatch(FakeProbe(status=status("idle")), s).check().state == BUSY


def test_watch_source_has_no_writes_or_kills():
    src = Path(config.ROOT, "nexus", "priority_watch.py").read_text(encoding="utf-8")
    for bad in ('"w"', "'w'", '"a"', "'a'", "unlink", "remove(", "rmtree", "kill", "terminate", "os.replace", "subprocess"):
        assert bad not in src, bad
