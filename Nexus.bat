@echo off
rem Запуск Nexus без окна консоли — двойной клик, или закрепи этот файл на панели задач/рабочем столе.
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m nexus panel
