"""Данные для панели: читает то же, чем пользуется сам Nexus, и умеет сохранять личные настройки
(расписание, пресет исследования, свой стиль, темы) — всё через config/safety, никогда мимо них."""
from __future__ import annotations

import json
import time

from .. import config
from ..engine import Engine
from ..priority_watch import PriorityWatch
from ..memory.store import MemoryStore
from ..research.match import load_all_topics, load_topics
from ..safety import writable
from ..sources.collector import load_sources
from ..sources.store import ItemStore
from . import i18n
from .runtime import get_runtime
from ..tasks import RUNNING, TaskStore

RECENT_LIMIT = 6
TOPIC_LIMIT = 8

STATUS_COLOR = {
    "ПОДТВЕРЖДЕНО": "ok",
    "ЧАСТИЧНО": "warn",
    "НЕ ПРОВЕРЕНО": "muted",
    "ОСПАРИВАЕТСЯ": "bad",
}


def priority_status() -> dict:
    """Текст для панели. Если приоритетная программа не настроена (Settings.priority_name пуст) —
    отдельное состояние, не «занята»/«свободна», а «никого не защищаем»."""
    s = config.load_settings()
    if not s.priority_name:
        return {"state": "NOT_CONFIGURED", "name": i18n.t("priority.default_title"),
               "text": i18n.t("priority.not_configured"), "may_work": True, "reasons": []}
    o = PriorityWatch(settings=s).check()
    if o.state == "FREE":
        text = i18n.t("priority.free", name=s.priority_name)
    elif o.state == "BUSY":
        text = i18n.t("priority.busy", name=s.priority_name)
    else:
        text = i18n.t("priority.unknown", name=s.priority_name)
    return {"state": o.state, "name": s.priority_name, "text": text, "may_work": o.may_work,
           "reasons": o.busy + o.unknown}


def engine_status() -> dict:
    """Не ходит в сеть сама: если есть общий Runtime, берёт его уже готовую проверку
    (обновляется раз в отрезок в фоне). Иначе — прямая проверка, как раньше (для тестов
    и для случая, когда Runtime недоступен)."""
    s = config.Settings()
    rt = get_runtime()
    if hasattr(rt, "engine_alive_cached"):
        return {"alive": rt.engine_alive_cached, "model": s.work_model}
    try:
        alive = Engine(s).alive()
    except Exception:                                   # noqa: BLE001 - панель не должна падать из-за движка
        alive = False
    return {"alive": alive, "model": s.work_model}


ACTIVITY_KIND_KEY = {
    "probe": "activity.kind.probe", "errand": "activity.kind.errand",
    "source_review": "activity.kind.source_review", "triage": "activity.kind.triage",
    "digest": "activity.kind.digest", "credibility": "activity.kind.credibility",
    "overview": "activity.kind.overview", "memory": "activity.kind.memory",
    "pull_model": "activity.kind.pull_model",
}
ACTIVITY_STATE_KEY = {s: f"activity.state.{s}" for s in
                      ("QUEUED", "RUNNING", "PAUSED", "INTERRUPTED", "COMPLETED", "FAILED", "CANCELLED")}
ACTIVITY_STATE_COLOR = {"COMPLETED": "ok", "FAILED": "bad", "CANCELLED": "bad", "RUNNING": "warn",
                        "QUEUED": "muted", "PAUSED": "muted", "INTERRUPTED": "muted"}


def activity_log(limit: int = 150) -> list[dict]:
    """Журнал переходов задач — честная прозрачность того, что Nexus делал (раздел 11 задания)."""
    store = TaskStore()
    out = []
    for e in store.recent_events(limit):
        out.append({
            "when": time.strftime("%d.%m %H:%M:%S", time.localtime(e["at"])),
            "kind": i18n.t(ACTIVITY_KIND_KEY.get(e["kind"], "")) or e["kind"],
            "title": e["title"],
            "state": i18n.t(ACTIVITY_STATE_KEY.get(e["to_state"], "")) or e["to_state"],
            "state_color": ACTIVITY_STATE_COLOR.get(e["to_state"], "muted"),
            "reason": e["reason"],
            "task_id": e["task_id"],
        })
    return out


def task_summary() -> dict:
    tasks = TaskStore().all()
    return {"running": sum(1 for t in tasks if t.state == RUNNING), "total": len(tasks)}


def topics_with_counts(limit: int = TOPIC_LIMIT) -> list[dict]:
    items = ItemStore()
    counts = items.counts_by_topic()
    topics = sorted(load_topics(), key=lambda t: (t.priority, -counts.get(t.id, 0)))[:limit]
    return [{"id": t.id, "name": t.name, "count": counts.get(t.id, 0)} for t in topics]


def recent_reports(limit: int = RECENT_LIMIT) -> list[dict]:
    items = ItemStore()
    names = {s.id: s.name for s in load_sources()}         # человеку — название источника, не его внутренний id
    out = []
    for r in items.reports(limit=limit):
        cred = items.credibility_of(r["item_id"])
        status = cred["status"] if cred else None
        out.append({
            "id": r["item_id"], "title": r["title"], "url": r["url"],
            "source": names.get(r["source_id"], r["source_id"]),
            "status": i18n.status_label(status),
            "status_color": STATUS_COLOR.get(status, "muted"),
            "low_reliability": bool(cred and cred["low_reliability"]),
            "when": time.strftime("%d.%m %H:%M", time.localtime(r["at"])),
        })
    return out


def control_status() -> dict:
    rt = get_runtime()
    reason = getattr(rt, "reason", "") or getattr(rt, "last_error", "")
    return {"state": rt.state, "label": i18n.control_label(rt.state), "reason": reason}


def home_snapshot() -> dict:
    return {
        "priority": priority_status(),
        "engine": engine_status(),
        "tasks": task_summary(),
        "topics": topics_with_counts(),
        "recent": recent_reports(),
        "control": control_status(),
        "has_priority_photo": bool(priority_photo_path()),
        "generated": time.strftime("%H:%M:%S"),
    }


def _day_range(date_str: str) -> tuple[float, float]:
    """YYYY-MM-DD (локальный день Давида) -> (начало, конец) unix-времени."""
    d = time.strptime(date_str, "%Y-%m-%d")
    start = time.mktime(d)
    return start, start + 24 * 3600


def research_feed(topic_id: str | None = None, limit: int = 200, date: str | None = None) -> list[dict]:
    items = ItemStore()
    names = {s.id: s.name for s in load_sources()}
    topic_names = {t.id: t.name for t in load_topics()}
    since, until = (None, None)
    if date:
        try:
            since, until = _day_range(date)
        except ValueError:
            pass
    out = []
    for r in items.reports(topic_id=topic_id, limit=limit, since=since, until=until):
        cred = items.credibility_of(r["item_id"])
        status = cred["status"] if cred else None
        out.append({
            "id": r["item_id"], "title": r["title"], "url": r["url"], "text": r["text"],
            "source": names.get(r["source_id"], r["source_id"]),
            "topic": topic_names.get(r["topic_id"], r["topic_id"]),
            "status": i18n.status_label(status),
            "status_color": STATUS_COLOR.get(status, "muted"),
            "reason": cred["reason"] if cred else "",
            "low_reliability": bool(cred and cred["low_reliability"]),
            "when": time.strftime("%d.%m %H:%M", time.localtime(r["at"])),
            "day": time.strftime("%Y-%m-%d", time.localtime(r["at"])),
            "day_label": time.strftime("%d.%m.%Y", time.localtime(r["at"])),
        })
    return out


def group_by_day(items: list[dict]) -> list[dict]:
    """Материалы уже отсортированы по времени (новые сверху) — просто режем на дни подряд идущими."""
    groups: list[dict] = []
    for it in items:
        if groups and groups[-1]["day"] == it["day"]:
            groups[-1]["materials"].append(it)
        else:
            groups.append({"day": it["day"], "label": it["day_label"], "materials": [it]})
    return groups


def material_detail(item_id: int) -> dict | None:
    """Полная страница одного материала — не источник, а то, что про него решил и написал Nexus."""
    items = ItemStore()
    try:
        it = items.item(item_id)
    except KeyError:
        return None
    report = items.report(item_id)
    cred = items.credibility_of(item_id)
    status = cred["status"] if cred else None
    names = {s.id: s.name for s in load_sources()}
    topic_names = {t.id: t.name for t in load_topics()}
    return {
        "id": item_id, "title": it["title"], "url": it["url"], "state": it["state"],
        "source": names.get(it["source_id"], it["source_id"]),
        "topic": topic_names.get(report["topic_id"], report["topic_id"]) if report else "",
        "text": report["text"] if report else "",
        "status": i18n.status_label(status),
        "status_color": STATUS_COLOR.get(status, "muted"),
        "reason": cred["reason"] if cred else "",
        "low_reliability": bool(cred and cred["low_reliability"]),
        "memory_id": MemoryStore().item_memory_id(item_id),
        "when": time.strftime("%d.%m %H:%M", time.localtime(report["at"])) if report else "",
    }


def memory_detail(memory_id: int) -> dict | None:
    """Полная карточка темы памяти: выводы целиком, история изменений, из каких материалов собрана."""
    store = MemoryStore()
    try:
        t = store.get(memory_id)
    except KeyError:
        return None
    topic_names = {tp.id: tp.name for tp in load_topics()}
    hist = [{"at": time.strftime("%d.%m %H:%M", time.localtime(h[0])), "reason": h[3]} for h in store.history(memory_id)]
    return {
        "id": t.id, "title": t.title, "conclusions": t.conclusions, "report": t.report,
        "topic": topic_names.get(t.interest_topic_id, t.interest_topic_id),
        "status": i18n.status_label(t.credibility_status),
        "status_color": STATUS_COLOR.get(t.credibility_status, "muted"),
        "low_reliability": t.low_reliability, "links": t.links, "related": t.related,
        "updated": time.strftime("%d.%m %H:%M", time.localtime(t.updated)), "history": hist,
    }


def interests_overview() -> list[dict]:
    items = ItemStore()
    counts = items.counts_by_topic()
    all_counts = items.counts_by_topic(("MATCHED", "SELECTED", "DIGESTED"))
    out = []
    for t in sorted(load_topics(), key=lambda t: t.priority):
        out.append({"id": t.id, "name": t.name, "priority": t.priority, "about": t.about,
                    "how_to_present": t.how_to_present, "new_count": counts.get(t.id, 0),
                    "total_count": all_counts.get(t.id, 0)})
    return out


def memory_overview(query: str = "", limit: int = 40) -> list[dict]:
    store = MemoryStore()
    topic_names = {t.id: t.name for t in load_topics()}
    rows = store.search_text(query, limit=limit) if query.strip() else store.all(limit=limit)
    out = []
    for t in rows:
        out.append({
            "id": t.id, "title": t.title, "gist": t.gist,
            "topic": topic_names.get(t.interest_topic_id, t.interest_topic_id),
            "status": i18n.status_label(t.credibility_status),
            "status_color": STATUS_COLOR.get(t.credibility_status, "muted"),
            "low_reliability": t.low_reliability,
            "sources_count": len(t.links), "related_count": len(t.related),
            "updated": time.strftime("%d.%m %H:%M", time.localtime(t.updated)),
        })
    return out


def sources_overview() -> list[dict]:
    items = ItemStore()
    out = []
    for s in load_sources():
        st = items.status(s.id)
        out.append({
            "id": s.id, "name": s.name, "lang": s.lang, "reliability": s.reliability,
            "note": s.note, "primary": s.primary, "ok": st.ok,
            "last_ok": time.strftime("%d.%m %H:%M", time.localtime(st.last_ok)) if st.last_ok else "",
            "error": st.error if not st.ok else "", "count": items.count(s.id),
        })
    return out


def settings_overview() -> dict:
    s = config.load_settings()                                    # то, что реально сейчас действует
    return {
        "work_model": s.work_model, "cpu_model": s.cpu_model, "embed_model": s.embed_model,
        "segment_min": round(s.segment_s / 60, 1), "rest_min": round(s.rest_s / 60, 1),
        "after_priority_min": round(s.after_priority_s / 60, 1),
        "min_free_ram_gb": s.min_free_ram_gb,
        "research_mode": s.research_mode, "custom_instruction": s.custom_instruction,
        "research_modes": [{"id": k, "name": i18n.t(f"mode.{k}")} for k in config.RESEARCH_MODES],
        "has_priority_photo": bool(priority_photo_path()),
        "language": s.language,
        "languages": [{"id": k, "name": v} for k, v in config.LANGUAGES.items()],
        "extra_pause_programs": list(s.extra_pause_programs),
        "games": s.games,
        "priority_name": s.priority_name,
        "priority_processes": ", ".join(s.priority_processes),
        "priority_ports": ", ".join(str(p) for p in s.priority_ports),
        "priority_status_file": s.priority_status_file,
        "priority_vram_mb": s.priority_vram_mb, "priority_ram_gb": s.priority_ram_gb,
    }


def save_extra_pause_programs(programs: list) -> None:
    """Свои программы (помимо встроенного списка игр) — во время них Nexus тоже на паузе."""
    cleaned = sorted({str(p).strip().lower() for p in programs if str(p).strip()})[:50]
    config.save_settings_overrides({"extra_pause_programs": cleaned})


def save_priority_settings(name: str, processes: str, ports: str, status_file: str,
                           vram_mb: float = 0, ram_gb: float = 0) -> None:
    """Приоритетная программа: настраивается полностью, пустое имя = функция выключена."""
    proc_list = sorted({p.strip().lower() for p in processes.split(",") if p.strip()})
    port_list = sorted({int(p.strip()) for p in ports.split(",") if p.strip().lstrip("-").isdigit()})
    config.save_settings_overrides({
        "priority_name": name.strip()[:80],
        "priority_processes": proc_list,
        "priority_ports": port_list,
        "priority_status_file": status_file.strip(),
        "priority_vram_mb": max(0, int(vram_mb)),
        "priority_ram_gb": max(0.0, float(ram_gb)),
    })


ALLOWED_PHOTO_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024


def priority_photo_path():
    """(путь, mime) выбранного фото, если файл на месте — иначе None."""
    s = config.load_settings()
    if not s.priority_photo:
        return None
    p = config.PERSONAL_DIR / s.priority_photo
    return (p, s.priority_photo_mime) if p.exists() else None


def save_priority_photo(data_url: str) -> None:
    """data_url — то, что браузер отдаёт из <input type=file> (data:image/...;base64,...).
    Картинку выбирает сам человек, случайные не скачиваются."""
    import base64
    import re
    m = re.match(r"^data:(image/[\w.+-]+);base64,(.+)$", data_url, re.S)
    if not m:
        raise ValueError("непонятный формат файла")
    mime = m.group(1)
    ext = ALLOWED_PHOTO_MIME.get(mime)
    if not ext:
        raise ValueError("нужна картинка: PNG, JPEG или WEBP")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception as e:                                          # noqa: BLE001
        raise ValueError("не удалось прочитать файл") from e
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValueError("файл больше 8 МБ")
    rel = f"assets/priority.{ext}"
    target = writable(config.PERSONAL_DIR / rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    config.save_settings_overrides({"priority_photo": rel, "priority_photo_mime": mime})


def save_settings(segment_min: float, rest_min: float, after_priority_min: float, research_mode: str,
                  custom_instruction: str, language: str = "ru", work_model: str = "", cpu_model: str = "",
                  embed_model: str = "") -> None:
    if research_mode not in config.RESEARCH_MODES:
        raise ValueError(f"неизвестный пресет: {research_mode}")
    if language not in config.LANGUAGES:
        raise ValueError(f"неизвестный язык: {language}")
    overrides = {
        "segment_min": max(1.0, float(segment_min)), "rest_min": max(0.5, float(rest_min)),
        "after_priority_min": max(0.0, float(after_priority_min)), "research_mode": research_mode,
        "custom_instruction": str(custom_instruction).strip()[:500], "language": language,
    }
    if work_model.strip():
        overrides["work_model"] = work_model.strip()
    if cpu_model.strip():
        overrides["cpu_model"] = cpu_model.strip()
    if embed_model.strip():
        overrides["embed_model"] = embed_model.strip()
    config.save_settings_overrides(overrides)


def available_models() -> dict:
    """Что уже скачано в папку Nexus — движок должен быть запущен, иначе честно говорим, что недоступно."""
    try:
        s = config.load_settings()
        return {"available": True, "models": Engine(s).list_models()}
    except Exception:                                           # noqa: BLE001 - список необязателен
        return {"available": False, "models": []}


ALLOWED_RELIABILITY = {"high", "medium", "low"}


def add_source(source_id: str, name: str, url: str, note: str = "", reliability: str = "medium") -> None:
    """Добавляет источник (RSS), который предложил Давид — решение его, модель только подсказала
    (раздел 10 задания: «нейросеть проверяет и говорит, хороший это источник или нет»)."""
    import re
    clean_id = re.sub(r"[^a-z0-9_-]", "", source_id.strip().lower())[:40]
    if not clean_id:
        raise ValueError("нужен короткий идентификатор источника (латиница/цифры)")
    if not url.strip():
        raise ValueError("нужна ссылка на ленту")
    if reliability not in ALLOWED_RELIABILITY:
        reliability = "medium"
    path = config.personal_or_example("sources.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if any(s.get("id") == clean_id for s in data.get("sources", [])):
        raise ValueError(f"источник с id «{clean_id}» уже есть")
    data.setdefault("sources", []).append({
        "id": clean_id, "name": name.strip()[:120] or clean_id, "kind": "rss", "url": url.strip()[:500],
        "reliability": reliability, "note": note.strip()[:300], "enabled": True,
    })
    target = writable(config.PERSONAL_DIR / "sources.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def delete_source(source_id: str) -> None:
    """Удаляет источник из personal/sources.json — подтверждение (два клика) делает панель."""
    path = config.personal_or_example("sources.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    before = len(data.get("sources", []))
    data["sources"] = [s for s in data.get("sources", []) if s.get("id") != source_id]
    if len(data["sources"]) == before:
        raise ValueError(f"источник «{source_id}» не найден")
    target = writable(config.PERSONAL_DIR / "sources.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def add_topic(topic_id: str, name: str, about: str, keywords: list[str], priority: int = 2) -> None:
    """Добавляет свою тему в personal/interests.json. Без ключевых слов тема никогда ничего не
    найдёт (nexus/research/match.py — дешёвый отбор ищет по ним до модели), поэтому они обязательны."""
    import re
    clean_id = re.sub(r"[^a-z0-9_-]", "", topic_id.strip().lower())[:40]
    if not clean_id:
        raise ValueError("нужен короткий идентификатор темы (латиница/цифры)")
    if not name.strip():
        raise ValueError("нужно название темы")
    kw = sorted({k.strip().lower() for k in keywords if k.strip()})[:30]
    if not kw:
        raise ValueError("нужно хотя бы одно ключевое слово — без них тема никогда не найдёт материалы")
    priority = max(1, min(3, int(priority)))
    path = config.personal_or_example("interests.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if any(t.get("id") == clean_id for t in data.get("topics", [])):
        raise ValueError(f"тема с id «{clean_id}» уже есть")
    data.setdefault("topics", []).append({
        "id": clean_id, "name": name.strip()[:120], "priority": priority, "enabled": True,
        "about": about.strip()[:400], "keywords": kw,
    })
    target = writable(config.PERSONAL_DIR / "interests.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def delete_topic(topic_id: str) -> None:
    """Удаляет тему из personal/interests.json — подтверждение (два клика) делает панель."""
    path = config.personal_or_example("interests.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    before = len(data.get("topics", []))
    data["topics"] = [t for t in data.get("topics", []) if t.get("id") != topic_id]
    if len(data["topics"]) == before:
        raise ValueError(f"тема «{topic_id}» не найдена")
    target = writable(config.PERSONAL_DIR / "interests.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def topics_for_settings() -> list[dict]:
    """Все темы, включая выключенные — чтобы их можно было включить обратно."""
    return [{"id": t.id, "name": t.name, "priority": t.priority, "enabled": t.enabled, "about": t.about}
           for t in sorted(load_all_topics(), key=lambda t: t.priority)]


def save_topics(updates: dict[str, dict]) -> None:
    """updates: {topic_id: {"enabled": bool, "priority": int}}. Пишет в personal/interests.json —
    только два этих поля, остальное (ключевые слова, описание) не трогает."""
    source_path = config.personal_or_example("interests.json")
    data = json.loads(source_path.read_text(encoding="utf-8"))
    for t in data.get("topics", []):
        u = updates.get(t["id"])
        if not u:
            continue
        if "enabled" in u:
            t["enabled"] = bool(u["enabled"])
        if "priority" in u:
            t["priority"] = max(1, min(3, int(u["priority"])))
    target = writable(config.PERSONAL_DIR / "interests.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
