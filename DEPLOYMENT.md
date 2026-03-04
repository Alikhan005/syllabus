# DEPLOYMENT

## 1. Локальный запуск (рекомендуется для защиты)

### Быстрый способ
1. Запустить `start_project.bat`.
2. Дождаться открытия двух окон:
   1. Django server.
   2. AI worker.
3. Открыть `http://localhost:8000/`.

Важно: не закрывайте окно `AI WORKER`, иначе документы останутся в `ai_check`.

### Ручной способ
1. Активировать окружение:
```powershell
venv312\Scripts\activate
```
2. Применить миграции:
```powershell
python manage.py migrate
```
3. Запустить сервер:
```powershell
python manage.py runserver localhost:8000
```
4. В отдельном окне запустить воркер:
```powershell
python manage.py run_worker
```

## 2. Проверка перед показом

1. Проверить миграции:
```powershell
python manage.py migrate --plan
```
Ожидаемо: `No planned migration operations`.

2. Проверить тесты:
```powershell
python manage.py test
```

3. Проверить, что можно создать силлабус и перевести его по статусам.

## 3. Ключевые переменные окружения

Минимальный набор:

1. `DJANGO_SECRET_KEY`
2. `DJANGO_DEBUG`
3. `DJANGO_ALLOWED_HOSTS`
4. `DATABASE_URL` (или `DB_*`)

Для почты (уведомления):

1. `EMAIL_HOST`
2. `EMAIL_PORT`
3. `EMAIL_HOST_USER`
4. `EMAIL_HOST_PASSWORD`
5. `DEFAULT_FROM_EMAIL`

Для ИИ:

1. `LLM_PROVIDER`
2. `LLM_API_KEY` / `OPENAI_API_KEY` (если remote LLM)
3. `LLM_API_URL`
4. `LLM_REMOTE_MODEL`
5. `AI_WORKER_IDLE_SLEEP`
6. `AI_WORKER_PRELOAD_MODEL`
7. `AI_CHECK_MAX_INPUT_CHARS`
8. `AI_CHECK_LLM_MAX_TOKENS`

## 4. Продакшн-чеклист

1. Выключить debug (`DJANGO_DEBUG=False`).
2. Настроить PostgreSQL.
3. Включить безопасные cookie/SSL/HSTS.
4. Настроить SMTP для уведомлений.
5. Запускать `run_worker` как отдельный сервис (systemd/supervisor/docker).
6. Настроить резервное копирование БД.
7. Настроить мониторинг health/diagnostics endpoint.

## 5. Частые проблемы

1. Документ завис в `ai_check`:
   не запущен worker.
2. Не приходит почта:
   не настроен SMTP.
3. Ошибка при запуске:
   не применены миграции.
4. ИИ работает медленно:
   увеличить ресурсы, включить preload, использовать fast-rules параметры.
