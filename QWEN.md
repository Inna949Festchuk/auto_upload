# auto_upload — выгрузка из Яндекс Диска

Локальное веб-приложение для массового асинхронного скачивания файлов и папок
из Яндекс Диска на локальный диск с сохранением структуры вложенных каталогов.
Одноаккаунтовый инструмент: один подключённый диск, много задач выгрузки.

## Стек

- **Frontend:** React 18 + Vite 5 (SPA без роутера), отдаётся nginx; `/api` проксируется на `backend:8000`
- **Backend:** Django 5.2 + DRF, uvicorn (ASGI), порт 8000
- **Асинхронность:** Celery 5.5 (брокер — Redis), concurrency воркера = `DOWNLOAD_CONCURRENCY` (по умолчанию 8)
- **Redis:** брокер Celery + счётчики прогресса + общий QPS-рейт-лимит + флаги отмены
- **БД:** SQLite — `var/db.sqlite3` (volume `./var`)
- **Запуск:** docker compose — сервисы `redis`, `backend`, `celery`, `frontend`

## Основные команды

```bash
# Сборка и запуск всего
docker compose up -d --build

# Тесты (Celery в eager-режиме, без сети и без реального Redis)
docker compose run --rm backend pytest

# После ЛЮБЫХ правок кода (Python/JS/HTML) — обязательно пересобрать:
# код не монтируется в контейнеры (нет volume mounts)
docker compose up -d --build
```

Frontend dev-режим (опционально): `cd frontend && npm run dev` — Vite на 5173,
прокси `/api` → `localhost:8000` (см. `frontend/vite.config.js`).

## Конфигурация (.env)

`docker-compose.yml` пробрасывает переменные в контейнеры backend и celery.

| Переменная            | По умолчанию | Назначение                                                              |
| --------------------- | ------------ | ----------------------------------------------------------------------- |
| `YANDEX_CLIENT_ID`    | — (обязательно) | Client ID OAuth-приложения (implicit-флоу, Client Secret не нужен)    |
| `DOWNLOAD_ROOT`       | `/data`      | Корень допустимых папок назначения (в контейнере; на хосте — `./data`)  |
| `DOWNLOAD_CONCURRENCY`| `8`          | Число потоков celery-воркера (параллельные загрузки)                    |
| `API_QPS`             | `4`          | Общий лимит запросов к API Яндекса, req/s (Redis, общий для всех процессов) |
| `FORCE_IPV4`          | `1`          | Принудительный IPv4 в httpx (для хостов без IPv6-маршрута)              |
| `SECRET_KEY`          | dev-значение | Секрет Django (локальное использование)                                 |

Также в `config/settings.py`: `DATABASE_PATH` (по умолчанию `/var/db.sqlite3`),
`REDIS_URL` (ставится compose'ом: `redis://redis:6379/0`), `DEBUG`.

## Архитектура

```
frontend (nginx + React SPA, 127.0.0.1:8080)
   │  /api → proxy → backend:8000
backend (Django + DRF, uvicorn)
   │  DownloadTask.objects.create(...) → run_download.delay(task_id)
celery worker (N потоков)
   │  run_download: рекурсивно раскрывает выбранное дерево (API Яндекса)
   │  → на каждый файл: download_file.delay(...)
   │  download_file: стримит в dest/<путь файла от корня диска>
   │  прогресс/отмена/ошибки — ключи Redis ydl:task:{id}:{name} (TTL 7 дней)
redis (брокер, счётчики, rate-limit, флаги отмены)
./data (volume) — выгружаемые файлы
./var  (volume) — db.sqlite3
```

Ключевые инварианты:

- Файл пишется в `.part` и атомарно переименовывается (`os.replace`) — после
  отмены/сбоя не остаётся «половинчатых» файлов.
- Завершение задачи (`finalize`) — в `select_for_update`, когда
  `done_files >= total_files`; статусы: pending / running / done / error / cancelled.
- Отмена — Redis-флаг, проверяется в циклах задачи и между чанками стрима.
- `download_file` ретраится на retryable-ошибки (429/5xx/сеть): max_retries=5,
  backoff `2^retries` (в `yandex.py` — свои ретраи на 429/5xx с Retry-After).

### API (backend/config/urls.py)

- `GET /api/oauth-url/` — ссылка авторизации Яндекса (client_id из окружения)
- `GET /api/token/` — статус подключения (токен маскирован: `••••` + 4 последних)
- `POST /api/token/` — подключение по токену (валидирует токен, сохраняет аккаунт)
- `DELETE /api/token/` — отключить диск
- `GET /api/disk/browse/?path=/` — содержимое папки (пагинация 1000/страница, папки сначала)
- `GET /api/tasks/` — история (последние 50)
- `POST /api/tasks/` — создать задачу: `{dest, items:[{path, type}]}`, ≤1000 элементов
- `GET /api/tasks/<uuid>/` — задача + прогресс из Redis
- `DELETE /api/tasks/<uuid>/` — удалить из истории (чищает Redis-ключи)
- `POST /api/tasks/<uuid>/cancel/` — отмена

### Основные модули (backend/core/)

- `models.py` — `Account` (**одна строка**, `id=1`; новая авторизация перезаписывает), `DownloadTask` (UUID-pk, items JSON, статусы, счётчики)
- `views.py` — DRF APIView; ошибки — на русском, коды 400/401/404/502
- `tasks.py` — `run_download` (сканирование дерева + постановка в очередь), `download_file`, `finalize`, `_fail`; префикс ключей Redis `ydl:task:`, TTL 7 дней; ошибки файла — список в Redis (последние 50)
- `yandex.py` — `YandexClient`: классический API `https://cloud-api.yandex.net/v1`;
  **нормализует два формата ответов** (актуальный `_embedded.items` + `file`-строка и старый `items` + `download_url`); 401 → `TokenInvalidError`; `stream_to_file` — чанками 1 МБ через `.part`
- `paths.py` — `resolve_dest` (папка назначения **только внутри** `DOWNLOAD_ROOT`), `safe_join`, `yandex_rel`
- `ratelimit.py` — `RateLimiter`: временное окно `floor(now*qps)` через Redis, общий для API и воркеров
- `config/celery.py` — Celery-приложение, конфиг из `CELERY_*` в settings

### Frontend (frontend/src/)

- `App.jsx` — одна страница: сначала `TokenScreen` (получение/вставка токена), затем `Browser` + `TaskPanel`
- `api.js` — fetch-обёртка, все endpoints
- `components/Browser.jsx` — дерево диска с чекбоксами (папки/файлы), `TaskPanel.jsx` — прогресс (файлы/байты/скорость), отмена, список ошибок, `TokenScreen.jsx` — подключение
- `format.js` — форматирование размеров/дат; `styles.css` — стили
- Сборка: `npm run build` → `dist/`, nginx отдаёт статику, `/assets/` — immutable-cache

## Тесты

- `pytest` + `pytest-django`; `DJANGO_SETTINGS_MODULE = config.settings` (backend/pytest.ini)
- `backend/conftest.py`: session-фиксатура — Celery в **eager-режиме** (`task_always_eager`),
  временный SQLite, временный `DOWNLOAD_ROOT`
- Redis подменяется фейком `DictRedis` (в `test_api.py`); **никаких сетевых запросов** в тестах
- Пакет: `backend/core/tests/` — `test_api.py`, `test_paths.py`, `test_ratelimit.py`, `test_yandex.py`

## Соглашения и ограничения

- UI, API-сообщения и комментарии в коде — на **русском**.
- `.env` не коммитится; в `.env.example` — только плейсхолдеры, без реальных ключей.
- Приложение **без авторизации**: порт фронтенда привязан только к `127.0.0.1:8080`.
  Для сетевого доступа — reverse-proxy с аутентификацией.
- Токен Яндекса хранится в БД в открытом виде (локальный инструмент); в API — только маска; в логи не пишется.
- Гибкие настройки — через переменные окружения с дефолтами, а не хардкод.
- В каталоге **нет git-репозитория** (`.gitignore` присутствует).

## Известные грабли

- **Docker compose: shell-окружение сессии переопределяет `.env`.** Если после правки
  `.env` контейнер берёт старое значение — compose берёт переменные из окружения
  shell-сессии с приоритетом над `.env`. Проверить:
  `docker inspect <ctr> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep KEY`.
  Лечить запуском из чистого окружения:
  `env -u YANDEX_CLIENT_ID docker compose up -d --force-recreate backend celery`.
- **API Яндекса имеет два формата ответов** (новый и старый) — `yandex.py` намеренно
  нормализует оба; не опираться только на один формат.
- `Account` — одна строка (`id=1`): повторное подключение переопределяет предыдущее.