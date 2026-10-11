from pathlib import Path

import pytest

from core.paths import PathError, resolve_dest, safe_join, yandex_rel

ROOT = "/data"


def test_dest_inside_root():
    assert resolve_dest("/data/backup", ROOT) == Path("/data/backup")


def test_dest_root_itself():
    assert resolve_dest("/data", ROOT) == Path("/data")
    assert resolve_dest("", ROOT) == Path("/data")
    assert resolve_dest("/data/", ROOT) == Path("/data")


def test_dest_outside_root():
    with pytest.raises(PathError):
        resolve_dest("/etc", ROOT)


def test_dest_traversal():
    with pytest.raises(PathError):
        resolve_dest("/data/../etc", ROOT)


def test_dest_relative_to_root():
    assert resolve_dest("sub/dir", ROOT) == Path("/data/sub/dir")


def test_safe_join_basic():
    assert safe_join(Path("/data"), "a/b/file.txt") == Path("/data/a/b/file.txt")


def test_safe_join_traversal_blocked():
    with pytest.raises(PathError):
        safe_join(Path("/data"), "../../etc/passwd")


def test_yandex_rel():
    assert yandex_rel("/a/b/c.txt") == "a/b/c.txt"
    assert yandex_rel("/single.txt") == "single.txt"
    assert yandex_rel("/a/b/") == "a/b"


def test_yandex_rel_empty():
    with pytest.raises(PathError):
        yandex_rel("/")
