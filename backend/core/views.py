import json
import posixpath

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, DownloadTask
from .paths import PathError, resolve_dest
from .tasks import get_redis, k, run_download, set_cancelled
from .yandex import TokenInvalidError, YandexAPIError, YandexClient

SINGLE_ROW_PK = 1


def _account():
    return Account.objects.order_by("id").first()


class OAuthUrlView(APIView):
    """Ссылка OAuth-авторизации (implicit-флоу) с ClientID из .env."""

    def get(self, request):
        client_id = settings.YANDEX_CLIENT_ID
        if not client_id:
            return Response(
                {"error": "YANDEX_CLIENT_ID не задан — добавьте его в .env"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"url": f"https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}"}
        )


class TokenView(APIView):
    def get(self, request):
        acc = _account()
        if acc is None:
            return Response({"connected": False})
        return Response(
            {
                "connected": True,
                "login": acc.login,
                "used_bytes": acc.used_bytes,
                "total_bytes": acc.total_bytes,
                "token_masked": "••••" + acc.token[-4:],
            }
        )

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            return Response({"error": "Вставьте токен"}, status=status.HTTP_400_BAD_REQUEST)
        client = YandexClient(token)
        try:
            info = client.disk_info()
            login = client.user_login()
        except TokenInvalidError:
            return Response(
                {"error": "Токен недействителен или истёк. Получите новый."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except YandexAPIError as e:
            return Response(
                {"error": f"Ошибка Яндекс Диска: {e.message}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        finally:
            client.close()
        Account.objects.update_or_create(
            id=SINGLE_ROW_PK,
            defaults={
                "token": token,
                "login": login,
                "total_bytes": int(info.get("total_bytes", 0)),
                "used_bytes": int(info.get("used_bytes", 0)),
            },
        )
        return Response(
            {
                "connected": True,
                "login": login,
                "used_bytes": int(info.get("used_bytes", 0)),
                "total_bytes": int(info.get("total_bytes", 0)),
            }
        )

    def delete(self, request):
        Account.objects.all().delete()
        return Response({"connected": False})


class BrowseView(APIView):
    """Содержимое папки диска."""

    def get(self, request):
        acc = _account()
        if acc is None:
            return Response(
                {"error": "Подключите Яндекс Диск"}, status=status.HTTP_401_UNAUTHORIZED
            )
        path = request.query_params.get("path", "/") or "/"
        client = YandexClient(acc.token)
        try:
            items = []
            for it in client.list_folder(path):
                items.append(it)
            items.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))
        except TokenInvalidError:
            return Response(
                {"error": "Токен истёк — подключите Яндекс Диск снова"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except YandexAPIError as e:
            return Response({"error": e.message}, status=status.HTTP_502_BAD_GATEWAY)
        finally:
            client.close()
        parent = posixpath.dirname(path.rstrip("/")) or "/"
        return Response({"path": path, "parent": parent, "items": items})


def _task_payload(t):
    r = get_redis()
    tid = str(t.id)

    def rget(name, default=0):
        try:
            v = r.get(k(tid, name))
            return int(v) if v is not None else default
        except Exception:
            return default

    errors = []
    try:
        for raw in r.lrange(k(tid, "errors"), -50, -1):
            errors.append(json.loads(raw))
    except Exception:
        pass

    return {
        "id": str(t.id),
        "dest": t.dest,
        "items": t.items,
        "status": t.status,
        "total_files": int(r.get(k(tid, "total_files")) or 0) or t.total_files,
        "total_bytes": int(r.get(k(tid, "total_bytes")) or 0) or t.total_bytes,
        "done_files": rget("done_files", t.done_files),
        "done_bytes": rget("done_bytes", t.done_bytes),
        "failed_files": rget("failed_files", t.failed_files),
        "error": t.error,
        "errors": errors,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class TaskListView(APIView):
    def get(self, request):
        tasks = DownloadTask.objects.order_by("-created_at")[:50]
        return Response({"tasks": [_task_payload(t) for t in tasks]})

    def post(self, request):
        if _account() is None:
            return Response(
                {"error": "Подключите Яндекс Диск"}, status=status.HTTP_401_UNAUTHORIZED
            )
        dest = (request.data.get("dest") or "").strip()
        items = request.data.get("items") or []
        if not dest:
            return Response(
                {"error": "Укажите папку назначения"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not isinstance(items, list) or not items:
            return Response(
                {"error": "Выберите хотя бы один файл или папку"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        clean = []
        for it in items[:1000]:
            if not isinstance(it, dict):
                return Response({"error": "Некорректный запрос"}, status=status.HTTP_400_BAD_REQUEST)
            p = (it.get("path") or "").strip()
            if not p.startswith("/"):
                return Response(
                    {"error": f"Некорректный путь на диске: {p}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            clean.append(
                {
                    "path": p,
                    "type": it.get("type") if it.get("type") in ("file", "folder") else "folder",
                }
            )
        try:
            dest_path = resolve_dest(dest, settings.DOWNLOAD_ROOT)
        except PathError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        task = DownloadTask.objects.create(dest=str(dest_path), items=clean)
        run_download.delay(str(task.id))
        return Response({"id": str(task.id)}, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    def get(self, request, pk):
        try:
            task = DownloadTask.objects.get(id=pk)
        except DownloadTask.DoesNotExist:
            return Response({"error": "Не найдено"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_task_payload(task))

    def delete(self, request, pk):
        deleted, _ = DownloadTask.objects.filter(id=pk).delete()
        if not deleted:
            return Response({"error": "Не найдено"}, status=status.HTTP_404_NOT_FOUND)
        r = get_redis()
        tid = str(pk)
        # Флаг отмены НЕ удаляем, а устанавливаем: задачи download_file, уже стоящие
        # в очереди, должны быстро отброситься, не тратя сеть и воркеры.
        try:
            set_cancelled(tid)
            for name in ("total_files", "total_bytes", "done_files", "done_bytes", "failed_files", "errors"):
                r.delete(k(tid, name))
        except Exception:
            pass
        return Response({"deleted": True})


class TaskCancelView(APIView):
    def post(self, request, pk):
        try:
            task = DownloadTask.objects.get(id=pk)
        except DownloadTask.DoesNotExist:
            return Response({"error": "Не найдено"}, status=status.HTTP_404_NOT_FOUND)
        if task.status in (
            DownloadTask.Status.DONE,
            DownloadTask.Status.ERROR,
            DownloadTask.Status.CANCELLED,
        ):
            return Response({"cancelled": False, "status": task.status})
        set_cancelled(str(task.id))
        task.status = DownloadTask.Status.CANCELLED
        task.save(update_fields=["status", "updated_at"])
        return Response({"cancelled": True})
