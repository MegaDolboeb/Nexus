@echo off
rem Собирает Nexus в .exe (PyInstaller). Результат — packaging\dist\Nexus\ (папка, не один файл:
rem Nexus хранит свои данные рядом с собой, поэтому важно раздавать именно папку целиком).
cd /d "%~dp0\.."
.venv\Scripts\python.exe -m PyInstaller packaging\nexus.spec --noconfirm --distpath packaging\dist --workpath packaging\build
echo.
echo Готово: packaging\dist\Nexus\Nexus.exe
pause
