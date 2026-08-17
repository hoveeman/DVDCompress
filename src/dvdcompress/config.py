"""Configuration settings for DVDCompress."""

import os
from pathlib import Path
from pydantic import BaseModel, Field

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


def load_app_settings(config_dir: Path) -> AppSettings:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.json"
    if settings_file.exists():
        try:
            import json
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return AppSettings(**data)
        except Exception:
            pass
    s = AppSettings()
    save_app_settings(s, config_dir)
    return s


def save_app_settings(app_settings: AppSettings, config_dir: Path) -> None:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.json"
    settings_file.write_text(app_settings.model_dump_json(indent=2), encoding="utf-8")

