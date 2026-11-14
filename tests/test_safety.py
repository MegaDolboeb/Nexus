from pathlib import Path

import pytest

from nexus import config
from nexus.safety import ForbiddenWrite, writable


def test_inside_nexus_allowed():
    assert writable(config.ROOT / "data" / "nexus.db") == (config.ROOT / "data" / "nexus.db").resolve()


@pytest.mark.parametrize("path", [
    Path.home() / "AppData" / "Roaming" / "RenPy" / "x",
    Path.home() / ".ollama" / "models" / "x",
    Path(r"C:\Games\SomeOtherApp\x"),
    Path(r"C:\Dev\x.txt"),
    config.ROOT / ".." / "x.txt",
])
def test_outside_nexus_forbidden(path):
    with pytest.raises(ForbiddenWrite):
        writable(path)
