"""DVDCompress: Hardware-Accelerated DVD & Blu-ray Authoring and Burning Application."""

from dvdcompress.models import (
    DiscType,
    TVStandard,
    AspectRatio,
    MenuMode,
    OutputMode,
    AudioStreamInfo,
    SubtitleStreamInfo,
    MediaInfo,
    BitrateBudget,
)
from dvdcompress.calculator import calculate_bitrate_budget, DISC_CAPACITIES_MB

__all__ = [
    "DiscType",
    "TVStandard",
    "AspectRatio",
    "MenuMode",
    "OutputMode",
    "AudioStreamInfo",
    "SubtitleStreamInfo",
    "MediaInfo",
    "BitrateBudget",
    "calculate_bitrate_budget",
    "DISC_CAPACITIES_MB",
]
