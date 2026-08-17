"""Domain data models and enumerations for DVDCompress."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class DiscType(str, Enum):
    DVD5 = "dvd5"
    DVD9 = "dvd9"
    BD25 = "bd25"
    BD50 = "bd50"
    BD66 = "bd66"
    BD100 = "bd100"
    BD128 = "bd128"

class TVStandard(str, Enum):
    AUTO = "auto"
    NTSC = "ntsc"
    PAL = "pal"

class AspectRatio(str, Enum):
    RATIO_16_9 = "16:9"
    RATIO_4_3 = "4:3"

class MenuMode(str, Enum):
    AUTOPLAY = "autoplay"
    MENU = "menu"

class OutputMode(str, Enum):
    ISO_ONLY = "iso_only"
    BURN_DIRECT = "burn_direct"
    AUTHOR_AND_BURN = "author_and_burn"
    PREVIEW_VIDEO = "preview_video"
    PREVIEW_ISO = "preview_iso"


class AudioStreamInfo(BaseModel):
    index: int
    codec_name: str
    channels: int
    channel_layout: Optional[str] = "stereo"
    language: Optional[str] = "und"
    title: Optional[str] = None
    bitrate: Optional[int] = None

class SubtitleStreamInfo(BaseModel):
    index: int
    codec_name: str
    language: Optional[str] = "und"
    title: Optional[str] = None
    is_default: bool = False
    is_forced: bool = False

class MediaInfo(BaseModel):
    path: str
    filename: str
    duration_sec: float
    width: int
    height: int
    aspect_ratio: str
    frame_rate: float
    video_codec: str
    pix_fmt: Optional[str] = None
    color_space: Optional[str] = None
    color_transfer: Optional[str] = None
    color_primaries: Optional[str] = None
    is_hdr: bool = False
    audio_streams: List[AudioStreamInfo] = Field(default_factory=list)
    subtitle_streams: List[SubtitleStreamInfo] = Field(default_factory=list)
    chapters_count: int = 0
    chapter_times: List[float] = Field(default_factory=list)
    size_bytes: int = 0

# Aliases for interface compatibility
MediaStreamInfo = AudioStreamInfo
VideoMetadata = MediaInfo

class BitrateBudget(BaseModel):
    disc_type: DiscType
    target_capacity_mb: float
    used_capacity_mb: float
    capacity_percent: float
    video_bitrate_kbps: int
    audio_bitrate_kbps: int
    mux_overhead_kbps: int
    total_bitrate_kbps: int
    fits_disc: bool
    warnings: List[str] = Field(default_factory=list)
    recommended_disc_type: Optional[DiscType] = None
    recommendation_reason: Optional[str] = None

class ProjectConfig(BaseModel):
    input_files: List[str]
    disc_type: DiscType = DiscType.DVD5
    output_mode: OutputMode = OutputMode.ISO_ONLY
    output_name: str = "dvd_project"
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    disc_label: str = "DVD_VIDEO"
    burn_device: Optional[str] = None
    burn_speed: int = 4
