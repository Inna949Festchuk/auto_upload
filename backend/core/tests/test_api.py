from pathlib import Path

import pytest
from django.conf import settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class DictRedis:
    """Мини-подделька Redis для тестов."""

    def __init__(self):
        self.d = {}
        self.lists = {}

    def get(self, key):
        return self.d.get(key)

    def set(self, key, value, ex=None):
        self.d[key] = value
        return True

    def incr(self, key):
        return self.incrby(key, 1)

    def incrby(self, key, n=1):
        value = int(self.d.get(key, 0)) + n
        self.d[key] = value
        return value

    def exists(self, key):
        return 1 if key in self.d else 0

    def delete(self, *keys):
        for key in keys:
            self.d.pop(key, None)

    def expire(self, key, ttl):
        return True

    def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)

    def ltrim(self, key, start, end):
        lst = self.lists.get(key, [])
        if start < 0:
            start = max(0, len(lst) + start)
        if end < 0:
            end = len(lst) + end
        self.lists[key] = lst[start : end + 1]

    def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        if start < 0:
            start = max(0, len(lst) + start)
        if end < 0:
            end = len(lst) + end
        return lst[start : end + 1]


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def fake_redis(monkeypatch):
    from core import tasks as tasks_mod

    fr = DictRedis()
    # get_redis() читает модульную глобальную _redis; views импортирует ту же функцию
    monkeypatch.setattr(tasks_mod, "_redis", fr)
    return fr


@pytest.fixture
def connected(client, monkeypatch):
    """Сохраняем токен, подменив сетевые вызовы к Яндексу."""
    from core.yandex import YandexClient

    monkeypatch.setattr(
        YandexClient, "disk_info", lambda self: {"total_bytes": 1000, "used_bytes": 100}
    )
    monkeypatch.setattr(YandexClient, "user_login", lambda self: "tester")
    resp = client.post("/api/token/", {"token": "tok-12345"}, format="json")
    assert resp.status_code == 200, resp.json()


def test_oauth_url_requires_client_id(client):
    settings.YANDEX_CLIENT_ID = ""
    resp = client.get("/api/oauth-url/")
    assert resp.status_code == 400


def test_oauth_url(client, monkeypatch):
    monkeypatch.setattr(settings, "YANDEX_CLIENT_ID", "12345abcde")
    resp = client.get("/api/oauth-url/")
    assert resp.status_code == 200
    assert "client_id=12345abcde" in resp.json()["url"]


def test_token_flow(client, monkeypatch):
    from core.yandex import YandexClient

    monkeypatch.setattr(YandexClient, "disk_info", lambda self: {"total_bytes": 1000, "used_bytes": 100})
    monkeypatch.setattr(YandexClient, "user_login", lambda self: "tester")

    resp = client.get("/api/token/")
    assert resp.json()["connected"] is False

    resp = client.post("/api/token/", {"token": "tok-12345"}, format="json")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["login"] == "tester"

    resp = client.get("/api/token/")
    data = resp.json()
    assert data["connected"] is True
    assert data["token_masked"] == "••••2345"
    assert "tok-12345" not in str(data)

    resp = client.delete("/api/token/")
    assert resp.json()["connected"] is False


def test_browse(client, connected, monkeypatch):
    from core.yandex import YandexClient

    def fake_list(self, path="/"):
        yield {"name": "folder1", "path": "/folder1", "type": "folder", "size": 0, "modified": ""}
        yield {"name": "file.txt", "path": "/file.txt", "type": "file", "size": 42, "modified": ""}

    monkeypatch.setattr(YandexClient, "list_folder", fake_list)
    resp = client.get("/api/disk/browse/", {"path": "/"})
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    names = [i["name"] for i in data["items"]]
    # папки первыми
    assert names[0] == "folder1"
    assert "file.txt" in names
    assert data["parent"] == "/"


def test_task_download_end_to_end(client, connected, fake_redis, monkeypatch, tmp_path):
    from core.yandex import YandexClient

    monkeypatch.setattr(settings, "DOWNLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(
        YandexClient,
        "iter_files",
        lambda self, items: iter([("/dir/file.txt", 10)]),
    )
    monkeypatch.setattr(
        YandexClient, "get_resource", lambda self, path: {"file": "http://fake", "size": 10}
    )

    def fake_stream(self, url, dest, cancel_check=None, chunk_size=1, expected_size=None):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"0123456789")
        return 10

    monkeypatch.setattr(YandexClient, "stream_to_file", fake_stream)

    resp = client.post(
        "/api/tasks/",
        {"dest": str(tmp_path), "items": [{"path": "/dir", "type": "folder"}]},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    tid = resp.json()["id"]

    resp = client.get(f"/api/tasks/{tid}/")
    data = resp.json()
    assert data["status"] == "done"
    assert data["total_files"] == 1
    assert data["done_files"] == 1
    assert data["failed_files"] == 0
    assert (tmp_path / "dir" / "file.txt").read_bytes() == b"0123456789"


def test_task_dest_outside_root_rejected(client, connected, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DOWNLOAD_ROOT", str(tmp_path))
    resp = client.post(
        "/api/tasks/",
        {"dest": "/etc", "items": [{"path": "/a.txt", "type": "file"}]},
        format="json",
    )
    assert resp.status_code == 400


def test_task_requires_items(client, connected, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DOWNLOAD_ROOT", str(tmp_path))
    resp = client.post("/api/tasks/", {"dest": str(tmp_path), "items": []}, format="json")
    assert resp.status_code == 400


def test_task_delete(client, connected, fake_redis, monkeypatch, tmp_path):
    from core.yandex import YandexClient

    monkeypatch.setattr(settings, "DOWNLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(YandexClient, "iter_files", lambda self, items: iter([]))

    resp = client.post(
        "/api/tasks/",
        {"dest": str(tmp_path), "items": [{"path": "/empty-dir", "type": "folder"}]},
        format="json",
    )
    assert resp.status_code == 201
    tid = resp.json()["id"]

    resp = client.delete(f"/api/tasks/{tid}/")
    assert resp.json()["deleted"] is True
    resp = client.get(f"/api/tasks/{tid}/")
    assert resp.status_code == 404
