"""Parakeet (MLX) transcription. Model loads once; audio goes in as a numpy array.

Privacy: once the model is present in the local Hugging Face cache, the hub is
never contacted again (HF_HUB_OFFLINE is set before huggingface_hub is
imported), so the app runs with zero network access.
"""

import os
import tempfile
import wave
from pathlib import Path

import numpy as np

from .recorder import SAMPLE_RATE

MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v2"
# recordings longer than this are transcribed in overlapping chunks
CHUNK_SECONDS = 120.0


def _model_cached(model_id: str) -> bool:
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    snapshots = hf_home / "hub" / f"models--{model_id.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


def maybe_go_offline(model_ids: list[str]) -> None:
    """Force HF offline mode when every needed model is already cached.

    Must run before huggingface_hub is first imported (i.e. before any model
    load), because it reads HF_HUB_OFFLINE at import time.
    """
    if all(_model_cached(m) for m in model_ids):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")


class Transcriber:
    def __init__(self) -> None:
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from parakeet_mlx import from_pretrained

        self._model = from_pretrained(MODEL_ID)

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        # parakeet-mlx takes a file path, so round-trip through a temp WAV
        # (NamedTemporaryFile is created with 0600 permissions)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = Path(f.name)
        try:
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(pcm.tobytes())
            result = self._model.transcribe(path, chunk_duration=CHUNK_SECONDS)
            return result.text.strip()
        finally:
            path.unlink(missing_ok=True)
