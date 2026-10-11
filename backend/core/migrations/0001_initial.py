import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("token", models.CharField(max_length=500)),
                ("login", models.CharField(blank=True, default="", max_length=200)),
                ("total_bytes", models.BigIntegerField(default=0)),
                ("used_bytes", models.BigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="DownloadTask",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("dest", models.CharField(max_length=1000)),
                ("items", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "В очереди"),
                            ("running", "Идёт выгрузка"),
                            ("done", "Завершено"),
                            ("error", "Ошибка"),
                            ("cancelled", "Отменено"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("total_files", models.IntegerField(default=0)),
                ("total_bytes", models.BigIntegerField(default=0)),
                ("done_files", models.IntegerField(default=0)),
                ("done_bytes", models.BigIntegerField(default=0)),
                ("failed_files", models.IntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
