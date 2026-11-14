"""Тесты того, что можно проверить без настоящего окна Windows: иконку и структуру меню трея.
Само окно (pywebview) и то, что оно правда открывается, сворачивается в трей и закрывается
«Выходом», — можно проверить только руками, на компьютере Давида."""
import pytest

from nexus.panel.window import ServerThread, make_icon_image, make_tray


def test_icon_is_correct_size_and_not_empty():
    img = make_icon_image()
    assert img.size == (128, 128)
    assert img.getpixel((64, 64))[3] > 0           # центр фигуры (бесконечность) непрозрачен
    assert img.getpixel((0, 0))[3] == 0            # угол за пределами фигуры прозрачен


def test_tray_menu_has_open_pause_and_quit():
    calls = []
    tray = make_tray(lambda *a: calls.append("open"), lambda *a: calls.append("quit"))
    items = list(tray.menu)
    titles = [str(i) for i in items]
    assert any("Открыть панель" in t for t in titles)
    assert any("Выход" in t for t in titles)
    pause = next(i for i in items if "Пауза" in str(i))
    assert not pause.enabled                        # честно неактивна, не притворяется рабочей


def test_tray_open_item_calls_handler():
    calls = []
    tray = make_tray(lambda *a: calls.append("open"), lambda *a: calls.append("quit"))
    open_item = next(i for i in tray.menu if "Открыть" in str(i))
    open_item(tray)
    assert calls == ["open"]


def test_server_thread_stop_sets_flag(tmp_path, monkeypatch):
    import nexus.safety as safety
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    monkeypatch.setattr("nexus.panel.token.TOKEN_FILE", tmp_path / "secrets" / "panel_token.txt")
    t = ServerThread(port=8778)
    assert t.server.should_exit in (False, None)
    t.stop()
    assert t.server.should_exit is True
