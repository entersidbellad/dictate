"""Cache detection, offline mode, WAV temp-file hygiene, and real ASR (slow)."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from dictate import transcriber as transcriber_mod
from dictate.transcriber import Transcriber, _model_cached, maybe_go_offline


def make_fake_cache(tmp_path: Path, model_id: str) -> None:
    d = tmp_path / "hub" / f"models--{model_id.replace('/', '--')}" / "snapshots" / "abc"
    d.mkdir(parents=True)


def test_model_cached_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert not _model_cached("org/model")
    make_fake_cache(tmp_path, "org/model")
    assert _model_cached("org/model")


def test_offline_only_when_all_models_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    make_fake_cache(tmp_path, "org/present")

    maybe_go_offline(["org/present", "org/missing"])
    assert "HF_HUB_OFFLINE" not in os.environ

    make_fake_cache(tmp_path, "org/missing")
    maybe_go_offline(["org/present", "org/missing"])
    assert os.environ["HF_HUB_OFFLINE"] == "1"


class FakeResult:
    text = "  hi there  "


def test_temp_wav_exists_during_and_deleted_after():
    t = Transcriber()
    seen = {}

    class FakeModel:
        def transcribe(self, path, **kwargs):
            seen["path"] = Path(path)
            seen["existed"] = Path(path).exists()
            seen["mode"] = oct(Path(path).stat().st_mode & 0o777)
            return FakeResult()

    t._model = FakeModel()
    out = t.transcribe(np.zeros(1600, dtype=np.float32))
    assert out == "hi there"
    assert seen["existed"]
    assert seen["mode"] == "0o600"  # transcript audio is private
    assert not seen["path"].exists()  # cleaned up


def test_temp_wav_deleted_even_on_error():
    t = Transcriber()
    seen = {}

    class ExplodingModel:
        def transcribe(self, path, **kwargs):
            seen["path"] = Path(path)
            raise RuntimeError("boom")

    t._model = ExplodingModel()
    with pytest.raises(RuntimeError):
        t.transcribe(np.zeros(1600, dtype=np.float32))
    assert not seen["path"].exists()


def test_ffmpeg_reachable_under_launchd_path():
    """Guards the Dictate.app PATH bug: with launchd's bare default PATH,
    _ensure_homebrew_path() must make ffmpeg findable (parakeet-mlx needs it)."""
    code = (
        "from dictate.app import _ensure_homebrew_path; import shutil;"
        "_ensure_homebrew_path();"
        "assert shutil.which('ffmpeg'), 'ffmpeg not on PATH after fix'"
    )
    env = {**os.environ, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.slow
def test_real_transcription_of_synthesized_speech(tmp_path):
    wav = tmp_path / "speech.wav"
    subprocess.run(
        ["say", "-o", str(wav), "--data-format=LEI16@16000", "hello world"],
        check=True,
    )
    import wave

    with wave.open(str(wav)) as w:
        audio = (
            np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(
                np.float32
            )
            / 32768
        )
    t = Transcriber()
    text = t.transcribe(audio)
    assert "hello" in text.lower()
    assert "world" in text.lower()
