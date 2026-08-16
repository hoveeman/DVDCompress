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
from dvdcompress.transcoder import (
    build_dvd_transcode_command,
    build_bluray_transcode_command,
    parse_ffmpeg_progress_line,
)
from dvdcompress.authoring import (
    generate_dvdauthor_xml,
    generate_tsmuxer_meta,
    format_chapter_time,
)
from dvdcompress.iso import (
    build_genisoimage_command,
    build_xorriso_bd_command,
)

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
    "build_dvd_transcode_command",
    "build_bluray_transcode_command",
    "parse_ffmpeg_progress_line",
    "generate_dvdauthor_xml",
    "generate_tsmuxer_meta",
    "format_chapter_time",
    "build_genisoimage_command",
    "build_xorriso_bd_command",
]


