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
    generate_spumux_xml,
    build_spumux_pipeline_command,
    get_spumux_font_path,
    format_chapter_time,
)
from dvdcompress.iso import (
    build_genisoimage_command,
    build_xorriso_dvd_command,
    build_dvd_iso_command,
    build_xorriso_bd_command,
)
from dvdcompress.burner import (
    OpticalDrive,
    scan_optical_drives,
    build_burn_command,
    parse_burn_progress_line,
    parse_lsscsi_output,
)
from dvdcompress.system_info import get_hardware_telemetry
from dvdcompress.job_manager import JobStage, Job, JobManager

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
    "generate_spumux_xml",
    "build_spumux_pipeline_command",
    "get_spumux_font_path",
    "format_chapter_time",
    "build_genisoimage_command",
    "build_xorriso_dvd_command",
    "build_dvd_iso_command",
    "build_xorriso_bd_command",
    "OpticalDrive",
    "scan_optical_drives",
    "build_burn_command",
    "parse_burn_progress_line",
    "parse_lsscsi_output",
    "get_hardware_telemetry",
    "JobStage",
    "Job",
    "JobManager",
]



