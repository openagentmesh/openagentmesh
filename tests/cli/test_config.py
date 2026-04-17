from __future__ import annotations

from openagentmesh.cli._config import DEFAULT_URL, OAM_URL_FILE, resolve_url, write_url_file


def test_flag_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("OAM_URL", "nats://env:4222")
    (tmp_path / OAM_URL_FILE).write_text("nats://file:4222\n")
    assert resolve_url("nats://flag:4222", cwd=tmp_path) == "nats://flag:4222"


def test_env_wins_over_file(monkeypatch, tmp_path):
    monkeypatch.setenv("OAM_URL", "nats://env:4222")
    (tmp_path / OAM_URL_FILE).write_text("nats://file:4222\n")
    assert resolve_url(None, cwd=tmp_path) == "nats://env:4222"


def test_file_wins_over_default(monkeypatch, tmp_path):
    monkeypatch.delenv("OAM_URL", raising=False)
    (tmp_path / OAM_URL_FILE).write_text("nats://file:4222\n")
    assert resolve_url(None, cwd=tmp_path) == "nats://file:4222"


def test_file_walked_up_from_subdir(monkeypatch, tmp_path):
    monkeypatch.delenv("OAM_URL", raising=False)
    (tmp_path / OAM_URL_FILE).write_text("nats://walked:4222\n")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    assert resolve_url(None, cwd=sub) == "nats://walked:4222"


def test_default_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.delenv("OAM_URL", raising=False)
    assert resolve_url(None, cwd=tmp_path) == DEFAULT_URL


def test_write_url_file_creates_file_in_cwd(tmp_path):
    write_url_file("nats://written:4222", cwd=tmp_path)
    assert (tmp_path / OAM_URL_FILE).read_text().strip() == "nats://written:4222"


def test_file_trims_whitespace_and_blank_lines(monkeypatch, tmp_path):
    monkeypatch.delenv("OAM_URL", raising=False)
    (tmp_path / OAM_URL_FILE).write_text("\n  nats://trimmed:4222  \n\n")
    assert resolve_url(None, cwd=tmp_path) == "nats://trimmed:4222"
