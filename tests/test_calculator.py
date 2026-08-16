import pytest
from dvdcompress.models import (
    DiscType,
    TVStandard,
    AspectRatio,
    MenuMode,
    OutputMode,
    MediaInfo,
    AudioStreamInfo,
    SubtitleStreamInfo,
    BitrateBudget,
    ProjectConfig,
)
from dvdcompress.calculator import (
    calculate_bitrate_budget,
    DISC_CAPACITIES_MB,
    DVD_MIN_VIDEO_BITRATE,
    DVD_MAX_VIDEO_BITRATE,
    DVD_MAX_TOTAL_BITRATE,
    BD_MIN_VIDEO_BITRATE,
    BD_MAX_VIDEO_BITRATE,
    BD_MAX_TOTAL_BITRATE,
)
from dvdcompress.config import Settings


def test_dvd5_single_movie_bitrate():
    # 2 hour movie (7200 sec) with 1x AC3 192k audio on DVD-5 (4300 MB)
    budget = calculate_bitrate_budget(
        total_duration_sec=7200,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1,
    )
    # Available bytes = ~4300 MB * 0.96 = ~4128 MB -> ~33024000 kbits
    # Audio total = 192 * 7200 = 1382400 kbits
    # Video bits = 31641600 kbits / 7200 s = ~4394 kbps
    assert 4000 <= budget.video_bitrate_kbps <= 4600
    assert budget.audio_bitrate_kbps == 192
    assert budget.total_bitrate_kbps <= 9800
    assert budget.fits_disc is True


def test_dvd5_clamping_short_video():
    # 5 minute video (300 sec) on DVD-5 should clamp to max DVD-Video bitrate (8000 kbps)
    budget = calculate_bitrate_budget(
        total_duration_sec=300,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1,
    )
    assert budget.video_bitrate_kbps == 8000
    assert budget.fits_disc is True


def test_multi_episode_dvd9_calculation():
    # 6 episodes of 45 mins each = 270 mins = 16200 sec on DVD-9 (7850 MB)
    budget = calculate_bitrate_budget(
        total_duration_sec=16200,
        disc_type=DiscType.DVD9,
        audio_tracks_kbps=[192],
        video_count=6,
    )
    assert 3000 <= budget.video_bitrate_kbps <= 4000
    assert budget.fits_disc is True


def test_oversized_duration_warning():
    # 10 hours on DVD-5 -> drops below min acceptable bitrate (2000 kbps)
    budget = calculate_bitrate_budget(
        total_duration_sec=36000,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1,
    )
    assert budget.video_bitrate_kbps == 2000
    assert budget.fits_disc is False
    assert len(budget.warnings) > 0


def test_bd25_calculation():
    # 2 hour movie (7200 sec) with 1x 640k AC3 on BD-25 (23000 MB)
    budget = calculate_bitrate_budget(
        total_duration_sec=7200,
        disc_type=DiscType.BD25,
        audio_tracks_kbps=[640],
        video_count=1,
    )
    assert 20000 <= budget.video_bitrate_kbps <= 30000
    assert budget.total_bitrate_kbps <= 40000
    assert budget.fits_disc is True


def test_bd50_clamping_short_video():
    # 5 minute video (300 sec) on BD-50 should clamp to max BD bitrate (35000 kbps)
    budget = calculate_bitrate_budget(
        total_duration_sec=300,
        disc_type=DiscType.BD50,
        audio_tracks_kbps=[640],
        video_count=1,
    )
    assert budget.video_bitrate_kbps == 35000
    assert budget.fits_disc is True


def test_bdxl_bd100_and_bd128_calculation():
    # 6 hour 4K/HD collection (21600 sec) on BD-100
    budget_100 = calculate_bitrate_budget(
        total_duration_sec=21600,
        disc_type=DiscType.BD100,
        audio_tracks_kbps=[640],
        video_count=6,
    )
    assert budget_100.target_capacity_mb == 92000.0
    assert budget_100.video_bitrate_kbps > 25000
    assert budget_100.fits_disc is True

    # 10 hour TV series (36000 sec) on BD-128
    budget_128 = calculate_bitrate_budget(
        total_duration_sec=36000,
        disc_type=DiscType.BD128,
        audio_tracks_kbps=[640],
        video_count=10,
    )
    assert budget_128.target_capacity_mb == 118000.0
    assert budget_128.video_bitrate_kbps > 20000
    assert budget_128.fits_disc is True


def test_zero_or_negative_duration_handling():
    budget = calculate_bitrate_budget(
        total_duration_sec=0,
        disc_type=DiscType.DVD5,
    )
    assert budget.video_bitrate_kbps == 8000
    assert budget.fits_disc is True


def test_default_and_multiple_audio_tracks():
    # Default audio track
    budget_default = calculate_bitrate_budget(
        total_duration_sec=3600,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=None,
    )
    assert budget_default.audio_bitrate_kbps == 192

    # Multiple audio tracks (e.g. 5.1 AC3 448k + Commentary 192k)
    budget_multi = calculate_bitrate_budget(
        total_duration_sec=3600,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[448, 192],
    )
    assert budget_multi.audio_bitrate_kbps == 640


def test_total_bitrate_cap_enforced():
    # If audio is very high (e.g. 2000 kbps), video is capped so total does not exceed max
    budget = calculate_bitrate_budget(
        total_duration_sec=300,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[2000],
    )
    assert budget.video_bitrate_kbps + budget.audio_bitrate_kbps <= DVD_MAX_TOTAL_BITRATE


def test_model_serialization_and_enums():
    info = MediaInfo(
        path="/media/test.mkv",
        filename="test.mkv",
        duration_sec=120.5,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="h264",
        audio_streams=[
            AudioStreamInfo(
                index=1,
                codec_name="ac3",
                channels=6,
                channel_layout="5.1",
                language="eng",
            )
        ],
        subtitle_streams=[
            SubtitleStreamInfo(index=2, codec_name="subrip", language="eng")
        ],
        chapters_count=5,
        size_bytes=1024000,
    )
    data = info.model_dump()
    assert data["filename"] == "test.mkv"
    assert len(data["audio_streams"]) == 1
    assert data["audio_streams"][0]["codec_name"] == "ac3"

    cfg = ProjectConfig(
        input_files=["/media/test.mkv"],
        disc_type=DiscType.BD25,
        output_mode=OutputMode.AUTHOR_AND_BURN,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.MENU,
    )
    assert cfg.disc_type == DiscType.BD25
    assert cfg.menu_mode == MenuMode.MENU


def test_config_settings(monkeypatch):
    monkeypatch.setenv("DVDCOMPRESS_MEDIA_DIR", "/custom/media")
    monkeypatch.setenv("DVDCOMPRESS_PORT", "9090")
    custom_settings = Settings()
    assert str(custom_settings.media_dir) == "/custom/media"
    assert custom_settings.port == 9090
