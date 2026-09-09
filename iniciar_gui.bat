@echo off
cd /d "%~dp0"

if not exist ".venv" (
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
pip show bleak >nul 2>&1
if errorlevel 1 (
    pip install -r requirements.txt
)

python pc\gui.py
pause
