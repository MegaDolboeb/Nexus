import sqlite3
import time

import pytest

from nexus import backup


@pytest.fixture
def layout(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    db_path = tmp_path / "nexus.db"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE t(x)")
    db.execute("INSERT INTO t VALUES (1)")
    db.commit()
    db.close()
    personal = tmp_path / "personal"
    personal.mkdir()
    (personal / "interests.json").write_text("{}", encoding="utf-8")
    return tmp_path, db_path, personal


def test_backup_now_copies_db_and_personal(layout):
    tmp_path, db_path, personal = layout
    out = backup.backup_now(db_path, personal, tmp_path / "backups")
    assert (out / "nexus.db").exists() and (out / "interests.json").exists()
    copy = sqlite3.connect(out / "nexus.db")
    assert copy.execute("SELECT x FROM t").fetchone() == (1,)


def test_backup_now_missing_db_does_not_crash(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    out = backup.backup_now(tmp_path / "no.db", tmp_path / "no-personal", tmp_path / "backups")
    assert out.exists() and not (out / "nexus.db").exists()


def test_due_is_false_right_after_backup(layout):
    tmp_path, db_path, personal = layout
    root = tmp_path / "backups"
    assert backup.due(root)
    backup.backup_now(db_path, personal, root)
    assert not backup.due(root)


def test_prune_keeps_only_recent_days(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    root = tmp_path / "backups"
    root.mkdir()
    days = [f"2026-01-{i:02d}" for i in range(1, 20)]
    for d in days:
        (root / d).mkdir()
    backup._prune(root, keep=5)
    left = sorted(p.name for p in root.iterdir())
    assert left == days[-5:]
