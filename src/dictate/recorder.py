"""Microphone capture: 16 kHz mono float32, buffered while the hotkey is held.

Recording is capped at MAX_SECONDS so a stuck or forgotten key can't grow the
buffer without bound.
"""

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000
MAX_SECONDS = 300  # 5 minutes


class Recorder:
    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._samples = 0
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self.level = 0.0  # RMS of the latest block, for the overlay animation

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self._samples = 0
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

    def _callback(self, indata, frames, time, status) -> None:
        self.level = float(np.sqrt(np.mean(indata**2)))
        if self._samples >= SAMPLE_RATE * MAX_SECONDS:
            return
        self._chunks.append(indata.copy())
        self._samples += len(indata)

    def stop(self) -> tuple[np.ndarray, bool]:
        """Stop capturing; return (1-D float32 audio, hit_the_duration_cap)."""
        with self._lock:
            if self._stream is None:
                return np.zeros(0, dtype=np.float32), False
            self._stream.stop()
            self._stream.close()
            self._stream = None
            truncated = self._samples >= SAMPLE_RATE * MAX_SECONDS
            if not self._chunks:
                return np.zeros(0, dtype=np.float32), truncated
            audio = np.concatenate(self._chunks)[:, 0]
            self._chunks = []
            return audio, truncated
