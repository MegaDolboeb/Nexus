# -*- mode: python ; coding: utf-8 -*-
"""Сборка Nexus в .exe (PyInstaller). Папка, не один файл: Nexus хранит свои данные
(models/, data/, logs/, personal/) рядом с собой (nexus/config.py: ROOT = путь к себе) —
--onefile распаковывал бы всё во временную папку и стирал бы её при каждом закрытии."""
import pathlib

ROOT = pathlib.Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "nexus" / "panel" / "templates"), "nexus/panel/templates"),
    (str(ROOT / "nexus" / "panel" / "icon.png"), "nexus/panel"),
    (str(ROOT / "config"), "config"),
]
ollama_dir = ROOT / "packaging" / "ollama"
if ollama_dir.exists():          # своя копия движка (packaging/fetch_ollama.py) — без неё просто не бандлим
    datas.append((str(ollama_dir), "ollama"))

a = Analysis(
    [str(ROOT / "packaging" / "run_nexus.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=[
        "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on", "uvicorn.logging",
    ],
    hookspath=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Nexus",
    console=False,
    icon=str(ROOT / "packaging" / "nexus.ico"),
    contents_directory=".",     # без _internal/ — иначе config.ROOT (путь к себе) съедет на уровень
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="Nexus",
)
