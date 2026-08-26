"""Configuration settings for DVDCompress."""

import os
from pathlib import Path
from pydantic import BaseModel, Field

from typing import Optional

class Settings(BaseModel):
    media_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("DVDCOMPRESS_MEDIA_DIR", os.environ.get("MEDIA_DIR", "/media"))
        )
    )
    output_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("DVDCOMPRESS_OUTPUT_DIR", os.environ.get("OUTPUT_DIR", "/output"))
        )
    )
    config_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("DVDCOMPRESS_CONFIG_DIR", os.environ.get("CONFIG_DIR", "/config"))
        )
    )
    temp_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("DVDCOMPRESS_TEMP_DIR", os.environ.get("TEMP_DIR", "/tmp/dvdcompress"))
        )
    )
    host: str = Field(
        default_factory=lambda: os.environ.get("DVDCOMPRESS_HOST", os.environ.get("HOST", "0.0.0.0"))
    )
    port: int = Field(
        default_factory=lambda: int(os.environ.get("DVDCOMPRESS_PORT", os.environ.get("PORT", "8080")))
    )
    log_level: str = Field(
        default_factory=lambda: os.environ.get("DVDCOMPRESS_LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
    )

settings = Settings()


class AppSettings(BaseModel):
    max_concurrent_jobs: int = Field(default=5, ge=1, le=20)
    preferred_audio_language: str = Field(default="eng")
    prefer_surround_audio: bool = Field(default=True)


_current_settings: Optional[AppSettings] = None



def load_app_settings(config_dir: Path) -> AppSettings:
    global _current_settings
    config_dir = Path(config_dir)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass
    settings_file = config_dir / "settings.json"
    try:
        if settings_file.exists():
            import json
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            _current_settings = AppSettings(**data)
            return _current_settings
    except Exception:
        pass
    if _current_settings is not None:
        return _current_settings
    s = AppSettings()
    save_app_settings(s, config_dir)
    _current_settings = s
    return s


def save_app_settings(app_settings: AppSettings, config_dir: Path) -> None:
    global _current_settings
    _current_settings = app_settings
    config_dir = Path(config_dir)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_file = config_dir / "settings.json"
        settings_file.write_text(app_settings.model_dump_json(indent=2), encoding="utf-8")
    except (OSError, PermissionError):
        pass



