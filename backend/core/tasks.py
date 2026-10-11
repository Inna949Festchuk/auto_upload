"""Celery-задачи: развёртка выбранного дерева и скачивание файлов параллельно."""

import json
import logging
import os
from pathlib import Path

import redis
from celery import shared_task
from django.db import transaction

from .models import Account, DownloadTask
from .paths import PathError, safe_join, yandex_rel
from .ratelimit import RateLimiter
from .yandex import CancelledDownload, TokenInvalidError, YandexAPIError, YandexClient

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
API_QPS = int(os.environ.get("API_QPS", "4"))
REDIS_TTL = 7 * 24 * 3600

_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(REDIS_URL)
    return _redis


def k(task_id, name):
    return f"ydl:task:{task_id}:{name}"


def make_client():
    account = Account.objects.order_by("id").first()
    if account is None:
        raise YandexAPIError(0, "Яндекс Диск не подключён")
    return YandexClient(account.token, RateLimiter(get_redis(), API_QPS))


def is_cancelled(task_id):
    try:
        return bool(get_redis().exists(k(task_id, "cancel")))
    except Exception:
        return False


def set_cancelled(task_id):
    get_redis().set(k(task_id, "cancel"), 1, ex=24 * 3600)


def record_error(task_id, path, message):
    r = get_redis()
    entry = json.dumps({"path": path, "error": str(message)[:300]}, ensure_ascii=False)
    r.rpush(k(task_id, "errors"), entry)
    r.ltrim(k(task_id, "errors"), -50, -1)
    r.incrby(k(task_id, "failed_files"), 1)
    r.expire(k(task_id, "errors"), REDIS_TTL)


def _mark_done(task_id, size, ok):
    """Отмечает файл завершённым (успешно или с ошибкой) и завершает задачу, когда всё готово."""
    r = get_redis()
    if ok:
        r.incrby(k(task_id, "done_bytes"), size)
    done = r.incrby(k(task_id, "done_files"), 1)
    for name in ("done_files", "done_bytes", "failed_files", "errors"):
        r.expire(k(task_id, name), REDIS_TTL)
    total = int(r.get(k(task_id, "total_files")) or 0)
    if total and done >= total:
        finalize(task_id)
    return done


def finalize(task_id):
    r = get_redis()
    try:
        with transaction.atomic():
            task = DownloadTask.objects.select_for_update().get(id=task_id)
            if task.status != DownloadTask.Status.RUNNING:
                return
            done = int(r.get(k(task_id, "done_files")) or 0)
            failed = int(r.get(k(task_id, "failed_files")) or 0)
            done_bytes = int(r.get(k(task_id, "done_bytes")) or 0)
            task.done_files = done
            task.done_bytes = done_bytes
            task.failed_files = failed
            if task.total_files and failed == task.total_files:
                task.status = DownloadTask.Status.ERROR
                task.error = "Не удалось выгрузить ни один файл"
            else:
                task.status = DownloadTask.Status.DONE
            task.save(update_fields=["status", "done_files", "done_bytes", "failed_files", "error", "updated_at"])
    except DownloadTask.DoesNotExist:
        return
    logger.info("Task %s finalized: %s (failed: %s)", task_id, task.status, failed)


def _fail(task, message):
    task.status = DownloadTask.Status.ERROR
    task.error = str(message)[:2000]
    task.save(update_fields=["status", "error", "updated_at"])
    logger.error("Task %s failed: %s", task.id, message)


@shared_task(bind=True, acks_late=True, name="core.tasks.run_download")
def run_download(self, task_id):
    """Раскрывает выбранное дерево в список файлов и ставит их в очередь."""
    try:
        task = DownloadTask.objects.get(id=task_id)
    except DownloadTask.DoesNotExist:
        return
    r = get_redis()
    try:
        client = make_client()
    except YandexAPIError as e:
        _fail(task, e.message)
        return

    task.status = DownloadTask.Status.RUNNING
    task.save(update_fields=["status", "updated_at"])

    files = []
    try:
        for item in task.items:
            for file_path, size in client.iter_files([item]):
                if is_cancelled(task_id):
                    task.status = DownloadTask.Status.CANCELLED
                    task.save(update_fields=["status", "updated_at"])
                    client.close()
                    logger.info("Task %s cancelled during scan", task_id)
                    return
                files.append((file_path, size))
    except TokenInvalidError as e:
        client.close()
        _fail(task, "Токен истёк во время выгрузки")
        return
    except (YandexAPIError, PathError) as e:
        client.close()
        _fail(task, e.message if isinstance(e, YandexAPIError) else e)
        return

    total_bytes = sum(size for _, size in files)
    task.total_files = len(files)
    task.total_bytes = total_bytes
    task.save(update_fields=["total_files", "total_bytes", "updated_at"])

    r.set(k(task_id, "total_files"), len(files), ex=REDIS_TTL)
    r.set(k(task_id, "total_bytes"), total_bytes, ex=REDIS_TTL)
    for name in ("done_files", "done_bytes", "failed_files", "errors"):
        r.delete(k(task_id, name))

    if not files:
        client.close()
        finalize(task_id)
        return

    for file_path, size in files:
        download_file.delay(str(task.id), file_path, size, task.dest)
    client.close()


@shared_task(bind=True, acks_late=True, max_retries=5, default_retry_delay=5, name="core.tasks.download_file")
def download_file(self, task_id, disk_path, size, dest):
    """Скачивает один файл, сохраняя структуру: dest + путь файла от корня диска."""
    if is_cancelled(task_id):
        return "cancelled"
    try:
        client = make_client()
    except YandexAPIError as e:
        record_error(task_id, disk_path, e.message)
        _mark_done(task_id, 0, ok=False)
        return "failed"
    try:
        try:
            resource = client.get_resource(disk_path)
            url = client.download_url(resource)
            if not url:
                raise YandexAPIError(500, "Не получен URL для скачивания", retryable=True)
            target = safe_join(Path(dest), yandex_rel(disk_path))
            client.stream_to_file(url, target, cancel_check=lambda: is_cancelled(task_id))
        except CancelledDownload:
            return "cancelled"
        except YandexAPIError as e:
            if e.retryable and self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=min(60, 2 ** self.request.retries))
            record_error(task_id, disk_path, f"HTTP {e.status}: {e.message}")
            _mark_done(task_id, size, ok=False)
            return "failed"
        except (OSError, PathError) as e:
            record_error(task_id, disk_path, str(e))
            _mark_done(task_id, size, ok=False)
            return "failed"
        _mark_done(task_id, size, ok=True)
        return "ok"
    finally:
        client.close()
