import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(prefix="ydl-test-"), "db.sqlite3")

import django  # noqa: E402

django.setup()

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _celery_eager():
    """Celery-задачи выполняем синхронно, без брокера."""
    import celery
    from django.conf import settings

    celery.current_app.conf.task_always_eager = True
    celery.current_app.conf.task_eager_propagates = False
    settings.DOWNLOAD_ROOT = tempfile.mkdtemp(prefix="ydl-root-")
    yield
