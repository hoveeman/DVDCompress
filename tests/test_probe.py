import pytest
import json
from unittest.mock import patch, AsyncMock
from dvdcompress.probe import probe_media_file, parse_ffprobe_output, run_ffprobe_json

SAMPLE_FFPROBE_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "display_aspect_ratio": "16:9",
            "r_frame_rate": "24000/1001",
            "duration": "5400.5"
        },
        {
            "codec_type": "audio",
            "index": 1,
            "codec_name": "eac3",
            "channels": 6,
            "channel_layout": "5.1(side)",
            "tags": {"language": "eng", "title": "English 5.1"},
            "bit_rate": "448000"
        },
        {
            "codec_type": "subtitle",
            "index": 2,
            "codec_name": "subrip",
            "tags": {"language": "eng", "title": "English SDH"}
        }
    ],
    "format": {
        "duration": "5400.5",
        "size": "4500000000"
    },
    "chapters": [
        {"id": 0, "start_time": "0.0", "end_time": "300.0"},
        {"id": 1, "start_time": "300.0", "end_time": "600.0"}
    ]
}

def test_parse_ffprobe_output():
    media_info = parse_ffprobe_output("/media/movie.mkv", SAMPLE_FFPROBE_JSON)
    assert media_info.filename == "movie.mkv"
    assert media_info.duration_sec == 5400.5
    assert media_info.width == 1920
    assert media_info.height == 1080
    assert media_info.aspect_ratio == "16:9"
    assert round(media_info.frame_rate, 2) == 23.98
    assert len(media_info.audio_streams) == 1
    assert media_info.audio_streams[0].channels == 6
    assert media_info.audio_streams[0].language == "eng"
    assert media_info.audio_streams[0].bitrate == 448000
    assert len(media_info.subtitle_streams) == 1
    assert media_info.subtitle_streams[0].language == "eng"
    assert media_info.chapters_count == 2
    assert media_info.size_bytes == 4500000000

def test_parse_ffprobe_aspect_ratio_fallback():
    # Test 4:3 derivation when display_aspect_ratio is missing or unknown
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "mpeg2video",
                "width": 640,
                "height": 480,
                "r_frame_rate": "30000/1001",
            }
        ],
        "format": {
            "duration": "100.0",
            "size": "10000"
        }
    }
    media_info = parse_ffprobe_output("/media/classic.avi", data)
    assert media_info.aspect_ratio == "4:3"
    assert round(media_info.frame_rate, 2) == 29.97

def test_parse_ffprobe_video_stream_duration_fallback():
    # Test duration fallback to video stream when format duration is 0
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "duration": "3600.0"
            }
        ],
        "format": {}
    }
    media_info = parse_ffprobe_output("/media/stream_only.mp4", data)
    assert media_info.duration_sec == 3600.0
    assert media_info.aspect_ratio == "16:9"

@pytest.mark.asyncio
async def test_probe_media_file():
    with patch("dvdcompress.probe.run_ffprobe_json", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = SAMPLE_FFPROBE_JSON
        result = await probe_media_file("/media/movie.mkv")
        assert result.filename == "movie.mkv"
        assert result.duration_sec == 5400.5
        assert result.video_codec == "h264"

@pytest.mark.asyncio
async def test_run_ffprobe_json_failure():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"Error: file not found")
    mock_proc.returncode = 1
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc_info:
            await run_ffprobe_json("/nonexistent/file.mkv")
        assert "ffprobe failed on /nonexistent/file.mkv" in str(exc_info.value)

def test_parse_ffprobe_multiple_streams_and_fallbacks():
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "r_frame_rate": "invalid_fraction",
            },
            {
                "codec_type": "audio",
                "index": 1,
                "codec_name": "ac3",
                "channels": 2,
                "tags": None
            },
            {
                "codec_type": "audio",
                "index": 2,
                "codec_name": "dts",
                "channels": 6,
                "channel_layout": "5.1",
                "tags": {"language": "fra", "title": "French DTS"}
            },
            {
                "codec_type": "subtitle",
                "index": 3,
                "codec_name": "subrip",
                "tags": {"language": "spa", "title": "Spanish"}
            },
            {
                "codec_type": "subtitle",
                "index": 4,
                "codec_name": "ass",
                "tags": None
            }
        ],
        "format": {
            "duration": "7200.0",
            "size": "8000000000"
        },
        "chapters": []
    }
    media_info = parse_ffprobe_output("/media/multi.mkv", data)
    assert media_info.filename == "multi.mkv"
    assert media_info.duration_sec == 7200.0
    assert media_info.width == 3840
    assert media_info.height == 2160
    assert media_info.aspect_ratio == "16:9"
    assert media_info.frame_rate == 29.97  # Fallback due to invalid fraction
    assert len(media_info.audio_streams) == 2
    assert media_info.chapters_count == 0


def test_parse_ffprobe_subtitle_disposition():
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
            },
            {
                "codec_type": "subtitle",
                "index": 1,
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "eng", "title": "English Forced"},
                "disposition": {"default": 0, "forced": 1},
            },
            {
                "codec_type": "subtitle",
                "index": 2,
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "English SDH"},
                "disposition": {"default": 1, "forced": 0},
            },
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    media_info = parse_ffprobe_output("/media/sample.mkv", data)
    assert len(media_info.subtitle_streams) == 2
    assert media_info.subtitle_streams[0].codec_name == "hdmv_pgs_subtitle"
    assert media_info.subtitle_streams[0].is_forced is True
    assert media_info.subtitle_streams[0].is_default is False
    assert media_info.subtitle_streams[1].codec_name == "subrip"
    assert media_info.subtitle_streams[1].is_forced is False
    assert media_info.subtitle_streams[1].is_default is True


def test_parse_ffprobe_hdr_detection():
    # 1. HDR10 ST2084 / BT.2020 10-bit
    hdr_data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "pix_fmt": "yuv420p10le",
                "color_primaries": "bt2020",
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
            }
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    info_hdr = parse_ffprobe_output("/media/hdr_movie.mkv", hdr_data)
    assert info_hdr.is_hdr is True
    assert info_hdr.pix_fmt == "yuv420p10le"
    assert info_hdr.color_transfer == "smpte2084"

    # 2. Standard 8-bit SDR
    sdr_data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
            }
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    info_sdr = parse_ffprobe_output("/media/sdr_movie.mp4", sdr_data)
    assert info_sdr.is_hdr is False

    # 3. Dolby Vision Profile 5 with DOVI side data
    dovi_p5_data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "side_data_list": [
                    {
                        "side_data_type": "DOVI configuration record",
                        "dv_profile": 5,
                        "dv_level": 6,
                    }
                ],
            }
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    info_dovi_p5 = parse_ffprobe_output("/media/dovi_p5.mp4", dovi_p5_data)
    assert info_dovi_p5.is_hdr is True

    # 4. Dolby Vision Profile 8 with dvh1 codec tag
    dovi_p8_data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "codec_tag_string": "dvh1",
                "width": 3840,
                "height": 2160,
            }
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    info_dovi_p8 = parse_ffprobe_output("/media/dovi_p8.mkv", dovi_p8_data)
    assert info_dovi_p8.is_hdr is True

    # 5. HLG broadcast HDR (arib-std-b67)
    hlg_data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "color_transfer": "arib-std-b67",
                "color_primaries": "bt2020",
            }
        ],
        "format": {"duration": "100.0", "size": "1000"},
        "chapters": [],
    }
    info_hlg = parse_ffprobe_output("/media/hlg_stream.ts", hlg_data)
    assert info_hlg.is_hdr is True


@pytest.mark.asyncio
async def test_analyze_video_complexity(tmp_path):
    from dvdcompress.models import DiscType, MediaInfo, AudioStreamInfo
    from dvdcompress.probe import analyze_video_complexity
    from unittest.mock import patch, AsyncMock

    test_file = tmp_path / "movie.mkv"
    test_file.write_bytes(b"dummy video")

    mock_info = MediaInfo(
        path=str(test_file),
        filename="movie.mkv",
        duration_sec=6720.0,  # 112 mins
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="hevc",
        audio_streams=[AudioStreamInfo(index=1, codec_name="ac3", channels=6, channel_layout="5.1", bitrate=448000)],
        subtitle_streams=[],
        chapters_count=5,
        chapter_times=[0.0, 600.0, 1200.0],
        size_bytes=1000000000,
    )

    with patch("dvdcompress.probe.probe_media_file", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_info
        with patch("dvdcompress.probe.sample_snippet_bitrate", new_callable=AsyncMock) as mock_sample:
            mock_sample.return_value = 3250.0  # 3,250 kbps measured

            res = await analyze_video_complexity(
                input_files=[str(test_file)],
                disc_type=DiscType.DVD5,
            )

            assert res.empirical_video_bitrate_kbps == 3250
            assert 2.5 <= res.projected_iso_size_gb <= 3.6
            assert res.recommended_disc_type == DiscType.DVD5
            assert "Low" in res.complexity_level or "Clean" in res.complexity_level
            assert res.sample_count > 0


@pytest.mark.asyncio
async def test_analyze_video_complexity_multi_audio_tracks(tmp_path):
    from dvdcompress.models import DiscType, MediaInfo, AudioStreamInfo
    from dvdcompress.probe import analyze_video_complexity
    from unittest.mock import patch, AsyncMock

    test_file = tmp_path / "movie_multiaudio.mkv"
    test_file.write_bytes(b"dummy video")

    # Simulate a Blu-ray rip with 5 audio streams totaling over 12 Mbps
    audio_streams = [
        AudioStreamInfo(index=1, codec_name="truehd", channels=8, bitrate=4500000),
        AudioStreamInfo(index=2, codec_name="dts_hd_ma", channels=6, bitrate=3500000),
        AudioStreamInfo(index=3, codec_name="ac3", channels=6, bitrate=640000),
        AudioStreamInfo(index=4, codec_name="ac3", channels=2, bitrate=192000),
        AudioStreamInfo(index=5, codec_name="ac3", channels=2, bitrate=192000),
    ]

    mock_info = MediaInfo(
        path=str(test_file),
        filename="movie_multiaudio.mkv",
        duration_sec=9654.0,  # 160.9 mins (Harry Potter length)
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="h264",
        audio_streams=audio_streams,
        subtitle_streams=[],
        chapters_count=10,
        chapter_times=[0.0, 600.0, 1200.0],
        size_bytes=30000000000,
    )

    with patch("dvdcompress.probe.probe_media_file", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_info
        with patch("dvdcompress.probe.sample_snippet_bitrate", new_callable=AsyncMock) as mock_sample:
            mock_sample.return_value = 1963.0  # 1,963 kbps empirical VBR

            res = await analyze_video_complexity(
                input_files=[str(test_file)],
                disc_type=DiscType.DVD9,
            )

            assert res.empirical_video_bitrate_kbps == 1963
            # With target AC3 audio at 384 kbps (5.1ch), projected ISO size should be ~2.9 GB, NOT 17.7 GB!
            assert 2.5 <= res.projected_iso_size_gb <= 3.5
            assert res.recommended_disc_type == DiscType.DVD5
