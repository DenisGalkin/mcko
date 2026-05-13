# MCKO

Веб-приложение для отправки школьных заданий, проверки работ в админ-панели и выдачи ответов от учителя или AI.

## Возможности

- автоматический 4-значный ID пользователя в cookie;
- отправка текста и файлов по номерам заданий `1`-`13`, включая `6.1` и `6.2`;
- просмотр своих загрузок и полученных ответов;
- админ-панель для проверки, фильтрации и ответа на работы;
- белый список никнеймов для AI-ответов;
- настройки модели, промпта и включения AI из админки;
- SQLite с WAL и настройками таймаутов.

## Быстрый запуск

```bash
pip install -r requirements.txt
python main.py
```

Локальный адрес: `http://localhost:5000`.

## Docker Compose

```bash
copy .env.example .env
docker compose up -d
```

Приложение будет доступно через Caddy: `http://localhost`.

## Структура проекта

```text
mcko/
├── app/
│   ├── __init__.py               # Application factory and blueprint registration
│   ├── web.py                    # Compatibility app entrypoint
│   ├── config.py                 # Environment-based config
│   ├── settings.py               # Paths, task numbers, shared constants
│   ├── database.py               # Compatibility facade for repositories
│   ├── db/                       # SQLAlchemy engine, sessions, schema and init
│   ├── repositories/             # Query groups by domain
│   ├── routes/                   # Flask blueprints by app area
│   ├── services/                 # Business logic and external integrations
│   ├── models.py                 # Typed DTO/dataclass models
│   ├── submission_service.py     # Compatibility facade for submission service
│   ├── templates/
│   │   ├── student_exam.html
│   │   ├── admin_dashboard.html
│   │   ├── admin_login.html
│   │   └── admin_settings.html
│   └── static/
│       ├── css/
│       ├── js/
│       ├── images/
│       └── vendor/
├── data/                         # Runtime data, ignored by git
│   ├── app.db
│   └── uploads/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Caddyfile
└── .env.example
```

По умолчанию runtime-данные лежат в `data/`. В Docker используется volume `/data`.

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `SECRET_KEY` | Секретный ключ Flask | `mcko-local-secret` |
| `ADMIN_PASSWORD` | Пароль админ-панели | `admin123` |
| `DATA_DIR` | Папка базы и загрузок | `./data` |
| `AI_ENABLED` | Включить AI | `1` |
| `OPENAI_API_KEY` | API ключ OpenAI | пусто |
| `OPENAI_MODEL` | Модель OpenAI | `gpt-5.4-mini` |
| `OPENAI_API_URL` | URL OpenAI API | `https://api.openai.com/v1` |
| `OPENAI_MAX_OUTPUT_TOKENS` | Максимум токенов ответа | `2048` |
| `OPENAI_MAX_RETRIES` | Количество повторов API-запроса | `2` |
| `AI_MAX_WORKERS` | Число фоновых AI-потоков | `8` |
| `SQLITE_TIMEOUT_SECONDS` | Таймаут SQLite | `60` |
| `SQLITE_CACHE_KB` | SQLite cache size | `32768` |

## Основные адреса

| Метод | Endpoint | Описание |
|---|---|---|
| `GET` | `/` | Страница ученика |
| `POST` | `/profile` | Сохранить никнейм |
| `POST` | `/profile/current-task` | Сохранить текущий номер задания |
| `POST` | `/submit` | Отправить задание |
| `GET` | `/answers` | Получить ответы текущего ученика |
| `GET` | `/my-summary` | Сводка загрузок и ответов |
| `GET` | `/admin` | Админ-панель |
| `GET`, `POST` | `/admin/login` | Вход в админку |
| `GET` | `/admin/settings` | Настройки AI |
| `GET` | `/api/tasks` | Список отправок |
| `PATCH` | `/api/tasks/<task_key>` | Обновить ответ |
| `POST` | `/admin/submission/<id>/generate-ai` | Сгенерировать AI-ответ |
| `GET` | `/files/<filename>` | Открыть загруженный файл |
| `GET` | `/healthz` | Healthcheck |

## Проверка

```bash
python -m compileall app
python main.py
curl http://localhost:5000/healthz
```

Ожидаемый healthcheck: `{"ok":true}`.

## Очистка runtime-данных

Остановите приложение, затем удалите ненужные файлы из `data/`:

```bash
del data\app.db*
rmdir /s /q data\uploads
```
