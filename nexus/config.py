"""Пути и настройки Nexus."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
MODELS_DIR = ROOT / "models"
PERSONAL_DIR = ROOT / "personal"                       # личные настройки (в публичную версию не входят)


def personal_or_example(name: str) -> Path:
    """personal/<name>, а если его нет — config/<name без .json>.example.json."""
    p = PERSONAL_DIR / name
    return p if p.exists() else ROOT / "config" / name.replace(".json", ".example.json")


@dataclass
class Settings:
    engine_port: int = 11436                 # свой движок Nexus
    watch_every_s: float = 2.0               # как часто проверять приоритетную программу
    http_timeout_s: float = 2.0
    # Игры: во время них Nexus только на процессоре. Список дополняется в Настройках.
    games: tuple[str, ...] = ("javaw.exe", "java.exe", "dota2.exe", "cs2.exe", "csgo.exe", "hoi4.exe")
    extra_pause_programs: tuple[str, ...] = ()   # свои программы (панель → Настройки), сверх games
    # Приоритетная программа (раздел «Главное» задания): пока она занята, Nexus не трогает видеокарту.
    # priority_name пустой = функция выключена — Nexus никого не ждёт, работает как обычная программа.
    priority_name: str = ""
    priority_processes: tuple[str, ...] = ()     # имена процессов, означающие «занята»
    priority_ports: tuple[int, ...] = ()         # порты, занятость которых означает «занята»
    priority_status_file: str = ""               # необязательный JSON-файл {"state": ..., "updated": unix_ts}
    priority_status_free_values: tuple[str, ...] = ("idle",)
    priority_status_stale_s: float = 180.0       # файл старше этого = UNKNOWN
    priority_vram_mb: int = 0                    # сколько видеопамяти ей нужно (0 = не резервируем)
    priority_ram_gb: float = 0.0
    priority_photo: str = ""                     # путь внутри personal/, её фото выбирает человек
    priority_photo_mime: str = "image/jpeg"
    # Расписание: работа отрезками, между ними движок выключен.
    segment_s: float = 25 * 60
    rest_s: float = 5 * 60
    after_priority_s: float = 3 * 60             # после того как приоритетная программа освободилась, подождать
    min_free_ram_gb: float = 3.0                 # меньше — новый отрезок не начинается
    vram_tolerance_mb: int = 300                 # «видеопамять вернулась» = не больше уровня до работы + это
    work_model: str = "qwen3.5:9b"
    cpu_model: str = "qwen3.5:4b"                 # на процессоре, пока идёт игра
    embed_model: str = "bge-m3"                   # поиск по смыслу
    work_options: dict = field(default_factory=lambda: {"num_ctx": 4096})
    # Как именно Nexus исследует (личная настройка, меняется из панели — personal/settings.json):
    research_mode: str = "balanced"               # fast | balanced | thorough — см. RESEARCH_MODES
    custom_instruction: str = ""                  # добавляется к каждой выжимке и ответу Дирижёра, если не пусто
    language: str = "ru"                          # ru | en — язык панели и новых материалов (старые не переводятся)
    extra: dict = field(default_factory=dict)


# Пресеты из раздела «Настройки» панели: быстрее и короче ↔ дольше, но подробнее и внимательнее.
# Настоящий эффект — в nexus/research/digest.py (длина и разбор) и nexus/research/credibility.py
# (повторная сверка расхождений). Список специально короткий и честный: не обещаем того, чего не делаем.
RESEARCH_MODES = {
    "fast": {"name": "Быстро, не так подробно", "digest_predict": 300, "recheck_disputes": False},
    "balanced": {"name": "Сбалансированно", "digest_predict": 600, "recheck_disputes": True},
    "thorough": {"name": "Дольше, но тщательнее", "digest_predict": 1000, "recheck_disputes": True},
}
LANGUAGES = {"ru": "Русский", "en": "English"}
DEFAULT_SETTINGS_FILE = "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Settings() с учётом личных настроек (панель → Настройки). Нет файла или он кривой —
    просто значения по умолчанию, без падения."""
    s = Settings()
    p = path or personal_or_example(DEFAULT_SETTINGS_FILE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return s
    if "segment_min" in data:
        s.segment_s = float(data["segment_min"]) * 60
    if "rest_min" in data:
        s.rest_s = float(data["rest_min"]) * 60
    if "after_priority_min" in data:
        s.after_priority_s = float(data["after_priority_min"]) * 60
    if data.get("research_mode") in RESEARCH_MODES:
        s.research_mode = data["research_mode"]
    s.custom_instruction = str(data.get("custom_instruction", "")).strip()[:500]
    s.priority_photo = str(data.get("priority_photo", ""))
    s.priority_photo_mime = str(data.get("priority_photo_mime", "image/jpeg"))
    if data.get("language") in LANGUAGES:
        s.language = data["language"]
    extra = data.get("extra_pause_programs")
    if isinstance(extra, list):
        s.extra_pause_programs = tuple(str(x).strip().lower() for x in extra if str(x).strip())
    if str(data.get("work_model", "")).strip():
        s.work_model = str(data["work_model"]).strip()
    if str(data.get("cpu_model", "")).strip():
        s.cpu_model = str(data["cpu_model"]).strip()
    if str(data.get("embed_model", "")).strip():
        s.embed_model = str(data["embed_model"]).strip()
    s.priority_name = str(data.get("priority_name", "")).strip()[:80]
    procs = data.get("priority_processes")
    if isinstance(procs, list):
        s.priority_processes = tuple(str(x).strip().lower() for x in procs if str(x).strip())
    ports = data.get("priority_ports")
    if isinstance(ports, list):
        s.priority_ports = tuple(int(x) for x in ports if str(x).strip().lstrip("-").isdigit())
    s.priority_status_file = str(data.get("priority_status_file", "")).strip()
    free_values = data.get("priority_status_free_values")
    if isinstance(free_values, list) and free_values:
        s.priority_status_free_values = tuple(str(x).strip() for x in free_values if str(x).strip())
    if "priority_vram_mb" in data:
        s.priority_vram_mb = int(data["priority_vram_mb"])
    if "priority_ram_gb" in data:
        s.priority_ram_gb = float(data["priority_ram_gb"])
    return s


def save_settings_overrides(data: dict, path: Path | None = None) -> None:
    """Сохраняет личные настройки — сливая с уже сохранёнными, а не затирая их целиком
    (иначе сохранение расписания стёрло бы, например, уже выбранное фото, и наоборот)."""
    from .safety import writable
    p = writable(path or (PERSONAL_DIR / DEFAULT_SETTINGS_FILE))
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    existing.update(data)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
