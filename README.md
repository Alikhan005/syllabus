# AlmaU Syllabus Management System

Дипломный Django-проект для управления силлабусами: создание, редактирование, согласование, публикация и базовая автоматическая проверка структуры.

## Стек

- Python 3.12+ рекомендуется
- Django 5.2.9
- SQLite для локальной разработки
- PostgreSQL для деплоя
- WeasyPrint для генерации PDF

## Что умеет проект

- регистрация и вход пользователей с ролями;
- создание силлабусов вручную в системе или загрузкой готового файла;
- workflow согласования: преподаватель -> декан -> УМУ;
- история статусов и уведомления;
- генерация PDF из данных силлабуса.

## AI-функции без преувеличений

В проекте есть AI-модуль, но он не является обязательным для базового запуска.

- Основной сценарий AI-проверки запускается через отдельный worker: `python manage.py run_worker`.
- Без worker силлабус можно отправить на AI-проверку, но очередь не будет обработана: результат не сохранится, а статус не сменится автоматически.
- Даже без LLM модуль может работать в упрощённом rule-based режиме для базовой проверки структуры.
- Для более точной проверки можно подключить удалённую LLM API или локальную GGUF-модель.
- AI-ассистент работает через обычный web-процесс Django, worker для него не нужен.
- В коде есть заготовка AI-виджета, но в базовом шаблоне он сейчас отключён по умолчанию.

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/Alikhan005/syllabus.git
cd syllabus
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
```

Активация:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bat
REM Windows CMD
.\.venv\Scripts\activate.bat
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### 3. Установка базовых зависимостей

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Этого достаточно для обычного Django-запуска, миграций, авторизации, workflow и основной части интерфейса.

### 4. Опциональная установка AI-зависимостей

Если нужен AI-модуль с извлечением текста из файлов и удалённой LLM:

```bash
pip install -r requirements-ai.txt
```

Примечание по локальной GGUF-модели:

- код поддерживает `llama-cpp-python` для локальной GGUF-модели;
- если локальная сборка этого пакета проблемна, можно использовать удалённую OpenAI-compatible API вместо локальной модели.

## Переменные окружения

Создайте файл `.env` в корне проекта при необходимости. Минимальный локальный пример:

```env
DJANGO_SECRET_KEY=change-me-to-a-long-random-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=sqlite:///db.sqlite3
```

Для email, Render и AI можно дополнительно использовать переменные из `config/settings.py` и `render.yaml`.

## Запуск проекта

### Только сайт

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

После этого приложение будет доступно по адресу:

`http://127.0.0.1:8000/`

### Сайт + AI worker

Если нужна фоновая AI-проверка файлов и автоматическая смена статусов, запустите worker во второй консоли:

```bash
python manage.py run_worker
```

Важно:

- только сайт: `python manage.py runserver`;
- сайт + AI worker: `python manage.py run_worker` во второй консоли;
- `requirements.txt` нужен для основного приложения;
- `requirements-ai.txt` нужен только для AI/NLP-сценариев, парсинга PDF/DOCX и remote/local LLM.

## Проверка проекта

```bash
python manage.py check
python manage.py test
```

## Зависимости

- `requirements.txt` — базовые зависимости для сайта, auth, workflow, PDF-экспорта и обычного deploy/run.
- `requirements-ai.txt` — дополнительные зависимости для AI/NLP-сценариев, извлечения текста из PDF/DOCX и LLM-интеграций.

Такое разделение сделано специально: обычный запуск и деплой не должны тянуть тяжёлые или лишние пакеты, которые не используются ядром приложения.

## Замечания

- Для генерации PDF через WeasyPrint на некоторых системах могут понадобиться системные библиотеки.
- На Render базовый деплой описан в `render.yaml` и `deploy/`.
