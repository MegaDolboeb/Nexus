"""Локальный сервер панели. Слушает только 127.0.0.1, доступ — по секретному токену
(ЗАДАНИЕ.md, раздел 9: «чтобы чужая веб-страница не могла им командовать»).

Панель и сама работа Nexus — один процесс (nexus.panel.runtime.Runtime). Поэтому кнопки
«Запустить/Пауза/Остановить» и Дирижёр по-настоящему управляют работой, а не притворяются.
При старте сервера Nexus запускается сам; если его движок занят другим Nexus, панель честно
показывает «управление недоступно», но продолжает показывать данные.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import data as panel_data
from . import i18n
from .token import get_token

log = logging.getLogger("nexus.panel.server")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
AUTO_START = True            # выключается в тестах, чтобы не поднимать настоящий движок


@asynccontextmanager
async def lifespan(app: FastAPI):
    if AUTO_START:
        panel_data.get_runtime().start()
    yield
    if AUTO_START:
        panel_data.get_runtime().shutdown_process()


app = FastAPI(title="Nexus", docs_url=None, redoc_url=None, lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def require_token(x_nexus_token: str | None = Header(default=None)) -> None:
    if not x_nexus_token or x_nexus_token != get_token():
        raise HTTPException(status_code=401, detail="неверный или отсутствующий токен")


def require_page_token(token: str = Query(default="")) -> str:
    if token != get_token():
        raise HTTPException(status_code=401, detail="неверный токен")
    return token


def page_base(token: str) -> dict:
    """Общие для каждой страницы данные шаблона (шапка/боковое меню, язык интерфейса)."""
    lang = i18n.current_lang()
    strings_for_lang = {k: (v.get(lang) or v.get("ru")) for k, v in i18n.STRINGS.items()}
    rt = panel_data.get_runtime()
    return {
        "token": token, "engine_alive": panel_data.engine_status()["alive"],
        "lang": lang, "t": lambda key, **kw: i18n.t(key, lang, **kw),
        "i18n_json": json.dumps(strings_for_lang, ensure_ascii=False),
        "integrity_changed": getattr(rt, "integrity_changed", []),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request, token: str = Depends(require_page_token)):
    snap = panel_data.home_snapshot()
    return templates.TemplateResponse(request, "index.html", {**page_base(token), "active": "/", **snap})


@app.get("/research", response_class=HTMLResponse)
def research_page(request: Request, token: str = Depends(require_page_token), topic: str = Query(default=""),
                  date: str = Query(default="")):
    items = panel_data.research_feed(topic_id=topic or None, date=date or None)
    topics = panel_data.interests_overview()
    groups = panel_data.group_by_day(items)
    return templates.TemplateResponse(request, "research.html", {
        **page_base(token), "active": "/research", "groups": groups, "topics": topics,
        "selected_topic": topic, "selected_date": date})


@app.get("/interests", response_class=HTMLResponse)
def interests_page(request: Request, token: str = Depends(require_page_token)):
    return templates.TemplateResponse(request, "interests.html", {
        **page_base(token), "active": "/interests", "topics": panel_data.interests_overview()})


@app.get("/memory", response_class=HTMLResponse)
def memory_page(request: Request, token: str = Depends(require_page_token), q: str = Query(default="")):
    return templates.TemplateResponse(request, "memory.html", {
        **page_base(token), "active": "/memory", "items": panel_data.memory_overview(q), "query": q})


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, token: str = Depends(require_page_token)):
    return templates.TemplateResponse(request, "sources.html", {
        **page_base(token), "active": "/sources", "sources": panel_data.sources_overview()})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, token: str = Depends(require_page_token)):
    return templates.TemplateResponse(request, "settings.html", {
        **page_base(token), "active": "/settings", "s": panel_data.settings_overview(),
        "edit_topics": panel_data.topics_for_settings()})


@app.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request, token: str = Depends(require_page_token)):
    return templates.TemplateResponse(request, "activity.html", {
        **page_base(token), "active": "/activity", "events": panel_data.activity_log()})


@app.get("/conductor", response_class=HTMLResponse)
def conductor_page(request: Request, token: str = Depends(require_page_token)):
    return templates.TemplateResponse(request, "conductor.html", {**page_base(token), "active": "/conductor"})


@app.get("/material/{item_id}", response_class=HTMLResponse)
def material_page(request: Request, item_id: int, token: str = Depends(require_page_token)):
    m = panel_data.material_detail(item_id)
    if m is None:
        raise HTTPException(status_code=404, detail="материал не найден")
    return templates.TemplateResponse(request, "material.html", {**page_base(token), "active": "/research", "m": m})


@app.get("/memory/{memory_id}", response_class=HTMLResponse)
def memory_detail_page(request: Request, memory_id: int, token: str = Depends(require_page_token)):
    m = panel_data.memory_detail(memory_id)
    if m is None:
        raise HTTPException(status_code=404, detail="тема не найдена")
    return templates.TemplateResponse(request, "memory_detail.html", {**page_base(token), "active": "/memory", "m": m})


@app.get("/assets/priority")
def priority_photo(token: str = Depends(require_page_token)):
    info = panel_data.priority_photo_path()
    if info is None:
        raise HTTPException(status_code=404, detail="фото не выбрано")
    path, mime = info
    return FileResponse(path, media_type=mime)


@app.get("/api/home", dependencies=[Depends(require_token)])
def api_home():
    return panel_data.home_snapshot()


@app.post("/api/control/start", dependencies=[Depends(require_token)])
def api_control_start():
    panel_data.get_runtime().start()
    return panel_data.control_status()


@app.post("/api/control/pause", dependencies=[Depends(require_token)])
def api_control_pause():
    panel_data.get_runtime().pause()
    return panel_data.control_status()


@app.post("/api/control/stop", dependencies=[Depends(require_token)])
def api_control_stop():
    panel_data.get_runtime().stop()
    return panel_data.control_status()


class ConductorRequest(BaseModel):
    text: str


@app.post("/api/conductor", dependencies=[Depends(require_token)])
def api_conductor_submit(body: ConductorRequest):
    from ..research.guardrails import cheap_check

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="пустой текст")
    cheap = cheap_check(text)
    if cheap is not None:
        return {"decision": cheap.decision, "reason": cheap.reason, "task_id": None}
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="Nexus сейчас недоступен для поручений: " + getattr(rt, "reason", "?"))
    task_id = rt.store.add("errand", f"Поручение: {text[:60]}", {"text": text}, priority=10)
    return {"decision": "queued", "reason": "", "task_id": task_id}


class SettingsForm(BaseModel):
    segment_min: float
    rest_min: float
    after_priority_min: float
    research_mode: str
    custom_instruction: str = ""
    language: str = "ru"
    work_model: str = ""
    cpu_model: str = ""
    embed_model: str = ""


@app.post("/api/settings", dependencies=[Depends(require_token)])
def api_settings_save(body: SettingsForm):
    try:
        panel_data.save_settings(body.segment_min, body.rest_min, body.after_priority_min,
                                 body.research_mode, body.custom_instruction, body.language,
                                 body.work_model, body.cpu_model, body.embed_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "note": "подействует после «Остановить» → «Запустить» (или при следующем запуске Nexus)"}


class PrioritySettingsForm(BaseModel):
    name: str = ""
    processes: str = ""
    ports: str = ""
    status_file: str = ""
    vram_mb: float = 0
    ram_gb: float = 0


@app.post("/api/settings/priority", dependencies=[Depends(require_token)])
def api_priority_settings_save(body: PrioritySettingsForm):
    panel_data.save_priority_settings(body.name, body.processes, body.ports, body.status_file,
                                      body.vram_mb, body.ram_gb)
    return {"ok": True, "note": "подействует после «Остановить» → «Запустить» (или при следующем запуске Nexus)"}


@app.get("/api/models/list", dependencies=[Depends(require_token)])
def api_models_list():
    return panel_data.available_models()


class ModelPullRequest(BaseModel):
    model: str


@app.post("/api/models/pull", dependencies=[Depends(require_token)])
def api_models_pull(body: ModelPullRequest):
    name = body.model.strip()
    if not name:
        raise HTTPException(status_code=400, detail="нужно имя модели")
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="Nexus сейчас недоступен: " + getattr(rt, "reason", "?"))
    task_id = rt.store.add("pull_model", f"Скачивание модели: {name}", {"model": name}, priority=10)
    return {"task_id": task_id}


@app.get("/api/models/pull/{task_id}", dependencies=[Depends(require_token)])
def api_models_pull_status(task_id: int):
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="недоступно")
    try:
        t = rt.store.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="нет такой задачи")
    return {"state": t.state, "checkpoint": t.checkpoint, "reason": t.reason}


class TopicsForm(BaseModel):
    updates: dict


@app.post("/api/topics", dependencies=[Depends(require_token)])
def api_topics_save(body: TopicsForm):
    panel_data.save_topics(body.updates)
    return {"ok": True}


class OverviewRequest(BaseModel):
    item_ids: list[int]


@app.post("/api/research/overview", dependencies=[Depends(require_token)])
def api_overview_submit(body: OverviewRequest):
    if not body.item_ids:
        raise HTTPException(status_code=400, detail="нет материалов")
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="Nexus сейчас недоступен: " + getattr(rt, "reason", "?"))
    task_id = rt.store.add("overview", f"Короткая выжимка: {len(body.item_ids)} материал(ов)",
                           {"item_ids": body.item_ids[:50]}, priority=10)
    return {"task_id": task_id}


@app.get("/api/research/overview/{task_id}", dependencies=[Depends(require_token)])
def api_overview_status(task_id: int):
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="недоступно")
    try:
        t = rt.store.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="нет такой задачи")
    return {"state": t.state, "checkpoint": t.checkpoint, "reason": t.reason}


class SourceReviewRequest(BaseModel):
    name: str
    url: str
    note: str = ""


@app.post("/api/sources/review", dependencies=[Depends(require_token)])
def api_source_review_submit(body: SourceReviewRequest):
    if not body.name.strip() or not body.url.strip():
        raise HTTPException(status_code=400, detail="нужны название и ссылка")
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="Nexus сейчас недоступен для проверки: " + getattr(rt, "reason", "?"))
    task_id = rt.store.add("source_review", f"Проверка источника: {body.name[:60]}",
                           {"name": body.name.strip()[:120], "url": body.url.strip()[:500],
                            "note": body.note.strip()[:300]}, priority=10)
    return {"task_id": task_id}


@app.get("/api/sources/review/{task_id}", dependencies=[Depends(require_token)])
def api_source_review_status(task_id: int):
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="недоступно")
    try:
        t = rt.store.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="нет такой задачи")
    return {"state": t.state, "checkpoint": t.checkpoint, "reason": t.reason}


class SourceAddRequest(BaseModel):
    id: str
    name: str
    url: str
    note: str = ""
    reliability: str = "medium"


@app.post("/api/sources/add", dependencies=[Depends(require_token)])
def api_source_add(body: SourceAddRequest):
    try:
        panel_data.add_source(body.id, body.name, body.url, body.note, body.reliability)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class SourceDeleteRequest(BaseModel):
    id: str


@app.post("/api/sources/delete", dependencies=[Depends(require_token)])
def api_source_delete(body: SourceDeleteRequest):
    try:
        panel_data.delete_source(body.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class TopicAddRequest(BaseModel):
    id: str
    name: str
    about: str = ""
    keywords: str = ""
    priority: int = 2


@app.post("/api/topics/add", dependencies=[Depends(require_token)])
def api_topic_add(body: TopicAddRequest):
    try:
        panel_data.add_topic(body.id, body.name, body.about, body.keywords.split(","), body.priority)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class TopicDeleteRequest(BaseModel):
    id: str


@app.post("/api/topics/delete", dependencies=[Depends(require_token)])
def api_topic_delete(body: TopicDeleteRequest):
    try:
        panel_data.delete_topic(body.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class PauseProgramsForm(BaseModel):
    programs: list[str]


@app.post("/api/settings/pause-programs", dependencies=[Depends(require_token)])
def api_pause_programs_save(body: PauseProgramsForm):
    panel_data.save_extra_pause_programs(body.programs)
    return {"ok": True}


class PhotoUpload(BaseModel):
    data_url: str


@app.post("/api/settings/photo", dependencies=[Depends(require_token)])
def api_settings_photo(body: PhotoUpload):
    try:
        panel_data.save_priority_photo(body.data_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@app.get("/api/conductor/{task_id}", dependencies=[Depends(require_token)])
def api_conductor_status(task_id: int):
    rt = panel_data.get_runtime()
    if not hasattr(rt, "store"):
        raise HTTPException(status_code=503, detail="недоступно")
    try:
        t = rt.store.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="нет такой задачи")
    return {"state": t.state, "checkpoint": t.checkpoint, "reason": t.reason}


def url_for_launch(host: str = "127.0.0.1", port: int = 8777) -> str:
    return f"http://{host}:{port}/?token={get_token()}"


def run(host: str = "127.0.0.1", port: int = 8777) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")
