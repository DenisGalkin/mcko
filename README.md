# MCKO — Система для отправки заданий и получения ответов

Веб-приложение для учеников и учителей. Ученики отправляют задания по номерам и получают ответы от учителя или AI. Учителя просматривают отправки и дают ответы через админ-панель.

## 🚀 Возможности

- **Автоматическая идентификация** — каждый пользователь получает уникальный 4-значный ID (сохраняется в cookie)
- **Отправка заданий** — поддержка 14 номеров заданий (1, 2, 3, 4, 5, 6.1, 6.2, 7-13)
- **Загрузка файлов** — можно прикреплять файлы к заданию
- **Получение ответов** — отображение ответов от учителя или AI
- **AI-ответы** — автоматическое генерирование ответов через OpenAI API
- **Админ-панель** — просмотр и управление всеми отправками
- **Настройки AI** — включение/выключение, настройка модели и промпта

## 📋 Требования

- Python 3.9+
- Docker и Docker Compose (опционально, для контейнерного развёртывания)
- OpenAI API ключ (опционально, для AI-ответов)

## 🛠️ Установка

### Вариант 1: Локальный запуск

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Создание файла .env (см. ниже раздел "Переменные окружения")
cp .env.example .env

# Запуск
python app.py
```

Приложение будет доступно по адресу: `http://localhost:5000`

### Вариант 2: Docker Compose

```bash
# Создание файла .env
cp .env.example .env

# Запуск всех сервисов
docker compose up -d
```

Приложение будет доступно по адресу: `http://localhost` (через Caddy)

## ⚙️ Переменные окружения

| Переменная | Описание | Значение по умолчанию |
|---|---|---|
| `SECRET_KEY` | Секретный ключ Flask | `mcko-local-secret` |
| `ADMIN_PASSWORD` | Пароль для админ-панели | `admin123` |
| `AI_ENABLED` | Включить AI | `1` |
| `OPENAI_API_KEY` | API ключ OpenAI | `` |
| `OPENAI_MODEL` | Модель OpenAI | `gpt-5.4-mini` |
| `OPENAI_API_URL` | URL OpenAI API | `https://api.openai.com/v1` |
| `OPENAI_MAX_OUTPUT_TOKENS` | Макс. токенов в ответе | `2048` |
| `OPENAI_MAX_RETRIES` | Макс. попыток ретрай | `2` |
| `AI_MAX_WORKERS` | Поток для AI задач | `15` |
| `SQLITE_TIMEOUT_SECONDS` | Таймаут SQLite | `60` |

## 📁 Структура проекта

```
mcko/
├── app.py                  # Основное приложение Flask
├── config.py               # Конфигурация
├── requirements.txt        # Зависимости
├── Dockerfile              # Docker образ
├── docker-compose.yml      # Оркестрация
├── Caddyfile               # Конфигурация обратного прокси
├── .env.example            # Пример переменных окружения
├── uploads/                # Загруженные файлы (создается автоматически)
├── mcko.db                 # База данных SQLite (создается автоматически)
├── static/                 # Статические файлы
│   ├── admin.js
│   ├── main7.css
│   └── ...
└── templates/              # HTML шаблоны
    ├── index.html          # Главная страница (ученик)
    ├── admin.html          # Админ-панель
    ├── admin_settings.html # Настройки админа
    └── admin_login.html    # Вход в админку
```

## 🗄️ База данных

Используется SQLite с оптимизациями (WAL mode, custom timeout, shared cache).

Основные таблицы:
- **users** — пользователи (uid, nickname, current_task)
- **submissions** — отправки заданий (task_number, text_content, admin_answer, ai_answer)
- **submission_files** — прикреплённые файлы
- **ai_allowed_nicknames** — никнеймы с доступом к AI
- **app_settings** — настройки приложения

## 🧪 Тесты

### Проверка здоровья приложения

```bash
curl http://localhost:5000/healthz
```

Ожидаемый ответ: `{"ok":true}`

### Тестирование админ-панели

```bash
# Вход в админку
curl -X POST http://localhost:5000/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin123"}'

# Получение списка отправок
curl http://localhost:5000/admin
```

### Тестирование отправки задания

```bash
# Отправка задания от пользователя
curl -X POST http://localhost:5000/api/submit \
  -H "Content-Type: application/json" \
  -d '{
    "uid": "1234",
    "nickname": "test_student",
    "task_number": 1,
    "text_content": "Привет, это мое задание!"
  }'
```

### Тестирование AI (если настроен)

```bash
# Проверка настроек AI
curl http://localhost:5000/api/ai-status

# Генерация AI-ответа для конкретной отправки
curl -X POST http://localhost:5000/admin/submission/1/generate-ai
```

## 🔐 Админ-панель

Доступ: `http://localhost:5000/admin`

1. Введите пароль администратора (по умолчанию: `admin123`)
2. Просматривайте отправки пользователей
3. Дайте ответ на задание
4. Настройте AI в разделе настроек

## 📡 API Endpoints

| Метод | Endpoint | Описание |
|---|---|---|
| POST | `/api/submit` | Отправить задание |
| GET | `/api/submission/<uid>/<task_number>` | Получить отправку |
| POST | `/admin/login` | Вход в админку |
| POST | `/admin/logout` | Выход из админки |
| GET | `/admin` | Список отправок |
| PATCH | `/api/tasks/<submission_id>` | Обновить отправку |
| POST | `/admin/submission/<id>/answer` | Сохранить ответ |
| POST | `/admin/submission/<id>/generate-ai` | Генерировать AI-ответ |
| POST | `/api/admin/settings/ai` | Настройки AI |
| POST | `/api/ai-allowed` | Добавить никнейм в белый список |
| DELETE | `/api/ai-allowed/<nickname>` | Удалить никнейм из белого списка |
| GET | `/healthz` | Проверка здоровья |

## 🔄 AI-ответы

AI-ответы генерируются асинхронно через ThreadPoolExecutor. Для этого необходимо:

1. Установить `OPENAI_API_KEY`
2. Включить AI (`AI_ENABLED=1`)
3. Добавить никнейм в белый список через админ-панель

## 🧹 Очистка

```bash
# Удаление базы данных и загруженных файлов
rm mcko.db
rm -rf uploads/*

# Остановка Docker сервисов
docker compose down
```
