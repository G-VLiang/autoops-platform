@echo off
setlocal
REM AutoOps - production mode on Windows
REM Single process serving both API and built frontend: http://localhost:8000
REM For a long-running background service use NSSM or Task Scheduler (see DEPLOY.md).

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\frontend\dist\index.html" (
  echo [1/2] Building frontend...
  pushd "%ROOT%\frontend"
  call npm ci --no-audit --no-fund || goto :failed
  call npm run build || goto :failed
  popd
) else (
  echo [1/2] frontend\dist already exists, skip build
)

echo [2/2] Starting AutoOps on http://localhost:8000
cd /d "%ROOT%\backend"
if not exist "venv\Scripts\activate.bat" (
  echo [error] venv not found. Run: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  goto :failed
)
call venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
goto :eof

:failed
echo.
echo [error] Startup failed. See message above.
pause
