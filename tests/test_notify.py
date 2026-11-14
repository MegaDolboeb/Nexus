"""Уведомления Windows через иконку в трее (раздел 10 задания) — не критично, если недоступны."""
import nexus.notify as notify


def test_send_without_icon_does_not_raise(monkeypatch):
    monkeypatch.setattr(notify, "_icon", None)
    notify.send("Заголовок", "Текст")   # просто не должно упасть


def test_send_calls_icon_notify(monkeypatch):
    calls = []

    class FakeIcon:
        def notify(self, message, title):
            calls.append((title, message))

    icon = FakeIcon()
    notify.set_icon(icon)
    try:
        notify.send("Заголовок", "Текст")
        assert calls == [("Заголовок", "Текст")]
    finally:
        notify.set_icon(None)


def test_send_swallows_icon_errors(monkeypatch):
    class BrokenIcon:
        def notify(self, message, title):
            raise RuntimeError("трей недоступен")

    notify.set_icon(BrokenIcon())
    try:
        notify.send("Заголовок", "Текст")   # не должно упасть наружу
    finally:
        notify.set_icon(None)
