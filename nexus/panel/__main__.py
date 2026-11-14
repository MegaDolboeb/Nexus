"""Запуск сервера панели отдельно, для разработки и проверки: python -m nexus.panel"""
from .server import run, url_for_launch

if __name__ == "__main__":
    print("Панель (для разработки, без окна): " + url_for_launch())
    run()
