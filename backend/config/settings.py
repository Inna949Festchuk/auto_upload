import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-key")
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", "/var/db.sqlite3"),
    }
}

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Параметры приложения -------------------------------------------------

# Корень, внутри которого разрешено указывать папку назначения (volume в контейнере)
DOWNLOAD_ROOT = os.environ.get("DOWNLOAD_ROOT", "/data")
# Лимит запросов к API Яндекс Диска (запросов в секунду, общий для всех воркеров)
API_QPS = int(os.environ.get("API_QPS", "4"))
# Client ID OAuth-приложения Яндекса (нужен только для ссылки авторизации в UI)
YANDEX_CLIENT_ID = os.environ.get("YANDEX_CLIENT_ID", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# --- Celery ----------------------------------------------------------------

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
