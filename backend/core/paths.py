"""Безопасная работа с путями: валидация папки назначения и маппинг пути Яндекса на локальный."""

from pathlib import Path


class PathError(ValueError):
    pass


def resolve_dest(requested, root):
    """Разрешает папку назначения, указанную пользователем.

    Принимает абсолютный путь (должен быть внутри ``root``) либо относительный
    (относительно ``root``). Возвращает нормализованный ``Path``.
    """
    root = Path(root).expanduser().resolve()
    req = (requested or "").strip()
    p = Path(req)
    if p.is_absolute():
        p = p.resolve()
    else:
        p = (root / req).resolve()
    if p == root or root in p.parents:
        return p
    raise PathError(f"Папка назначения должна быть внутри {root}")


def yandex_rel(disk_path):
    """Возвращает путь файла/папки Яндекса относительно корня диска.

    ``/a/b/c.txt`` → ``a/b/c.txt``.
    """
    rel = (disk_path or "").strip("/")
    if not rel:
        raise PathError("Путь на диске пуст")
    return rel


def safe_join(root, rel):
    """Безопасный ``root / rel`` с гарантией, что результат не выходит за пределы ``root``."""
    root = Path(root).expanduser().resolve()
    p = (root / rel).resolve()
    if p == root or root not in p.parents:
        raise PathError(f"Некорректный путь: {rel}")
    return p
