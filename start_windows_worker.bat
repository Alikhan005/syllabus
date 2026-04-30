@echo off
setlocal

title AlmaU Syllabus AI Worker

set "VENV_DIR=.venv"
if exist "venv312\Scripts\activate.bat" set "VENV_DIR=venv312"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Create it first with: py -m venv .venv
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 exit /b 1

python manage.py run_worker

endlocal
