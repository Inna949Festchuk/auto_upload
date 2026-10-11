"""Мини-клиент классического API Яндекс Диска (https://yandex.ru/dev/disk-api)."""

import os
import time
from pathlib import Path

import httpx

BASE_URL = "https://cloud-api.yandex.net/v1"
CHUNK_SIZE = 1024 * 1024


class YandexAPIError(Exception):
    def __init__(self, status, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


class TokenInvalidError(YandexAPIError):
    pass


class CancelledDownload(Exception):
    pass


class YandexClient:
    def __init__(self, token, rate_limiter=None, timeout=60.0, force_ipv4=None):
        self.token = token
        self.rate_limiter = rate_limiter
        if force_ipv4 is None:
            force_ipv4 = os.environ.get("FORCE_IPV4", "1") == "1"
        # На хостах без IPv6-маршрута резолвер может отдать A-запись IPv6 и
        # соединение падает с «Network is unreachable» — принудительно используем IPv4.
        kwargs = {"timeout": timeout, "follow_redirects": True}
        if force_ipv4:
            kwargs["transport"] = httpx.HTTPTransport(local_address="0.0.0.0")
        self._http = httpx.Client(**kwargs)

    def close(self):
        self._http.close()

    # --- базовые запросы ----------------------------------------------------

    def _headers(self):
        return {"Authorization": f"OAuth {self.token}"}

    @staticmethod
    def _json_message(resp):
        try:
            data = resp.json()
            msg = data.get("message") or data.get("description")
            if msg:
                return str(msg)[:300]
        except Exception:
            pass
        return (resp.text or resp.reason_phrase)[:300]

    @staticmethod
    def _retry_after(resp, default=2.0):
        try:
            return min(60.0, max(1.0, float(resp.headers.get("Retry-After", default))))
        except (TypeError, ValueError):
            return default

    def _request(self, method, path, params=None, max_retries=5):
        """GET/POST к API с ретраями на 429/5xx и сетевых сбоях."""
        url = BASE_URL + path
        attempt = 0
        while True:
            if self.rate_limiter:
                self.rate_limiter.acquire()
            try:
                resp = self._http.request(method, url, params=params, headers=self._headers())
            except httpx.TransportError as e:
                if attempt >= max_retries:
                    raise YandexAPIError(0, f"Сетевая ошибка: {e}", retryable=True) from e
                time.sleep(min(30.0, 2.0 ** attempt))
                attempt += 1
                continue

            if resp.status_code == 401:
                raise TokenInvalidError(401, "Токен недействителен или истёк")
            if resp.status_code == 403:
                raise YandexAPIError(403, f"Доступ запрещён: {self._json_message(resp)}")
            if resp.status_code == 404:
                raise YandexAPIError(404, "Не найдено на диске")
            if resp.status_code == 429:
                if attempt >= max_retries:
                    raise YandexAPIError(429, "Превышен лимит запросов (429)", retryable=True)
                time.sleep(self._retry_after(resp))
                attempt += 1
                continue
            if 500 <= resp.status_code < 600 and attempt < max_retries:
                time.sleep(min(30.0, 1.5 ** attempt))
                attempt += 1
                continue
            if resp.status_code >= 400:
                raise YandexAPIError(
                    resp.status_code,
                    self._json_message(resp),
                    retryable=500 <= resp.status_code < 600,
                )
            return resp

    # --- нормализация ответов (актуальный и старый форматы API) ----------------

    @staticmethod
    def _norm_path(p):
        """'disk:/a/b' → '/a/b'."""
        if p and p.startswith("disk:"):
            return p[len("disk:") :]
        return p

    @staticmethod
    def _norm_type(t):
        return "folder" if t in ("dir", "folder") else t

    @staticmethod
    def _item_size(item):
        if item.get("size") is not None:
            return int(item["size"] or 0)
        f = item.get("file")
        if isinstance(f, dict):
            return int(f.get("size", 0) or 0)
        return 0

    @staticmethod
    def _list_of(data):
        """(items, total) из ответа-списка. Актуальный формат: '_embedded.items'; старый: 'items'."""
        if isinstance(data, dict):
            emb = data.get("_embedded")
            if isinstance(emb, dict) and "items" in emb:
                return emb.get("items", []), int(emb.get("total", 0) or 0)
            if "items" in data:
                return data.get("items", []), int(data.get("total", 0) or 0)
        return [], 0

    def _norm_item(self, item):
        return {
            "path": self._norm_path(item.get("path") or ""),
            "type": self._norm_type(item.get("type") or "file"),
            "name": item.get("name") or "",
            "size": self._item_size(item),
            "modified": item.get("modified") or item.get("created") or "",
        }

    # --- операции над диском --------------------------------------------------

    def disk_info(self):
        data = self._request("GET", "/disk").json()
        return {
            "total_bytes": int(data.get("total_space", data.get("total_bytes", 0)) or 0),
            "used_bytes": int(data.get("used_space", data.get("used_bytes", 0)) or 0),
        }

    def user_login(self):
        try:
            data = self._request("GET", "/users/me").json()
            return data.get("login") or data.get("email") or ""
        except YandexAPIError:
            return ""

    def list_folder(self, path="/"):
        """Итератор по элементам папки с offset-пагинацией (1000 на страницу)."""
        params = {"path": self._norm_path(path or "/"), "limit": 1000, "offset": 0}
        while True:
            data = self._request("GET", "/disk/resources", params=params).json()
            items, total = self._list_of(data)
            for item in items:
                yield self._norm_item(item)
            params["offset"] = int(params["offset"]) + len(items)
            if not items or (total and params["offset"] >= total):
                break

    def iter_files(self, items):
        """Рекурсивно раскрывает выбранные элементы и выдаёт (путь_файла, размер)."""
        for item in items:
            if item.get("type") in ("folder", "dir"):
                for sub in self.list_folder(item["path"]):
                    if sub["type"] == "folder":
                        yield from self.iter_files([sub])
                    else:
                        yield sub["path"], sub["size"]
            else:
                # Размер из списка уже известен; для файла, выбранного напрямую, добираем.
                if "size" in item:
                    size = self._item_size(item)
                else:
                    try:
                        size = self._item_size(self.get_resource(item["path"]))
                    except YandexAPIError:
                        size = 0
                yield item["path"], size

    def get_resource(self, path):
        """Объект ресурса. Актуальный формат возвращает его без обёртки, старый — списком."""
        data = self._request(
            "GET", "/disk/resources", params={"path": self._norm_path(path)}
        ).json()
        if isinstance(data, dict) and ("type" in data or "file" in data):
            return data
        items, _ = self._list_of(data)
        if not items:
            raise YandexAPIError(404, f"Не найдено: {path}")
        return items[0]

    def download_url(self, resource):
        """URL скачивания: в актуальном формате — поле 'file' (строка), в старом — 'download_url'."""
        f = resource.get("file")
        if isinstance(f, str):
            return f
        if isinstance(f, dict):
            return f.get("download_url") or f.get("url")
        return resource.get("download_url")

    def stream_to_file(self, url, dest, cancel_check=None, chunk_size=CHUNK_SIZE):
        """Стримит файл с download_url в ``dest`` (через .part-файл). Возвращает число байт."""
        dest = Path(dest)
        tmp = dest.with_name(dest.name + ".part")
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self._http.stream("GET", url) as resp:
            if resp.status_code == 429:
                raise YandexAPIError(
                    429,
                    "Превышен лимит скачиваний (429)",
                    retryable=True,
                    retry_after=self._retry_after(resp, default=5.0),
                )
            if resp.status_code >= 400:
                raise YandexAPIError(resp.status_code, f"Ошибка загрузки файла: HTTP {resp.status_code}")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size):
                    if cancel_check and cancel_check():
                        f.close()
                        tmp.unlink(missing_ok=True)
                        raise CancelledDownload()
                    f.write(chunk)
                    written += len(chunk)
        os.replace(tmp, dest)
        return written
