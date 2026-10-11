import uuid

from django.db import models


class Account(models.Model):
    """Подключённый Яндекс Диск (одна строка)."""

    token = models.CharField(max_length=500)
    login = models.CharField(max_length=200, blank=True, default="")
    total_bytes = models.BigIntegerField(default=0)
    used_bytes = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]


class DownloadTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        RUNNING = "running", "Идёт выгрузка"
        DONE = "done", "Завершено"
        ERROR = "error", "Ошибка"
        CANCELLED = "cancelled", "Отменено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Абсолютный путь на сервере (внутри DOWNLOAD_ROOT)
    dest = models.CharField(max_length=1000)
    # [{"path": "/a/b", "type": "folder"|"file"}, ...]
    items = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    total_files = models.IntegerField(default=0)
    total_bytes = models.BigIntegerField(default=0)
    done_files = models.IntegerField(default=0)
    done_bytes = models.BigIntegerField(default=0)
    failed_files = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"DownloadTask {self.id} → {self.dest}"
