import json
import pytest
from pathlib import Path
from dvdcompress.config import AppSettings, load_app_settings, save_app_settings

def test_app_settings_defaults(tmp_path):
    settings = load_app_settings(tmp_path)
    assert settings.max_concurrent_jobs == 5

def test_app_settings_save_and_load(tmp_path):
    settings = AppSettings(max_concurrent_jobs=8)
    save_app_settings(settings, tmp_path)
    
    loaded = load_app_settings(tmp_path)
    assert loaded.max_concurrent_jobs == 8
    
    settings_file = tmp_path / "settings.json"
    assert settings_file.exists()
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["max_concurrent_jobs"] == 8

def test_app_settings_validation():
    with pytest.raises(Exception):
        AppSettings(max_concurrent_jobs=0)
    with pytest.raises(Exception):
        AppSettings(max_concurrent_jobs=25)


def test_audio_settings_persistence(tmp_path):
    cfg = AppSettings(
        max_concurrent_jobs=4,
        preferred_audio_language="jpn",
        prefer_surround_audio=False,
    )
    save_app_settings(cfg, tmp_path)
    loaded = load_app_settings(tmp_path)
    assert loaded.preferred_audio_language == "jpn"
    assert loaded.prefer_surround_audio is False

