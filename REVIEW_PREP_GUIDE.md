# AlmaU Syllabus: подготовка к код-ревью и защите

Этот файл — шпаргалка перед дипломной защитой. Его цель:
- быстро восстановить архитектуру проекта;
- понимать назначение каждого модуля;
- уверенно отвечать на вопросы комиссии;
- помнить сильные стороны реализации.

## 1. Коротко о проекте

Проект автоматизирует жизненный цикл силлабуса в AlmaU:
- преподаватель создает курс и темы;
- на основе курса формирует силлабус;
- загружает PDF/DOCX или собирает содержимое в системе;
- отправляет документ на AI-проверку;
- затем идет согласование `teacher -> dean -> umu`;
- утвержденный силлабус можно опубликовать в общий банк.

Краткая формулировка для защиты:

> Это Django-система для полного жизненного цикла силлабуса: создание, редактирование, AI-проверка, согласование, публикация, уведомления и история изменений.

## 2. Архитектурная идея

Проект разбит на отдельные Django apps:
- `accounts` — пользователи, роли, логин и профиль;
- `catalog` — курсы, темы, литература и вопросы;
- `syllabi` — основной объект “силлабус” и его содержимое;
- `workflow` — статусы, переходы, аудит и история;
- `ai_checker` — AI-проверка, извлечение текста и worker;
- `core` — dashboard, объявления, уведомления, диагностика;
- `config` — настройки, общие URL и dashboard view.

Главная мысль архитектуры:
- `models.py` хранит данные;
- `forms.py` валидирует ввод;
- `views.py` работает с HTTP;
- `services.py` содержит бизнес-логику;
- `templates/` отображают данные;
- `tests.py` проверяют критичные сценарии.

Если спросят, почему логика вынесена в `services.py`, отвечай так:

> View отвечает за запрос и ответ, а сервис — за доменные правила. Так код проще тестировать, поддерживать и переиспользовать.

## 3. Роли и workflow

Роли:
- `teacher`
- `dean`
- `umu`
- `admin`

Ключевые вычисляемые права пользователя:
- `is_admin_like`
- `is_teacher_like`
- `can_edit_content`
- `can_view_courses`
- `can_view_shared_courses`
- `can_manage_announcements`

Статусы силлабуса:
- `draft`
- `ai_check`
- `correction`
- `review_dean`
- `review_umu`
- `approved`
- `rejected`

Полный поток:
1. Создается курс.
2. Добавляются темы.
3. Создается силлабус.
4. Силлабус отправляется на AI-проверку.
5. Worker обрабатывает очередь.
6. Если все хорошо — `review_dean`.
7. Потом `review_umu`.
8. Потом `approved` или возврат на доработку.

## 4. Корневые файлы

### `manage.py`
- стандартная точка входа Django management-команд;
- запускает `runserver`, `migrate`, `test`, `run_worker`.

### `README.md`
- краткое описание проекта и его возможностей.

### `requirements.txt`
- базовые зависимости проекта: Django, WhiteNoise, WeasyPrint, dotenv, PostgreSQL driver и т.д.

### `requirements-ai.txt`
- зависимости для AI и извлечения текста: `httpx`, `markitdown[pdf]`, `pypdf`.

### `requirements-ai-local.txt`
- добавляет `llama-cpp-python` для локальной LLM.

### `start_project.bat`
- локально запускает Django server и AI worker в отдельных окнах.

### `render.yaml`
- декларативный деплой в Render;
- описывает web service, database и env-переменные.

### `deploy/render-build.sh`
- ставит зависимости и делает `collectstatic`.

### `deploy/render-predeploy.sh`
- выполняет миграции.

### `deploy/render-start.sh`
- запускает worker в фоне и Gunicorn в foreground.

## 5. `config/`

### `config/settings.py`

Главный конфиг проекта:
- читает `.env`;
- поддерживает SQLite и PostgreSQL;
- умеет парсить `DATABASE_URL`;
- задает security defaults;
- подключает кастомную модель пользователя;
- включает WhiteNoise для статики;
- настраивает email backend.

Очень важные причины решений:
- helper-функции `_env_*` уменьшают дублирование;
- `AUTH_USER_MODEL` нужен из-за кастомных ролей;
- `SECURE_PROXY_SSL_HEADER` нужен для reverse proxy в production.

### `config/urls.py`
- главный маршрутизатор проекта;
- подключает admin, login/logout/signup, dashboard и URL всех apps;
- на dev-среде умеет отдавать media/static.

### `config/views.py`
- собирает данные для dashboard;
- считает курсы и силлабусы;
- подтягивает pending review;
- управляет объявлениями.

## 6. `accounts/`

### `accounts/models.py`

Главное:
- кастомный `User(AbstractUser)`;
- поле `role`;
- поля `faculty`, `department`, `can_teach`;
- case-insensitive уникальность email;
- вычисляемые свойства для прав.

Почему кастомная модель пользователя:

> Стандартного пользователя Django недостаточно, потому что проект зависит от доменных ролей и логики доступа.

### `accounts/forms.py`
- `SignupForm` — регистрация;
- `LoginForm` — вход по username или email;
- `PasswordResetIdentifierForm` — reset по email или username;
- `ProfileForm` — профиль.

### `accounts/views.py`
- `LoginGateView`
- `SecureLogoutView`
- `SignupView`
- `PasswordResetGateView`
- `ProfileView`

Что важно:
- logout разрешен только через `POST`;
- после регистрации есть auto-login;
- redirect после логина безопасный.

### `accounts/backends.py`
- позволяет логиниться и по email, и по username.

### `accounts/decorators.py`
- переиспользуемые проверки прав доступа для view.

### `accounts/admin.py`

Что делает:
- регистрирует кастомного пользователя в Django admin;
- настраивает колонки, фильтры, fieldsets;
- добавляет массовые admin actions.

Если ткнут в этот файл, отвечай так:

> Я взял стандартный `BaseUserAdmin` и адаптировал его под свою модель пользователя, чтобы не переписывать готовую админку с нуля.

### `accounts/tests.py`
- покрывает регистрацию, password reset, logout security и route password reset confirm.

## 7. `catalog/`

### `catalog/models.py`

Модели:
- `Course`
- `Topic`
- `TopicLiterature`
- `TopicQuestion`

Идея:
- курс — контейнер;
- темы — банк контента;
- литература и вопросы привязаны к теме;
- потом из этого банка собирается силлабус.

### `catalog/forms.py`

Что важно:
- `CourseForm` сохраняет языки курса;
- `clean_code()` не дает дублировать код курса у одного владельца;
- formset-ы позволяют редактировать тему вместе с литературой и вопросами.

### `catalog/views.py`

Основные сценарии:
- список моих курсов;
- создание и редактирование курса;
- просмотр курса;
- создание и редактирование темы;
- список общих курсов;
- fork общего курса в личную копию.

Особенно важно объяснить `course_fork`:
- создается личная копия курса;
- копируются темы;
- копируется литература и вопросы;
- все обернуто в `transaction.atomic`, чтобы не было частично сохраненного состояния.

### `catalog/services.py`
- `ensure_default_courses()` — создает стартовые курсы, если у пользователя их нет;
- `dedupe_courses_queryset()` — скрывает дубликаты курсов и выбирает канонический экземпляр.

### `catalog/admin.py`
- админка курсов и тем.

### `catalog/urls.py`
- маршруты для списка, форм, общих курсов и fork.

### `catalog/tests.py`
- проверяет доступ, fork, formset-ы, дубликаты кода и shared/private сценарии.

## 8. `syllabi/`

### `syllabi/models.py`

Модели:
- `Syllabus`
- `SyllabusTopic`
- `SyllabusRevision`

`Syllabus` — центральная сущность проекта.

Важные поля:
- курс и создатель;
- semester и academic_year;
- статус;
- язык;
- загруженный файл;
- версия;
- AI feedback;
- подробные академические разделы;
- общая литература;
- `created_at` и `updated_at`.

`SyllabusTopic` нужен для важной идеи:

> Тема курса — это шаблон банка, а тема силлабуса — конкретная адаптация этой темы под семестр, недели, часы и задания.

`SyllabusRevision` хранит историю изменений.

### `syllabi/forms.py`
- `SyllabusForm` — создание/импорт;
- `SyllabusDetailsForm` — академические разделы.

Что важно:
- принимаются только `.pdf`, `.doc`, `.docx`;
- курсы в форме фильтруются по пользователю;
- скрываются дубликаты курсов.

### `syllabi/permissions.py`
- определяет, кто может видеть силлабус и shared syllabi.

### `syllabi/services.py`

Ключевые функции:
- `validate_syllabus_structure()`
- `generate_syllabus_pdf()`

`validate_syllabus_structure()` проверяет:
- курс;
- semester;
- academic_year;
- наличие тем;
- корректность недель;
- часы;
- наличие литературы.

`generate_syllabus_pdf()`:
- рендерит HTML-шаблон;
- lazily подключает WeasyPrint;
- возвращает PDF как response.

### `syllabi/views.py`

Это главный пользовательский сценарий работы с силлабусом.

Основные view:
- `syllabi_list`
- `shared_syllabi_list`
- `syllabus_create`
- `upload_pdf_view`
- `syllabus_detail`
- `syllabus_edit_topics`
- `syllabus_edit_details`
- `syllabus_pdf`
- `send_to_ai_check`
- `syllabus_change_status`
- `syllabus_upload_file`
- `syllabus_toggle_share`

Что важно уметь проговорить:
- создание силлабуса поддерживает и сценарий с файлом, и без файла;
- detail page динамически показывает кнопки в зависимости от роли и статуса;
- редактирование тем и деталей доступно только автору и только в `draft/correction`;
- загрузка нового файла увеличивает `version_number`;
- публикация возможна только после `approved`.

### `syllabi/ai.py`
- строит prompt для AI draft;
- получает JSON-ответ;
- использует guidelines и темы силлабуса.

### `syllabi/admin.py`
- админка `Syllabus`, `SyllabusTopic`, `SyllabusRevision`.

### `syllabi/urls.py`
- маршруты создания, редактирования, PDF, AI check и публикации.

### `syllabi/tests.py`
- покрывает права, статусы, редактирование, PDF streaming, share/unshare и AI submit flow.

## 9. `workflow/`

### `workflow/models.py`

Модели:
- `SyllabusStatusLog`
- `SyllabusAuditLog`

Разница:
- `StatusLog` — переходы статусов;
- `AuditLog` — более широкий журнал действий.

### `workflow/services.py`

Самый важный файл согласования.

Ключевые функции:
- `change_status()`
- `queue_for_ai_check()`
- `change_status_system()`

`change_status()`:
- проверяет, можно ли перейти в целевой статус;
- проверяет роль пользователя;
- не дает reviewer согласовать собственный силлабус;
- создает status log;
- создает audit log;
- запускает уведомления и email.

`queue_for_ai_check()`:
- переводит силлабус в `ai_check`;
- чистит старый `ai_feedback`;
- сбрасывает claim-поля;
- не создает дубль очереди, если документ уже там.

`change_status_system()`:
- нужен worker-у;
- обходит role checks, но сохраняет все логи и уведомления.

### `workflow/views.py`
- thin wrapper над `change_status`.

### `workflow/admin.py`
- админка status logs и audit logs.

### `workflow/urls.py`
- URL смены статуса.

### `workflow/tests.py`
- проверяет права reviewers, валидность статусов и системные переходы.

## 10. `core/`

### `core/models.py`

Модели:
- `Announcement`
- `NotificationState`
- `Notification`

Идея:
- объявления живут отдельно;
- уведомления адресованы конкретным пользователям;
- есть состояние прочтения.

### `core/views.py`

Что делает:
- `healthz` — базовый health endpoint;
- `diagnostics` — расширенная диагностика для privileged users;
- `workflow_guide` — страница инструкции;
- `mark_notifications_read` — пометка уведомлений как прочитанных.

### `core/notifications.py`

Сервис уведомлений:
- определяет actor label;
- строит title/body;
- выбирает получателей по статусу;
- создает уведомления;
- считает unread и mark-read.

### `core/announcements.py`
- отправляет email-объявления;
- определяет label автора;
- собирает список получателей;
- рендерит HTML и plain text шаблоны писем.

### `core/context_processors.py`
- подмешивает уведомления в base template.

### `core/forms.py`
- `AnnouncementForm`.

### `core/admin.py`
- админка объявлений и уведомлений.

### `core/urls.py`
- health, diagnostics, guide, notifications mark-read.

### `core/management/commands/seed_demo.py`

Очень сильный файл для защиты.

Что делает:
- создает demo users;
- создает demo courses;
- создает topics, literature и questions;
- создает syllabi в разных статусах;
- создает результаты AI-check;
- создает объявления.

Сильная формулировка:

> Я подготовил management command для быстрого наполнения проекта демонстрационными данными, чтобы можно было показать все роли и все этапы workflow без ручной подготовки базы.

### `core/tests.py`
- покрывает security settings, diagnostics, уведомления, объявления и mark-read.

## 11. `ai_checker/`

### `ai_checker/models.py`
- `AiCheckResult` хранит результат AI-проверки, summary и raw JSON.

### `ai_checker/views.py`
- `run_check` не делает долгую проверку синхронно, а ставит документ в очередь;
- `check_detail` показывает результат;
- `assistant_reply` отвечает в AI-виджете.

Почему очередь, а не синхронный HTTP:

> AI-проверка может быть долгой. Поэтому пользовательский запрос должен быстро завершаться, а тяжелая обработка идет в фоне.

### `ai_checker/llm.py`

Единый слой генерации текста:
- remote API mode;
- local llama.cpp mode;
- `generate_text()` как единая точка входа;
- `warmup_llm()` для уменьшения first-request latency.

### `ai_checker/assistant.py`

Здесь живет AI-помощник:
- быстрые rule-based ответы;
- помощь по использованию системы;
- перевод;
- загрузка guidelines;
- ответы по конкретному силлабусу;
- fallback без LLM.

### `ai_checker/services.py`

Это технически самый сложный файл проекта.

Он:
- извлекает текст из PDF и DOCX;
- умеет fast path и fallback path;
- определяет, что документ вообще не силлабус;
- делает deterministic rule-based проверку;
- при необходимости вызывает LLM;
- при ошибке LLM откатывается на rules;
- сохраняет результат проверки.

Ключевые узлы:
- `extract_text_from_file()` — извлечение текста;
- `_detect_non_syllabus_document()` — защита от загрузки резюме, transcript и других нерелевантных файлов;
- `_quick_structure_decision()` — быстрый deterministic путь;
- `_build_formal_markdown_result()` — строгая структура силлабуса по правилам;
- `_apply_lenient_guardrail()` — смягчает слишком строгий LLM verdict;
- `run_ai_check()` — orchestration всей проверки;
- `_save_check_result()` — сохраняет результат и summary.

На вопрос “почему AI-проверка не только через LLM?” отвечай так:

> Я специально сделал многоуровневую проверку: быстрые правила, строгие формальные правила, детекцию не-силлабуса и fallback при ошибках LLM. Это делает систему надежнее и предсказуемее.

### `ai_checker/management/commands/run_worker.py`

Фоновый worker:
- использует lock file, чтобы не было двух worker-ов;
- забирает силлабусы со статусом `ai_check`;
- проставляет claim-поля;
- вызывает `run_ai_check`;
- переводит силлабус либо в `review_dean`, либо в `correction`;
- при ошибке тоже аккуратно завершает сценарий.

### `ai_checker/admin.py`
- админка результатов AI-проверки.

### `ai_checker/urls.py`
- маршруты запуска проверки, просмотра результата и assistant reply.

### `ai_checker/tests.py`
- покрывают guardrails, fast rules, formal rules, persistence и AI-check view flow.

## 12. Миграции, шаблоны и статика

### Миграции

Что нужно понимать:
- миграции фиксируют эволюцию схемы БД;
- `accounts/migrations/0006_remove_program_leader_role.py` делает data migration и переводит старую роль `program_leader` в `teacher`;
- `syllabi` миграции добавляли AI claim поля и меняли defaults;
- `core` миграции добавили подсистему уведомлений.

Хороший ответ:

> Миграции нужны не только для схемы, но и для безопасного переноса старых данных в новую модель.

### Шаблоны

Главные шаблоны:
- `templates/base.html` — общий layout, nav, flash, уведомления, JS-поведение;
- `templates/dashboard.html` — главная панель;
- `templates/catalog/*.html` — курсы и темы;
- `templates/syllabi/*.html` — создание, detail, edit, PDF;
- `templates/registration/*.html` — логин, signup, профиль и reset;
- `templates/ai_checker/*.html` — результат AI и assistant partial;
- `templates/emails/*.html|*.txt` — письма;
- `templates/guide/workflow_guide.html` — инструкция.

Самый важный шаблон для защиты:
- `templates/syllabi/syllabus_detail.html`

Он показывает:
- статус и прогресс;
- correction feedback;
- upload corrected file;
- действия reviewers;
- AI report;
- общий доступ.

### Статика
- `static/css/style.css` — стили;
- `static/img/*` — логотипы, favicon и иллюстрации.

## 13. Что уже проверено

Локальная верификация:
- `python manage.py check` — без ошибок;
- `python manage.py test` — 92 теста проходят.

Это сильный аргумент на защите:

> У проекта не только реализован функционал, но и есть автоматическая проверка ключевых сценариев: права доступа, workflow, AI guardrails, уведомления, upload и публикация.

## 14. Самые вероятные вопросы комиссии

### Почему кастомная модель пользователя?

> Нужны роли и доменные свойства доступа. Стандартного пользователя Django для этого недостаточно.

### Почему workflow вынесен в отдельный app?

> Потому что статусы, правила переходов, уведомления и аудит — это самостоятельная подсистема, а не просто поле модели.

### Почему используется `transaction.atomic`?

> Чтобы не получить частично сохраненное состояние при составных операциях, например при fork курса или групповом сохранении тем.

### Почему используется `select_related` / `prefetch_related`?

> Чтобы убрать лишние SQL-запросы и избежать N+1 проблемы.

### Почему AI-проверка асинхронная?

> Чтобы не держать HTTP-запрос открытым во время тяжелой проверки и не ухудшать UX.

### Почему есть и rule-based проверка, и LLM?

> Потому что LLM не должна быть единственной точкой надежности. Rules дают предсказуемость и fallback.

### Почему uploaded file иногда отдается как исходный, а иногда генерируется PDF из БД?

> Если пользователь загрузил официальный файл, система отдает именно его. Если файла нет, PDF строится из структурированных данных.

## 15. Как объяснять любую строку кода

Универсальная схема ответа:
1. Назови слой: импорт, модель, форма, view, сервис, route, admin или template.
2. Назови задачу строки: хранение, валидация, доступ, оптимизация, аудит, fallback.
3. Назови причину: надежность, читаемость, переиспользование, безопасность, производительность.

Пример:

> Здесь стоит `transaction.atomic`, потому что операция копирует курс вместе с вложенными сущностями, и я хочу либо сохранить все полностью, либо не сохранить ничего при ошибке.

## 16. На чем сделать акцент перед защитой

Если времени мало, выучи особенно хорошо:
- `config/settings.py`
- `accounts/models.py`
- `accounts/admin.py`
- `catalog/models.py`
- `catalog/views.py`
- `syllabi/models.py`
- `syllabi/views.py`
- `syllabi/services.py`
- `workflow/services.py`
- `core/notifications.py`
- `ai_checker/services.py`
- `ai_checker/management/commands/run_worker.py`

Это ядро проекта.

## 17. Следующий лучший формат подготовки

Самый эффективный следующий шаг:
1. Я задаю тебе вопросы как комиссия.
2. Ты отвечаешь своими словами.
3. Я сразу правлю ответ до короткой, сильной и профессиональной формулировки.

Лучше идти по блокам:
1. `accounts`
2. `catalog`
3. `syllabi`
4. `workflow`
5. `ai_checker`
