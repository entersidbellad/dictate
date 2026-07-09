"""Recorder buffering and the 5-minute cap, without touching a real device."""

import numpy as np

from dictate.recorder import MAX_SECONDS, SAMPLE_RATE, Recorder


class FakeStream:
    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


def make_recording_recorder() -> Recorder:
    r = Recorder()
    r._stream = FakeStream()  # as if start() had opened a device stream
    return r


def block(n: int) -> np.ndarray:
    return np.ones((n, 1), dtype=np.float32) * 0.5


def test_buffers_and_concatenates():
    r = make_recording_recorder()
    r._callback(block(1024), 1024, None, None)
    r._callback(block(512), 512, None, None)
    audio, truncated = r.stop()
    assert audio.shape == (1536,)
    assert audio.dtype == np.float32
    assert not truncated


def test_stop_without_start_returns_empty():
    audio, truncated = Recorder().stop()
    assert audio.shape == (0,)
    assert not truncated


def test_cap_stops_buffering_and_sets_flag():
    r = make_recording_recorder()
    r._samples = SAMPLE_RATE * MAX_SECONDS  # at the cap already
    r._chunks = [block(16)]
    r._callback(block(1024), 1024, None, None)  # must be dropped
    audio, truncated = r.stop()
    assert audio.shape == (16,)
    assert truncated


def test_restart_clears_previous_buffer():
    r = make_recording_recorder()
    r._callback(block(100), 100, None, None)
    r.stop()
    # start() would reset state; emulate its buffer reset contract
    r._stream = FakeStream()
    r._chunks = []
    r._samples = 0
    r._callback(block(10), 10, None, None)
    audio, _ = r.stop()
    assert audio.shape == (10,)
