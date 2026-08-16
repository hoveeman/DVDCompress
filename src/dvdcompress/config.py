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
