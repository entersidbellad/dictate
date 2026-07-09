"""Frame selection and sprite fallback logic (no windows created)."""

from pathlib import Path

from dictate import overlay as overlay_mod
from dictate.overlay import TALK_THRESHOLD, load_frames, select_frame


def test_frame_selection_thresholds():
    assert select_frame("listening", 0.0) == "idle"
    assert select_frame("listening", TALK_THRESHOLD) == "idle"
    assert select_frame("listening", TALK_THRESHOLD + 0.001) == "talk"
    assert select_frame("listening", 0.5) == "talk"


def test_thinking_always_uses_think_frame():
    assert select_frame("thinking", 0.0) == "think"
    assert select_frame("thinking", 0.5) == "think"


def test_missing_assets_fall_back_to_vector(tmp_path, monkeypatch):
    monkeypatch.setattr(overlay_mod, "ASSETS_DIR", tmp_path)
    assert load_frames() is None  # empty dir → vector cat, no crash


def test_partial_assets_fall_back_to_vector(tmp_path, monkeypatch):
    (tmp_path / "cat_idle.png").write_bytes(b"not a real png")
    monkeypatch.setattr(overlay_mod, "ASSETS_DIR", tmp_path)
    # talk/think missing → must reject the set entirely
    assert load_frames() is None


def test_corrupt_asset_falls_back_to_vector(tmp_path, monkeypatch):
    for name in ("idle", "talk", "think"):
        (tmp_path / f"cat_{name}.png").write_bytes(b"this is not a png")
    monkeypatch.setattr(overlay_mod, "ASSETS_DIR", tmp_path)
    assert load_frames() is None


def test_real_assets_dir_is_packaged_location():
    assert overlay_mod.ASSETS_DIR == Path(overlay_mod.__file__).parent / "assets"
