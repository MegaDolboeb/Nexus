"""Секретный токен панели: чтобы чужая веб-страница не могла командовать Nexus через localhost
(ЗАДАНИЕ.md, раздел 9 и 11 — секреты отдельно от кода, не в git, не в логах)."""
from __future__ import annotations

import secrets as _secrets

from .. import config
from ..safety import writable

TOKEN_FILE = config.ROOT / "secrets" / "panel_token.txt"
_cached: dict[object, str] = {}          # один токен на всё время жизни процесса — не зависит от диска


def get_token(path=None) -> str:
    path = path or TOKEN_FILE
    if path in _cached:
        return _cached[path]
    p = writable(path)
    token = ""
    if p.exists():
        token = p.read_text(encoding="utf-8").strip()
    if not token:
        token = _secrets.token_hex(24)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(token, encoding="utf-8")
    _cached[path] = token
    return token
