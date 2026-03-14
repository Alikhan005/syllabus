# AlmaU Syllabus Management System

README осы ретпен берілген:
- Қазақша
- Русский
- English

---

# Қазақша

## Жоба туралы

**AlmaU Syllabus Management System** — AlmaU университетіне арналған силлабустарды басқару жүйесі.

Жүйе келесі процестерді біріктіреді:
- курстарды құру және сақтау;
- тақырыптар банкін жүргізу;
- силлабусты жүйе ішінде құрастыру;
- дайын PDF / DOCX файлдарын жүктеу;
- алдын ала AI-тексеру;
- декан және УМУ арқылы келісу;
- хабарламалар, нұсқалар тарихы және аудит.

## Негізгі мүмкіндіктер

- рөлдер және қолжетімділікті бөлу;
- жеке және ортақ курстар;
- жеке және ортақ силлабустар;
- силлабус конструкторы;
- PDF / DOCX жүктеу;
- AlmaU ережелері бойынша AI-тексеру;
- келісу workflow-ы;
- ішкі хабарламалар мен announcements;
- PDF генерациясы;
- әкімшілік басқару.

## Рөлдер

Жүйеде келесі рөлдер бар:
- `teacher`
- `program_leader`
- `dean`
- `umu`
- `admin`

`dean` рөлі үшін қосымша `can_teach` жалауы бар. Бұл:
- тек келісетін деканды;
- әрі декан, әрі оқытушы болатын пайдаланушыны
ажырату үшін қажет.

## Негізгі домендік модель

### Course
`Course` — базалық пән.

Өрістері:
- курс коды;
- бірнеше тілдегі атаулар;
- сипаттама;
- иесі;
- курс тілдері;
- `is_shared` белгісі.

### Topic
`Topic` — курстың мазмұны.

Тақырыпта:
- реттік нөмір;
- сабақ түрі;
- сағат;
- белсенділік;
- әдебиет;
- сұрақтар бар.

### Syllabus
`Syllabus` — нақты семестр мен оқу жылына арналған силлабус.

Оны екі жолмен жасауға болады:
- жүйе ішіндегі конструктор арқылы;
- дайын файлды жүктеу арқылы.

## Workflow

Негізгі статус тізбегі:

`draft -> ai_check -> review_dean -> review_umu -> approved`

Егер ескертулер болса:

`correction`

Қосымша статус:

`rejected`

## AI-тексеру

AI-тексеру адамның келісуін алмастырмайды. Ол тек алдын ала формалдық тексеріс жасайды.

Тексерілетіндер:
- міндетті бөлімдердің толтырылуы;
- AlmaU құрылымына сәйкестік;
- апталар бойынша жоспар;
- әдебиеттің өзектілігі;
- тақырыптардың қайталануы;
- формалдық қателер.

AI қазір AlmaU форматына және **12 аптаға** бейімделген.

Сондай-ақ жүйе силлабусқа ұқсамайтын файлдарды қайтара алады, мысалы:
- meeting transcript;
- meeting recording;
- протокол;
- стенограмма;
- invoice;
- resume.

## Технологиялық стек

- Python 3.12+
- Django 5.2.x
- PostgreSQL
- Django Templates
- WeasyPrint
- Whitenoise
- AI worker

## Жергілікті іске қосу

### 1. Репозиторийді көшіру

```powershell
git clone https://github.com/Alikhan005/syllabus.git
cd syllabus
```

### 2. Виртуалды орта

```powershell
C:\Python313\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Тәуелділіктерді орнату

```powershell
pip install -r requirements.txt
```

AI үшін қосымша тәуелділіктер:

```powershell
pip install -r requirements-ai.txt
```

## PostgreSQL баптауы

`.env` үшін мысал:

```env
DEBUG=True
SECRET_KEY=change-me
ALLOWED_HOSTS=127.0.0.1,localhost

DJANGO_USE_DATABASE_URL=False
DB_ENGINE=django.db.backends.postgresql
DB_NAME=almau_db
DB_USER=almau_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

## Миграциялар және іске қосу

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Сайт мекенжайы:

```text
http://127.0.0.1:8000/
```

## AI worker іске қосу

```powershell
python manage.py run_worker
```

Егер worker іске қосылмаса, AI-тексеру тапсырмалары өңделмейді.

## Ұсынылатын локалдық AI режимі

Сыртқы LLM API-сіз rules-only режимі үшін:

```env
LLM_ASSISTANT_MODE=rules
AI_CHECK_USE_LLM=false
AI_CHECK_FALLBACK_TO_RULES_ON_LLM_ERROR=true
```

## Demo деректер

Demo мәліметтерді жүктеу:

```powershell
python manage.py seed_demo
```

Ұсынылатын demo-аккаунттар:
- `admin_demo`
- `teacher_demo`
- `program_leader_demo`
- `dean_demo`
- `umu_demo`

Жалпы құпиясөз:

```text
Demo12345!
```

## Деплой

Render үшін дайын файлдар бар:
- `render.yaml`
- `deploy/render-build.sh`
- `deploy/render-start.sh`

## Ескерту

Қорғау алдында мыналарды қолмен тексерген дұрыс:
- login;
- рөлдер;
- курс құру;
- силлабус құру;
- AI-тексеру;
- келісу маршруты;
- хабарламалар;
- admin panel.

---

# Русский

## О проекте

**AlmaU Syllabus Management System** — система управления силлабусами для AlmaU.

Система покрывает полный цикл работы:
- создание и хранение курсов;
- ведение банка тем;
- сборка силлабуса внутри системы;
- загрузка готовых PDF / DOCX файлов;
- предварительная AI-проверка;
- согласование через декана и УМУ;
- уведомления, история версий и аудит.

## Основные возможности

- роли и разграничение доступа;
- личные и общие курсы;
- личные и общие силлабусы;
- конструктор силлабуса;
- загрузка PDF / DOCX;
- AI-проверка по правилам AlmaU;
- workflow согласования;
- внутренние уведомления и объявления;
- генерация PDF;
- административное управление.

## Роли

В системе используются роли:
- `teacher`
- `program_leader`
- `dean`
- `umu`
- `admin`

Для `dean` используется дополнительный флаг `can_teach`, чтобы отличать:
- декана, который только согласует;
- декана, который также работает как преподаватель.

## Предметная модель

### Course
`Course` — базовая дисциплина.

Хранит:
- код курса;
- названия на нескольких языках;
- описание;
- владельца;
- языки курса;
- признак `is_shared`.

### Topic
`Topic` — содержимое курса.

У темы есть:
- порядок;
- тип занятия;
- часы;
- активность;
- литература;
- вопросы.

### Syllabus
`Syllabus` — силлабус на конкретный семестр и учебный год.

Создается:
- через конструктор внутри системы;
- через загрузку готового файла.

## Workflow

Основной маршрут документа:

`draft -> ai_check -> review_dean -> review_umu -> approved`

Если есть замечания:

`correction`

Дополнительно:

`rejected`

## AI-проверка

AI-проверка используется как предварительный формальный контроль.

Она проверяет:
- обязательные разделы;
- соответствие структуре AlmaU;
- тематический план по неделям;
- актуальность литературы;
- повторы тем;
- формальные ошибки.

AI уже адаптирован под формат AlmaU на **12 недель**.

Система также умеет отклонять файлы, которые не похожи на силлабус, например:
- meeting transcript;
- meeting recording;
- протокол;
- стенограмма;
- invoice;
- resume.

## Технологический стек

- Python 3.12+
- Django 5.2.x
- PostgreSQL
- Django Templates
- WeasyPrint
- Whitenoise
- AI worker

## Локальный запуск

### 1. Клонирование репозитория

```powershell
git clone https://github.com/Alikhan005/syllabus.git
cd syllabus
```

### 2. Виртуальное окружение

```powershell
C:\Python313\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Установка зависимостей

```powershell
pip install -r requirements.txt
```

Дополнительные зависимости для AI:

```powershell
pip install -r requirements-ai.txt
```

## Настройка PostgreSQL

Пример `.env`:

```env
DEBUG=True
SECRET_KEY=change-me
ALLOWED_HOSTS=127.0.0.1,localhost

DJANGO_USE_DATABASE_URL=False
DB_ENGINE=django.db.backends.postgresql
DB_NAME=almau_db
DB_USER=almau_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

## Миграции и запуск

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Адрес приложения:

```text
http://127.0.0.1:8000/
```

## Запуск AI worker

```powershell
python manage.py run_worker
```

Если worker не запущен, AI-задачи не будут обработаны.

## Рекомендуемый локальный AI-режим

Для rules-only режима без внешнего LLM:

```env
LLM_ASSISTANT_MODE=rules
AI_CHECK_USE_LLM=false
AI_CHECK_FALLBACK_TO_RULES_ON_LLM_ERROR=true
```

## Demo-данные

Команда наполнения demo-данными:

```powershell
python manage.py seed_demo
```

Рекомендуемые demo-аккаунты:
- `admin_demo`
- `teacher_demo`
- `program_leader_demo`
- `dean_demo`
- `umu_demo`

Общий пароль:

```text
Demo12345!
```

## Деплой

В проекте есть готовые файлы для Render:
- `render.yaml`
- `deploy/render-build.sh`
- `deploy/render-start.sh`

## Примечание

Перед защитой желательно вручную проверить:
- login;
- роли;
- создание курса;
- создание силлабуса;
- AI-проверку;
- workflow согласования;
- уведомления;
- admin panel.

---

# English

## About the project

**AlmaU Syllabus Management System** is a Django-based syllabus management platform for AlmaU.

The system covers the full syllabus lifecycle:
- course creation and storage;
- topic bank management;
- in-system syllabus builder;
- PDF / DOCX syllabus upload;
- preliminary AI-based validation;
- dean and UMU approval workflow;
- notifications, revision history, and audit logs.

## Core features

- role-based access control;
- private and shared courses;
- private and shared syllabi;
- syllabus builder;
- PDF / DOCX upload;
- AlmaU-specific AI validation;
- approval workflow;
- internal notifications and announcements;
- PDF generation;
- administrative management tools.

## Roles

The system includes the following roles:
- `teacher`
- `program_leader`
- `dean`
- `umu`
- `admin`

The `dean` role also uses a `can_teach` flag to distinguish:
- a dean who only reviews and approves;
- a dean who also acts as a teacher.

## Domain model

### Course
`Course` is the base academic discipline.

It stores:
- course code;
- multilingual titles;
- description;
- owner;
- course languages;
- `is_shared` flag.

### Topic
`Topic` represents course content.

Each topic includes:
- order;
- class type;
- hours;
- activity;
- literature;
- questions.

### Syllabus
`Syllabus` is a semester-specific syllabus document.

It can be created:
- with the in-system builder;
- by uploading a prepared file.

## Workflow

Main status flow:

`draft -> ai_check -> review_dean -> review_umu -> approved`

If issues are found:

`correction`

Additional status:

`rejected`

## AI validation

AI validation is used as a preliminary formal check before human approval.

It validates:
- required sections;
- AlmaU structure compliance;
- weekly plan completeness;
- literature recency;
- duplicate topics;
- formal completeness issues.

The project is currently aligned with AlmaU's **12-week** format.

The system can also reject files that do not look like syllabi, for example:
- meeting transcript;
- meeting recording;
- protocol / minutes;
- transcript;
- invoice;
- resume.

## Tech stack

- Python 3.12+
- Django 5.2.x
- PostgreSQL
- Django Templates
- WeasyPrint
- Whitenoise
- AI worker

## Local setup

### 1. Clone the repository

```powershell
git clone https://github.com/Alikhan005/syllabus.git
cd syllabus
```

### 2. Create and activate virtual environment

```powershell
C:\Python313\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

Extra dependencies for AI-related file processing:

```powershell
pip install -r requirements-ai.txt
```

## PostgreSQL configuration

Example `.env`:

```env
DEBUG=True
SECRET_KEY=change-me
ALLOWED_HOSTS=127.0.0.1,localhost

DJANGO_USE_DATABASE_URL=False
DB_ENGINE=django.db.backends.postgresql
DB_NAME=almau_db
DB_USER=almau_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

## Migrations and startup

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

App URL:

```text
http://127.0.0.1:8000/
```

## Running the AI worker

```powershell
python manage.py run_worker
```

If the worker is not running, queued AI validation tasks will not be processed.

## Recommended local AI mode

For a local rules-only mode without an external LLM API:

```env
LLM_ASSISTANT_MODE=rules
AI_CHECK_USE_LLM=false
AI_CHECK_FALLBACK_TO_RULES_ON_LLM_ERROR=true
```

## Demo data

To load demo data:

```powershell
python manage.py seed_demo
```

Recommended demo accounts:
- `admin_demo`
- `teacher_demo`
- `program_leader_demo`
- `dean_demo`
- `umu_demo`

Shared password:

```text
Demo12345!
```

## Deployment

The repository already contains Render deployment files:
- `render.yaml`
- `deploy/render-build.sh`
- `deploy/render-start.sh`

## Final note

Before the diploma defense, it is recommended to manually verify:
- login;
- all key roles;
- course creation;
- syllabus creation;
- AI validation;
- approval workflow;
- notifications;
- admin panel.
