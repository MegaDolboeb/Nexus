"""Разбор лент RSS 2.0, RSS 1.0 (RDF) и Atom (в том числе arXiv) только стандартной библиотекой."""
from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

USER_AGENT = "NexusLocalResearch/0.1 (personal, non-commercial)"
MAX_BYTES = 5 * 1024 * 1024

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


@dataclass
class Entry:
    title: str
    url: str
    summary: str = ""
    published: float | None = None       # unix time
    guid: str = ""
    authors: list[str] = field(default_factory=list)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "li", "div"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(s: str) -> str:
    if not s:
        return ""
    p = _Text()
    try:
        p.feed(s)
        p.close()
        text = "".join(p.parts)
    except Exception:                      # noqa: BLE001 - кривой HTML: просто убрать теги
        text = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_date(s: str | None) -> float | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)                         # RSS: "Thu, 13 Nov 2026 10:00:00 +0300"
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))   # Atom: "2026-11-13T10:00:00Z"
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _t(el, path, ns=NS) -> str:
    """Весь текст элемента, включая вложенную разметку (Atom type="xhtml")."""
    x = el.find(path, ns)
    return "".join(x.itertext()).strip() if x is not None else ""


def parse_feed(data: bytes) -> list[Entry]:
    head = data[:500].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        raise ValueError("сайт отдал веб-страницу вместо ленты (возможно, проверка на робота)")
    root = ET.fromstring(data)
    tag = root.tag.lower()
    out: list[Entry] = []
    if tag.endswith("feed"):                                            # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate" and l.get("type", "text/html") in ("text/html", ""):
                    link = l.get("href", "")
                    break
            if not link:
                l = e.find("atom:link", NS)
                link = l.get("href", "") if l is not None else ""
            out.append(Entry(
                title=html_to_text(_t(e, "atom:title")), url=link.strip(),
                summary=html_to_text(_t(e, "atom:summary") or _t(e, "atom:content")),
                published=parse_date(_t(e, "atom:published") or _t(e, "atom:updated")),
                guid=_t(e, "atom:id"),
                authors=[_t(a, "atom:name") for a in e.findall("atom:author", NS) if _t(a, "atom:name")]))
    elif tag.endswith("rss"):                                           # RSS 2.0
        for i in root.iter("item"):
            out.append(Entry(
                title=html_to_text(_t(i, "title")), url=_t(i, "link"),
                summary=html_to_text(_t(i, "description") or _t(i, "content:encoded")),
                published=parse_date(_t(i, "pubDate") or _t(i, "dc:date")),
                guid=_t(i, "guid"),
                authors=[a for a in (_t(i, "author"), _t(i, "dc:creator")) if a]))
    elif tag.endswith("rdf"):                                           # RSS 1.0
        for i in root.findall("rss1:item", NS):
            out.append(Entry(
                title=html_to_text(_t(i, "rss1:title")), url=_t(i, "rss1:link"),
                summary=html_to_text(_t(i, "rss1:description") or _t(i, "content:encoded") or _t(i, "dc:description")),
                published=parse_date(_t(i, "dc:date")),
                guid=i.get(f"{{{NS['rdf']}}}about", ""),
                authors=[a for a in (_t(i, "dc:creator"),) if a]))
    else:
        raise ValueError(f"не лента: <{root.tag}>")
    return [e for e in out if e.url and e.title]


def fetch(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("ответ больше 5 МБ")
    return data
