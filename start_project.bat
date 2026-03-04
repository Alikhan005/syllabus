@echo off
title AlmaU Launcher
echo ===================================================
echo   ZAPUSK PROEKTA ALMAU SYLLABUS
echo   (Ne zakryvay chernye okna!)
echo ===================================================

set "DEV_FLAGS=set DJANGO_DEBUG=True&& set DJANGO_SECURE_SSL_REDIRECT=False&& set DJANGO_SESSION_COOKIE_SECURE=False&& set DJANGO_CSRF_COOKIE_SECURE=False&& set DJANGO_SECURE_HSTS_SECONDS=0&& set DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False&& set DJANGO_SECURE_HSTS_PRELOAD=False&& set DJANGO_X_FRAME_OPTIONS=SAMEORIGIN"

:: 1. Start Django server in forced local-dev mode (HTTP).
start "DJANGO SERVER (SITE)" cmd /k "%DEV_FLAGS%&& venv312\Scripts\activate && python manage.py runserver localhost:8000"

:: 2. Start AI worker in the same local-dev mode.
start "AI WORKER (BRAINS)" cmd /k "%DEV_FLAGS%&& venv312\Scripts\activate && python manage.py run_worker"

echo.
echo Vse zapusheno! Otkryvay sait strogo po HTTP: http://localhost:8000
start "" "http://localhost:8000/"
echo.
timeout /t 10
