import os

from app.observability.append_file import AppendFile


def test_keeps_one_descriptor_between_writes(tmp_path, monkeypatch):
    opened = []
    original = os.open
    monkeypatch.setattr(os, "open", lambda *a, **k: opened.append(a[0]) or original(*a, **k))
    log = AppendFile(tmp_path / "nested" / "app.log")
    for index in range(5):
        log.write(f"{index}\n".encode())
    assert len(opened) == 1
    assert (tmp_path / "nested" / "app.log").read_text().splitlines() == ["0", "1", "2", "3", "4"]


def test_reopens_after_rotation_and_deletion(tmp_path):
    path = tmp_path / "events.log"
    log = AppendFile(path)
    log.write(b"first\n")
    path.rename(tmp_path / "events.log.1")
    log.write(b"second\n")
    path.unlink()
    log.write(b"third\n")
    assert (tmp_path / "events.log.1").read_text() == "first\n"
    assert path.read_text() == "third\n"
