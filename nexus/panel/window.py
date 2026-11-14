"""Окно программы (pywebview) и иконка в трее (ЗАДАНИЕ.md, раздел 9: «открыть панель, пауза, выход»).

Это настоящее окно Windows, а не веб-страница — автоматически его открытие, сворачивание в трей
и работу «Выхода» я проверить не могу. Это делает только Давид на своём компьютере.
"""
from __future__ import annotations

import logging
import pathlib
import threading

log = logging.getLogger("nexus.panel.window")

ICON_PATH = pathlib.Path(__file__).resolve().parent / "icon.png"


def make_icon_image():
    """Иконка трея и окна: та же синяя бесконечность, что и .ico сборки (packaging/make_icon.py)."""
    from PIL import Image
    return Image.open(ICON_PATH)


class ServerThread(threading.Thread):
    """Свой сервер в отдельном потоке: pywebview на Windows должен занимать главный поток."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8777):
        super().__init__(daemon=True, name="nexus-panel-server")
        import uvicorn
        from .server import app
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


def make_tray(on_open, on_quit):
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("Открыть панель", on_open, default=True),
        pystray.MenuItem("Пауза (пока не подключена)", None, enabled=False),
        pystray.MenuItem("Выход", on_quit),
    )
    return pystray.Icon("nexus", make_icon_image(), "Nexus", menu)


def run(host: str = "127.0.0.1", port: int = 8777) -> None:
    import webview
    from .server import url_for_launch

    server = ServerThread(host, port)
    server.start()

    window = webview.create_window("Nexus", url_for_launch(host, port), width=1280, height=860,
                                   min_size=(960, 640), background_color="#0B1322")

    state = {"exiting": False}

    def on_closing():
        """Закрытие окна крестиком сворачивает в трей, а не выключает Nexus (раздел 9)."""
        if state["exiting"]:
            return None
        window.hide()
        return False

    window.events.closing += on_closing

    def show_panel(icon=None, item=None) -> None:
        window.show()

    tray_holder: dict = {}

    def quit_app(icon=None, item=None) -> None:
        state["exiting"] = True
        t = tray_holder.get("tray")
        if t is not None:
            t.stop()
        server.stop()
        window.destroy()

    tray = make_tray(show_panel, quit_app)
    tray_holder["tray"] = tray
    from .. import notify
    notify.set_icon(tray)
    threading.Thread(target=tray.run, daemon=True, name="nexus-tray").start()

    try:
        webview.start()
    finally:
        server.stop()
