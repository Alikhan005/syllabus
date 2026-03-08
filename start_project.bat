@echo off
setlocal

title AlmaU Syllabus Launcher

set "VENV_DIR=.venv"
if exist "venv312\Scripts\activate.bat" set "VENV_DIR=venv312"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Create it first with: python -m venv .venv
    exit /b 1
)

set "DEV_FLAGS=set DJANGO_DEBUG=True&& set DJANGO_SECURE_SSL_REDIRECT=False&& set DJANGO_SESSION_COOKIE_SECURE=False&& set DJANGO_CSRF_COOKIE_SECURE=False&& set DJANGO_SECURE_HSTS_SECONDS=0&& set DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False&& set DJANGO_SECURE_HSTS_PRELOAD=False&& set DJANGO_X_FRAME_OPTIONS=SAMEORIGIN"

echo ===================================================
echo   AlmaU Syllabus local start
echo   Site and AI worker will open in separate consoles.
echo ===================================================
echo Using virtual environment: %VENV_DIR%

start "Django Server" cmd /k "%DEV_FLAGS%&& %VENV_DIR%\Scripts\activate && python manage.py runserver localhost:8000"
start "AI Worker" cmd /k "%DEV_FLAGS%&& %VENV_DIR%\Scripts\activate && python manage.py run_worker"

echo.
echo Open: http://localhost:8000/
start "" "http://localhost:8000/"

endlocal
