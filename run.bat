@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found on PATH & exit /b 1)
echo Installing / updating dependencies...
python -m pip install -q -r requirements.txt
if "%1"=="asr" python -m pip install -q -r requirements-asr.txt
echo Starting Free AI Video Editor at http://127.0.0.1:8137
python app.py
endlocal
