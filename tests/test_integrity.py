"""«Замок с сигнализацией» для защищённого кода."""
import nexus.integrity as integrity


def test_no_lock_file_means_nothing_to_report(tmp_path, monkeypatch):
    monkeypatch.setattr(integrity, "LOCK_FILE", tmp_path / "no-such-file.json")
    assert integrity.check() == []


def test_write_lock_then_check_matches(tmp_path, monkeypatch):
    from nexus import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(integrity, "LOCK_FILE", tmp_path / "config" / "integrity.lock.json")
    for rel in integrity.PROTECTED_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("оригинал", encoding="utf-8")
    integrity.write_lock()
    assert integrity.check() == []


def test_check_reports_tampered_file(tmp_path, monkeypatch):
    from nexus import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(integrity, "LOCK_FILE", tmp_path / "config" / "integrity.lock.json")
    for rel in integrity.PROTECTED_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("оригинал", encoding="utf-8")
    integrity.write_lock()
    tampered = tmp_path / integrity.PROTECTED_FILES[1]
    tampered.write_text("подмена, занятость больше не проверяем", encoding="utf-8")
    changed = integrity.check()
    assert changed == [integrity.PROTECTED_FILES[1]]


def test_check_skips_everything_when_frozen(tmp_path, monkeypatch):
    """Собранный .exe: исходники упакованы, сверять нечем — не пугаем ложной тревогой."""
    import sys
    from nexus import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(integrity, "LOCK_FILE", tmp_path / "config" / "integrity.lock.json")
    for rel in integrity.PROTECTED_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("оригинал", encoding="utf-8")
    integrity.write_lock()
    (tmp_path / integrity.PROTECTED_FILES[0]).write_text("подмена", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert integrity.check() == []


def test_check_reports_missing_file(tmp_path, monkeypatch):
    from nexus import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(integrity, "LOCK_FILE", tmp_path / "config" / "integrity.lock.json")
    for rel in integrity.PROTECTED_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("оригинал", encoding="utf-8")
    integrity.write_lock()
    (tmp_path / integrity.PROTECTED_FILES[0]).unlink()
    assert integrity.PROTECTED_FILES[0] in integrity.check()
