"""Точка входа для .exe-сборки (PyInstaller) — то же самое, что `python -m nexus panel`,
без argparse и консоли."""
from nexus.panel.window import run

if __name__ == "__main__":
    run()
