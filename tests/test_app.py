"""Config persistence, single-instance lock, stale-job guard, PATH fix."""

import os
import subprocess
import sys

from dictate import app as app_mod
from dictate.app import (
    STALE_SECONDS,
    _acquire_single_instance_lock,
    _ensure_homebrew_path,
    _is_stale,
    _load_config,
    _save_config,
)


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "cfg" / "config.json")
    _save_config({"cleanup": False})
    assert _load_config() == {"cleanup": False}


def test_missing_config_defaults_to_cleanup_on(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "nope.json")
    assert _load_config() == {"cleanup": True}


def test_corrupted_config_falls_back(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text("{not json!!")
    monkeypatch.setattr(app_mod, "CONFIG_PATH", p)
    assert _load_config() == {"cleanup": True}
    p.write_text('"just a string"')
    assert _load_config() == {"cleanup": True}


def test_single_instance_lock_blocks_second_process(tmp_path, monkeypatch):
    lock = tmp_path / "dictate.lock"
    monkeypatch.setattr(app_mod, "LOCK_PATH", lock)
    assert _acquire_single_instance_lock()

    contender = (
        "import fcntl, sys\n"
        f"f = open({str(lock)!r}, 'w')\n"
        "try:\n"
        "    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "    sys.exit(0)  # unexpectedly acquired\n"
        "except OSError:\n"
        "    sys.exit(42)  # correctly blocked\n"
    )
    result = subprocess.run([sys.executable, "-c", contender])
    assert result.returncode == 42


def test_stale_job_detection():
    assert not _is_stale(enqueued_at=100.0, now=100.0 + STALE_SECONDS - 1)
    assert _is_stale(enqueued_at=100.0, now=100.0 + STALE_SECONDS + 1)


def test_ensure_homebrew_path_is_idempotent(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    _ensure_homebrew_path()
    first = os.environ["PATH"]
    assert first.split(":").count("/opt/homebrew/bin") <= 1
    _ensure_homebrew_path()
    assert os.environ["PATH"] == first  # no duplicate prepending
