@echo off
setlocal

title AlmaU Syllabus Windows Hosting

set "VENV_DIR=.venv"
if exist "venv312\Scripts\activate.bat" set "VENV_DIR=venv312"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Create it first with: py -m venv .venv
    exit /b 1
)

if not exist ".env" (
    echo Missing .env file in project root.
    echo Create it from .env.windows.server.example and set your server IP / host values.
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo Running migrations...
python manage.py migrate
if errorlevel 1 exit /b 1

echo Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 exit /b 1

echo Starting Waitress on 0.0.0.0:8000 ...
waitress-serve --listen=0.0.0.0:8000 config.wsgi:application

endlocal
