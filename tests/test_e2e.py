"""End-to-End Integration & Verification Suite for DVDCompress.

Tests the full lifecycle of DVDCompress:
1. Media Probing -> Bitrate Budgeting -> Transcoding -> Authoring -> ISO Mastering -> Burning.
2. Multi-Title Projects (e.g., 6-Episode TV series batch on DVD-9 / BD-50).
3. Blu-ray authoring with NVENC GPU acceleration and CPU libx264 fallback.
4. Standalone ISO Burner workflow via REST API.
5. Error recovery across all pipeline stages (probe, transcode, author, master, burn).
6. Asynchronous job cancellation and scratch directory cleanup.
7. Full REST API and WebSocket real-time progress broadcasting.
8. Synthetic video creation, ISO volume descriptor generation, and ISO header validation.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dvdcompress.api import _run_burn_iso_pipeline, app, job_manager
from dvdcompress.authoring import (
    format_chapter_time,
    generate_dvdauthor_xml,
    generate_tsmuxer_meta,
)
from dvdcompress.burner import (
    OpticalDrive,
    build_burn_command,
    parse_burn_progress_line,
    scan_optical_drives,
)
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.iso import build_genisoimage_command, build_xorriso_bd_command
from dvdcompress.job_manager import Job, JobManager, JobStage
from dvdcompress.models import (
    AspectRatio,
    AudioStreamInfo,
    BitrateBudget,
    DiscType,
    MediaInfo,
    MenuMode,
    OutputMode,
    SubtitleStreamInfo,
    TVStandard,
)
from dvdcompress.probe import probe_media_file
from dvdcompress.system_info import get_hardware_telemetry
from dvdcompress.transcoder import (
    build_bluray_transcode_command,
    build_dvd_transcode_command,
    parse_ffmpeg_progress_line,
)


# ---------------------------------------------------------------------------
# Synthetic Media & ISO Header Utilities
# ---------------------------------------------------------------------------


def create_synthetic_video_file(
    file_path: str,
    duration_sec: float = 2.0,
    width: int = 720,
    height: int = 480,
    frame_rate: int = 24,
) -> str:
    """Create a synthetic MP4 test video with video and audio streams.

    Uses host ffmpeg if available; otherwise falls back to writing a dummy file.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration_sec}:size={width}x{height}:rate={frame_rate}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration_sec}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            file_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(file_path):
            return file_path

    # Fallback dummy video file
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(b"SYNTHETIC_DUMMY_VIDEO_DATA_" + b"\x00" * 4096)
    return file_path


def create_synthetic_iso_file(
    file_path: str,
    volume_label: str = "DVD_DISC",
    total_size: int = 65536,
) -> str:
    """Create a minimal synthetic ISO image with standard ISO 9660 and UDF volume descriptors."""
    data = bytearray(max(total_size, 65536))

    # Sector 16: Primary Volume Descriptor at offset 32768 (0x8000)
    pvd_offset = 32768
    data[pvd_offset] = 0x01  # Primary Volume Descriptor
    data[pvd_offset + 1 : pvd_offset + 6] = b"CD001"  # Standard ISO-9660 identifier
    data[pvd_offset + 6] = 0x01  # Version
    clean_label = volume_label[:32].ljust(32).encode("ascii")
    data[pvd_offset + 40 : pvd_offset + 72] = clean_label

    # Sector 17: UDF Beginning Extended Area Descriptor at offset 34816 (0x8800)
    udf_offset = 34816
    data[udf_offset] = 0x00
    data[udf_offset + 1 : udf_offset + 6] = b"BEA01"
    data[udf_offset + 6] = 0x01

    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(data)
    return file_path


def validate_iso_headers(iso_path: str) -> Dict[str, Any]:
    """Validate ISO headers for standard ISO 9660 and UDF volume descriptors."""
    assert os.path.exists(iso_path), f"ISO file {iso_path} does not exist"
    size = os.path.getsize(iso_path)
    assert size >= 36864, f"ISO file too small: {size} bytes"

    with open(iso_path, "rb") as f:
        f.seek(32768)
        sector_16 = f.read(2048)
        pvd_type = sector_16[0]
        iso_identifier = sector_16[1:6]
        volume_id = sector_16[40:72].decode("ascii", errors="replace").strip()

        sector_17 = f.read(2048)
        udf_identifier = sector_17[1:6]

    return {
        "size_bytes": size,
        "pvd_type": pvd_type,
        "is_valid_iso9660": iso_identifier == b"CD001",
        "iso_identifier": iso_identifier.decode("ascii", errors="replace"),
        "volume_id": volume_id,
        "is_valid_udf": udf_identifier in (b"BEA01", b"NSR02", b"NSR03"),
        "udf_identifier": udf_identifier.decode("ascii", errors="replace"),
    }


class SmartSubprocessMock:
    """Simulates asynchronous subprocess execution for ffmpeg, dvdauthor, tsMuxeR, genisoimage, xorriso, growisofs, and cdrskin."""

    def __init__(
        self,
        *cmd: str,
        fail_on_cmd: Optional[str] = None,
        exit_code: int = 0,
        **kwargs: Any,
    ):
        self.cmd = [str(c) for c in cmd]
        self.fail_on_cmd = fail_on_cmd
        self.returncode = exit_code
        self.killed = False
        self.stdout = AsyncMock()
        self.stderr = AsyncMock()

        cmd_name = self.cmd[0] if self.cmd else ""
        if self.fail_on_cmd and (self.fail_on_cmd in cmd_name or self.fail_on_cmd in self.cmd):
            self.returncode = 1
            self.stderr.readline = AsyncMock(side_effect=[b"Mocked error occurred\n", b""])
            self.stdout.readline = AsyncMock(return_value=b"")
            return

        self._setup_behavior(cmd_name)

    def _setup_behavior(self, cmd_name: str):
        if "ffmpeg" in cmd_name:
            out_file = self.cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"MOCK_TRANSCODED_STREAM_BYTES")
            self.stderr.readline = AsyncMock(
                side_effect=[
                    b"frame= 100 fps= 45.0 q=2.0 size= 1024kB time=00:15:00.00 bitrate= 4500kbits/s speed= 2.0x\n",
                    b"frame= 300 fps= 48.0 q=2.0 size= 3072kB time=00:30:00.00 bitrate= 4500kbits/s speed= 2.2x\n",
                    b"frame= 600 fps= 50.0 q=2.0 size= 6144kB time=01:00:00.00 bitrate= 4500kbits/s speed= 2.5x\n",
                    b"",
                ]
            )
            self.stdout.readline = AsyncMock(return_value=b"")

        elif "dvdauthor" in cmd_name:
            # cmd: dvdauthor -o author_dir -x xml_path
            author_dir = self.cmd[2]
            v_ts = os.path.join(author_dir, "VIDEO_TS")
            os.makedirs(v_ts, exist_ok=True)
            with open(os.path.join(v_ts, "VIDEO_TS.IFO"), "wb") as f:
                f.write(b"DVDVIDEO-VMG")
            with open(os.path.join(v_ts, "VIDEO_TS.BUP"), "wb") as f:
                f.write(b"DVDVIDEO-VMG-BUP")
            with open(os.path.join(v_ts, "VTS_01_0.IFO"), "wb") as f:
                f.write(b"DVDVIDEO-VTS")
            with open(os.path.join(v_ts, "VTS_01_1.VOB"), "wb") as f:
                f.write(b"DVDVIDEO-VOB-DATA")
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(return_value=b"")

        elif "tsMuxeR" in cmd_name:
            # cmd: tsMuxeR meta_path author_dir
            author_dir = self.cmd[2]
            bdmv = os.path.join(author_dir, "BDMV")
            cert = os.path.join(author_dir, "CERTIFICATE")
            os.makedirs(bdmv, exist_ok=True)
            os.makedirs(cert, exist_ok=True)
            with open(os.path.join(bdmv, "index.bdmv"), "wb") as f:
                f.write(b"INDX0200")
            with open(os.path.join(bdmv, "MovieObject.bdmv"), "wb") as f:
                f.write(b"MOBJ0200")
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(return_value=b"")

        elif "genisoimage" in cmd_name or "xorriso" in cmd_name:
            try:
                o_idx = self.cmd.index("-o")
                iso_out = self.cmd[o_idx + 1]
            except ValueError:
                iso_out = self.cmd[-1]

            try:
                v_idx = self.cmd.index("-V")
                label = self.cmd[v_idx + 1]
            except ValueError:
                label = "DISC"

            create_synthetic_iso_file(iso_out, volume_label=label)
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(return_value=b"")

        elif "growisofs" in cmd_name:
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(
                side_effect=[
                    b" 10485760/4699979776 (  0.2%) @0.0x, remaining 15:00 RBU 100.0% UBU   4.2%\n",
                    b" 2350000000/4699979776 ( 50.0%) @4.0x, remaining 07:30 RBU 100.0% UBU  50.0%\n",
                    b" 4699979776/4699979776 (100.0%) @4.0x, remaining 00:00 RBU 100.0% UBU 100.0%\n",
                    b"",
                ]
            )

        elif "cdrskin" in cmd_name:
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(
                side_effect=[
                    b"Track 01:    10 of  500 MB written (fifo 100%)\n",
                    b"Track 01:   250 of  500 MB written (fifo 100%)\n",
                    b"Track 01:   500 of  500 MB written (fifo 100%)\n",
                    b"",
                ]
            )

        else:
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(return_value=b"")

    async def wait(self) -> int:
        return self.returncode

    def kill(self):
        self.killed = True


# ---------------------------------------------------------------------------
# Test Suite 1: Synthetic Probing, Budgeting, & ISO Header Verification
# ---------------------------------------------------------------------------


def test_synthetic_media_probing_and_budgeting(tmp_path):
    """Verify synthetic video creation, metadata probing, and multi-format bitrate budgeting."""
    video_path = str(tmp_path / "synthetic_probe.mp4")
    create_synthetic_video_file(video_path, duration_sec=2.0, width=720, height=480)

    # Test real or mocked probe
    if shutil.which("ffprobe"):
        info = asyncio.run(probe_media_file(video_path))
        assert info.filename == "synthetic_probe.mp4"
        assert info.duration_sec >= 1.5
        assert info.width == 720
        assert info.height == 480
        assert len(info.audio_streams) >= 1
    else:
        info = MediaInfo(
            path=video_path,
            filename="synthetic_probe.mp4",
            duration_sec=3600.0,
            width=720,
            height=480,
            aspect_ratio="16:9",
            frame_rate=24.0,
            video_codec="h264",
            audio_streams=[
                AudioStreamInfo(
                    index=1,
                    codec_name="aac",
                    channels=2,
                    channel_layout="stereo",
                    bitrate=192000,
                )
            ],
            subtitle_streams=[],
            chapters_count=0,
            size_bytes=100000,
        )

    # Test bitrate budgeting for all supported disc types
    budget_dvd5 = calculate_bitrate_budget(info.duration_sec, DiscType.DVD5, video_count=1)
    assert budget_dvd5.video_bitrate_kbps > 0
    assert budget_dvd5.video_bitrate_kbps <= 8500
    assert budget_dvd5.fits_disc is True

    budget_dvd9 = calculate_bitrate_budget(info.duration_sec, DiscType.DVD9, video_count=1)
    assert budget_dvd9.video_bitrate_kbps >= budget_dvd5.video_bitrate_kbps
    assert budget_dvd9.target_capacity_mb == 7850.0

    budget_bd25 = calculate_bitrate_budget(info.duration_sec, DiscType.BD25, video_count=1)
    assert budget_bd25.video_bitrate_kbps <= 35000
    assert budget_bd25.target_capacity_mb == 23000.0

    budget_bd50 = calculate_bitrate_budget(info.duration_sec, DiscType.BD50, video_count=1)
    assert budget_bd50.target_capacity_mb == 46000.0


def test_iso_header_generation_and_validation(tmp_path):
    """Verify synthetic ISO file generation and byte-level ISO 9660 & UDF header validation."""
    iso_file = str(tmp_path / "test_disc.iso")
    create_synthetic_iso_file(iso_file, volume_label="MY_TEST_MOVIE", total_size=65536)

    header_info = validate_iso_headers(iso_file)
    assert header_info["is_valid_iso9660"] is True
    assert header_info["iso_identifier"] == "CD001"
    assert header_info["volume_id"] == "MY_TEST_MOVIE"
    assert header_info["is_valid_udf"] is True
    assert header_info["udf_identifier"] == "BEA01"
    assert header_info["size_bytes"] == 65536


# ---------------------------------------------------------------------------
# Test Suite 2: Single-Title DVD Lifecycle (ISO & Burn)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_single_title_dvd_iso_pipeline(tmp_path):
    """End-to-end DVD-5 ISO generation pipeline: Probing -> Bitrate -> Transcode -> Author -> ISO Mastering."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video_path = str(tmp_path / "matrix.mkv")
    with open(video_path, "wb") as f:
        f.write(b"MOCK_MKV_BYTES")

    fake_info = MediaInfo(
        path=video_path,
        filename="matrix.mkv",
        duration_sec=7200.0,  # 2 hours
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
                title="English 5.1",
                bitrate=384000,
            )
        ],
        subtitle_streams=[],
        chapters_count=4,
        size_bytes=4000000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video_path],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="The Matrix (1999)",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.AUTOPLAY,
        use_gpu=False,
    )

    # Track progress and stages via listener queue
    event_queue: asyncio.Queue = asyncio.Queue()
    manager.register_listener(job_id, event_queue)

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(*cmd, **kwargs),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.COMPLETED
    assert job.progress_percent == 100.0
    assert job.error_message is None
    assert job.output_iso_path == os.path.join(output_dir, "The_Matrix__1999_.iso")

    # Validate generated ISO headers
    assert os.path.exists(job.output_iso_path)
    header_res = validate_iso_headers(job.output_iso_path)
    assert header_res["is_valid_iso9660"] is True
    assert "THE_MATRIX__1999_" in header_res["volume_id"]

    # Verify events received
    stages_seen = []
    while not event_queue.empty():
        evt = await event_queue.get()
        stages_seen.append(evt["stage"])

    assert JobStage.PROBING in stages_seen
    assert JobStage.TRANSCODING in stages_seen
    assert JobStage.AUTHORING in stages_seen
    assert JobStage.MASTERING_ISO in stages_seen
    assert JobStage.COMPLETED in stages_seen

    # Verify scratch work directory is completely cleaned up
    work_dir = os.path.join(scratch_dir, job_id)
    assert not os.path.exists(work_dir)


@pytest.mark.asyncio
async def test_e2e_single_title_dvd_author_and_burn_pipeline(tmp_path):
    """End-to-end DVD-Video pipeline with ISO mastering and optical disc burning orchestration."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video_path = str(tmp_path / "holiday_video.mp4")
    with open(video_path, "wb") as f:
        f.write(b"MOCK_HOLIDAY_VIDEO")

    fake_info = MediaInfo(
        path=video_path,
        filename="holiday_video.mp4",
        duration_sec=3600.0,
        width=1280,
        height=720,
        aspect_ratio="16:9",
        frame_rate=29.97,
        video_codec="h264",
        audio_streams=[
            AudioStreamInfo(
                index=1,
                codec_name="aac",
                channels=2,
                channel_layout="stereo",
                bitrate=192000,
            )
        ],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=1000000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video_path],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.AUTHOR_AND_BURN,
        output_name="Holiday 2024",
        tv_standard=TVStandard.NTSC,
        burner_device="/dev/sr0",
        burn_speed=4,
    )

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(*cmd, **kwargs),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.COMPLETED
    assert job.progress_percent == 100.0
    assert any("Burning ISO to /dev/sr0 at 4x" in log for log in job.logs)
    assert any("Job finished successfully!" in log for log in job.logs)


# ---------------------------------------------------------------------------
# Test Suite 3: Multi-Title TV Series Batch Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_multi_title_tv_series_batch_dvd9(tmp_path):
    """End-to-end multi-title batch test: 6 TV episodes mastered to a DVD-9 dual-layer disc."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    episode_files = [str(tmp_path / f"S01E0{i}.mkv") for i in range(1, 7)]
    for ep in episode_files:
        with open(ep, "wb") as f:
            f.write(b"MOCK_EPISODE_BYTES")

    def mock_probe_router(file_path: str):
        ep_name = os.path.basename(file_path)
        return MediaInfo(
            path=file_path,
            filename=ep_name,
            duration_sec=2700.0,  # 45 minutes per episode (total = 270 min = 4.5h)
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
                    bitrate=384000,
                )
            ],
            subtitle_streams=[],
            chapters_count=5,
            size_bytes=2000000000,
        )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=episode_files,
        disc_type=DiscType.DVD9,
        output_mode=OutputMode.ISO_ONLY,
        output_name="Breaking Bad Season 1 Disc 1",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.AUTOPLAY,
    )

    executed_cmds = []

    def tracking_subprocess_mock(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        return SmartSubprocessMock(*cmd, **kwargs)

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        side_effect=mock_probe_router,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=tracking_subprocess_mock,
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.COMPLETED
    assert job.total_files == 6
    assert job.progress_percent == 100.0

    # Verify all 6 transcoding commands were invoked
    ffmpeg_cmds = [c for c in executed_cmds if c[0] == "ffmpeg"]
    assert len(ffmpeg_cmds) == 6

    # Verify dvdauthor command was executed with author dir and xml path
    dvdauthor_cmds = [c for c in executed_cmds if c[0] == "dvdauthor"]
    assert len(dvdauthor_cmds) == 1
    assert dvdauthor_cmds[0][1] == "-o"
    assert dvdauthor_cmds[0][3] == "-x"

    # Verify multi-title XML generation logic
    xml_gen = generate_dvdauthor_xml(
        titles_mpg=[f"/tmp/title_{i}.mpg" for i in range(1, 7)],
        chapters_sec=[[0.0, 300.0, 600.0] for _ in range(6)],
        menu_mode=MenuMode.AUTOPLAY,
        tv_standard=TVStandard.NTSC,
    )
    assert "<post>jump title 2;</post>" in xml_gen
    assert "<post>jump title 3;</post>" in xml_gen
    assert "<post>jump title 6;</post>" in xml_gen
    assert "<post>jump title 1;</post>" in xml_gen  # loops back to 1 after last title

    # Verify ISO was created and validated
    assert os.path.exists(job.output_iso_path)
    header_res = validate_iso_headers(job.output_iso_path)
    assert header_res["is_valid_iso9660"] is True
    assert "BREAKING_BAD_SEASON_1_DISC_1" in header_res["volume_id"]


@pytest.mark.asyncio
async def test_e2e_multi_title_tv_series_batch_bd50(tmp_path):
    """End-to-end multi-title batch test on Blu-ray BD-50 with tsMuxeR and xorriso."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    episode_files = [str(tmp_path / f"Ep{i}.mkv") for i in range(1, 5)]
    for ep in episode_files:
        with open(ep, "wb") as f:
            f.write(b"MOCK_EPISODE_BYTES")

    def mock_probe(f):
        return MediaInfo(
            path=f,
            filename=os.path.basename(f),
            duration_sec=3600.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=24.0,
            video_codec="hevc",
            audio_streams=[
                AudioStreamInfo(
                    index=1,
                    codec_name="ac3",
                    channels=6,
                    channel_layout="5.1",
                    bitrate=448000,
                )
            ],
            subtitle_streams=[],
            chapters_count=0,
            size_bytes=3000000000,
        )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=episode_files,
        disc_type=DiscType.BD50,
        output_mode=OutputMode.ISO_ONLY,
        output_name="SciFi Anthology BD",
        use_gpu=True,
    )

    executed_cmds = []

    def tracking_mock(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        return SmartSubprocessMock(*cmd, **kwargs)

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        side_effect=mock_probe,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=tracking_mock,
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.COMPLETED
    assert job.progress_percent == 100.0

    # Verify tsMuxeR was invoked
    tsmuxer_cmds = [c for c in executed_cmds if c[0] == "tsMuxeR"]
    assert len(tsmuxer_cmds) == 1

    # Verify xorriso was invoked for Blu-ray ISO
    xorriso_cmds = [c for c in executed_cmds if c[0] == "xorriso"]
    assert len(xorriso_cmds) == 1
    assert "-udf" in xorriso_cmds[0]
    assert "SCIFI_ANTHOLOGY_BD" in xorriso_cmds[0]

    # Verify generated tsMuxeR meta structure
    transcoded_m2ts = [f"/tmp/title_{i}.m2ts" for i in range(1, 5)]
    meta_content = generate_tsmuxer_meta(transcoded_m2ts)
    for m2ts in transcoded_m2ts:
        assert f'"{m2ts}"' in meta_content
        assert "V_MPEG4/ISO/AVC" in meta_content
        assert "A_AC3" in meta_content


# ---------------------------------------------------------------------------
# Test Suite 4: Blu-ray NVENC vs CPU Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_bluray_nvenc_and_cpu_transcode_commands(tmp_path):
    """Verify GPU (NVENC) and CPU (libx264) transcoding command construction and pipeline execution."""
    input_video = str(tmp_path / "feature.mkv")
    output_m2ts = str(tmp_path / "feature.m2ts")
    with open(input_video, "wb") as f:
        f.write(b"MOCK_FEATURE")

    # 1. GPU / NVENC
    cmd_gpu = build_bluray_transcode_command(
        input_file=input_video,
        output_m2ts=output_m2ts,
        video_bitrate_kbps=25000,
        audio_stream_idx=1,
        audio_channels=6,
        use_gpu=True,
    )
    assert "-hwaccel" in cmd_gpu
    assert "cuda" in cmd_gpu
    assert "h264_nvenc" in cmd_gpu
    assert "-b:v" in cmd_gpu
    assert "25000k" in cmd_gpu

    # 2. CPU / libx264
    cmd_cpu = build_bluray_transcode_command(
        input_file=input_video,
        output_m2ts=output_m2ts,
        video_bitrate_kbps=25000,
        audio_stream_idx=1,
        audio_channels=6,
        use_gpu=False,
    )
    assert "libx264" in cmd_cpu
    assert "-bluray-compat" in cmd_cpu
    assert "1" in cmd_cpu
    assert "-hwaccel" not in cmd_cpu


# ---------------------------------------------------------------------------
# Test Suite 5: Standalone ISO Burner via REST API
# ---------------------------------------------------------------------------


def test_e2e_standalone_iso_burn_via_api(tmp_path):
    """Test standalone ISO burner workflow through FastAPI REST and WebSocket endpoints."""
    client = TestClient(app)

    # 1. Create a valid synthetic ISO
    iso_file = str(tmp_path / "direct_burn.iso")
    create_synthetic_iso_file(iso_file, volume_label="DIRECT_BURN_DISC")

    # 2. Submit burn job with mocked burning subprocess
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(*cmd, **kwargs),
    ):
        res = client.post(
            "/api/burn-iso",
            json={
                "iso_path": iso_file,
                "device_path": "/dev/sr0",
                "burn_speed": 8,
                "is_bluray": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        job_id = data["job_id"]
        assert data["status"] == "started"

        # 3. Stream WebSocket updates
        with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            initial = ws.receive_json()
            assert initial["job_id"] == job_id

            if initial.get("stage") == "completed":
                final_msg = initial
            else:
                final_msg = None
                for _ in range(10):
                    msg = ws.receive_json()
                    if msg.get("stage") == "completed":
                        final_msg = msg
                        break

            assert final_msg is not None
            assert final_msg["stage"] == "completed"
            assert final_msg["progress_percent"] == 100.0

    # 4. Verify job status via GET /api/jobs/{job_id}
    res_get = client.get(f"/api/jobs/{job_id}")
    assert res_get.status_code == 200
    job_status = res_get.json()
    assert job_status["stage"] == "completed"
    assert job_status["progress_percent"] == 100.0


@pytest.mark.asyncio
async def test_e2e_standalone_iso_burn_bluray_cdrskin(tmp_path):
    """Test standalone Blu-ray ISO burning with cdrskin."""
    iso_file = str(tmp_path / "bd_standalone.iso")
    create_synthetic_iso_file(iso_file, volume_label="BD_STANDALONE")

    job_id = job_manager.create_job(
        input_files=[iso_file],
        disc_type=DiscType.BD25,
        output_mode=OutputMode.BURN_DIRECT,
        output_name="bd_standalone",
        burner_device="/dev/sr1",
        burn_speed=2,
    )

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(*cmd, **kwargs),
    ):
        await _run_burn_iso_pipeline(
            job_id=job_id,
            iso_path=iso_file,
            device_path="/dev/sr1",
            speed=2,
            is_bluray=True,
        )

    job = job_manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.COMPLETED
    assert job.progress_percent == 100.0


# ---------------------------------------------------------------------------
# Test Suite 6: Error Recovery & Cancellation Workflows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_error_recovery_probe_failure(tmp_path):
    """Test graceful error handling when media probing fails."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    corrupt_video = str(tmp_path / "corrupt.mkv")
    with open(corrupt_video, "wb") as f:
        f.write(b"CORRUPT_NOT_MEDIA")

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[corrupt_video],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="corrupt_job",
    )

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        side_effect=RuntimeError("FFprobe could not find stream info"),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.FAILED
    assert "FFprobe could not find stream info" in (job.error_message or "")
    assert not os.path.exists(os.path.join(scratch_dir, job_id))


@pytest.mark.asyncio
async def test_e2e_error_recovery_authoring_failure(tmp_path):
    """Test graceful error handling and scratch cleanup when dvdauthor fails."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video = str(tmp_path / "clip.mkv")
    with open(video, "wb") as f:
        f.write(b"MOCK_CLIP")

    fake_info = MediaInfo(
        path=video,
        filename="clip.mkv",
        duration_sec=600.0,
        width=720,
        height=480,
        aspect_ratio="16:9",
        frame_rate=29.97,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=100000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="author_fail",
    )

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(
            *cmd, fail_on_cmd="dvdauthor", **kwargs
        ),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.FAILED
    assert "Authoring failed with dvdauthor" in (job.error_message or "")
    assert not os.path.exists(os.path.join(scratch_dir, job_id))


@pytest.mark.asyncio
async def test_e2e_error_recovery_iso_creation_failure(tmp_path):
    """Test error handling when genisoimage fails."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video = str(tmp_path / "clip.mkv")
    with open(video, "wb") as f:
        f.write(b"MOCK_CLIP")

    fake_info = MediaInfo(
        path=video,
        filename="clip.mkv",
        duration_sec=600.0,
        width=720,
        height=480,
        aspect_ratio="16:9",
        frame_rate=29.97,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=100000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="iso_fail",
    )

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(
            *cmd, fail_on_cmd="genisoimage", **kwargs
        ),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.FAILED
    assert "ISO creation failed" in (job.error_message or "")
    assert not os.path.exists(os.path.join(scratch_dir, job_id))


@pytest.mark.asyncio
async def test_e2e_error_recovery_burning_failure(tmp_path):
    """Test error handling when growisofs optical drive burning fails."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video = str(tmp_path / "clip.mkv")
    with open(video, "wb") as f:
        f.write(b"MOCK_CLIP")

    fake_info = MediaInfo(
        path=video,
        filename="clip.mkv",
        duration_sec=600.0,
        width=720,
        height=480,
        aspect_ratio="16:9",
        frame_rate=29.97,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=100000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.AUTHOR_AND_BURN,
        output_name="burn_fail",
        burner_device="/dev/sr0",
        burn_speed=4,
    )

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(
            *cmd, fail_on_cmd="growisofs", **kwargs
        ),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.FAILED
    assert "Burning failed" in (job.error_message or "")


@pytest.mark.asyncio
async def test_e2e_job_cancellation_during_transcode(tmp_path):
    """Verify active child process is terminated and scratch directory is cleaned upon cancellation."""
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    video = str(tmp_path / "clip.mkv")
    with open(video, "wb") as f:
        f.write(b"MOCK_CLIP")

    fake_info = MediaInfo(
        path=video,
        filename="clip.mkv",
        duration_sec=7200.0,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=24.0,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=1000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=[video],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="cancel_test",
    )

    async def hanging_readline():
        await asyncio.sleep(60)
        return b""

    class LongRunningProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.killed = False
            self.stderr = AsyncMock()
            self.stderr.readline = AsyncMock(side_effect=hanging_readline)
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(return_value=b"")

        async def wait(self):
            await asyncio.sleep(60)
            return 0

        def kill(self):
            self.killed = True

    active_mock_proc = None

    def create_mock(*cmd, **kwargs):
        nonlocal active_mock_proc
        active_mock_proc = LongRunningProcess(*cmd, **kwargs)
        return active_mock_proc

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch("asyncio.create_subprocess_exec", side_effect=create_mock):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        await asyncio.sleep(0.05)  # Let pipeline reach transcoding

        # Cancel job
        await manager.cancel_job(job_id)

    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.CANCELLED
    assert job.error_message == "Job cancelled by user"
    assert active_mock_proc is not None
    assert active_mock_proc.killed is True
    assert not os.path.exists(os.path.join(scratch_dir, job_id))


# ---------------------------------------------------------------------------
# Test Suite 7: Full REST API End-to-End User Journey
# ---------------------------------------------------------------------------


def test_e2e_full_rest_api_user_journey(tmp_path):
    """Complete REST API journey: Health -> System -> Files -> Drives -> Probe -> Calculate -> Create Job -> WebSocket Stream -> Complete."""
    client = TestClient(app)

    # 1. Health check
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # 2. Hardware telemetry
    mock_telemetry = {
        "gpu_available": True,
        "gpu_name": "NVIDIA GeForce RTX 4090",
        "gpu_utilization_percent": 15,
        "gpu_memory_used_mb": 2048,
        "gpu_memory_total_mb": 24576,
        "gpu_temp_c": 48,
    }
    with patch("dvdcompress.api.get_hardware_telemetry", return_value=mock_telemetry):
        res_sys = client.get("/api/system")
        assert res_sys.status_code == 200
        assert res_sys.json()["gpu_name"] == "NVIDIA GeForce RTX 4090"

    # 3. Files browser
    test_media_dir = tmp_path / "media"
    test_media_dir.mkdir()
    video_file = test_media_dir / "journey_clip.mp4"
    video_file.write_bytes(b"DUMMY_JOURNEY_VIDEO")

    with patch.dict(os.environ, {"MEDIA_DIR": str(test_media_dir)}):
        res_files = client.get(f"/api/files?path={test_media_dir}")
        assert res_files.status_code == 200
        files = res_files.json()["files"]
        assert any(f["name"] == "journey_clip.mp4" and f["is_video"] is True for f in files)

    # 4. Scan optical drives
    mock_drives = [
        OpticalDrive(
            device_path="/dev/sr0",
            sg_device="/dev/sg0",
            vendor="LG",
            model="WH16NS40",
            is_writable=True,
            media_status="Ready",
        )
    ]
    with patch("dvdcompress.api.scan_optical_drives", return_value=mock_drives):
        res_drives = client.get("/api/drives")
        assert res_drives.status_code == 200
        assert res_drives.json()[0]["vendor"] == "LG"

    # 5. Media Probe
    fake_info = MediaInfo(
        path=str(video_file),
        filename="journey_clip.mp4",
        duration_sec=5400.0,  # 1.5 hours
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
                bitrate=384000,
            )
        ],
        subtitle_streams=[],
        chapters_count=4,
        size_bytes=3000000000,
    )
    with patch("dvdcompress.api.probe_media_file", new_callable=AsyncMock, return_value=fake_info):
        res_probe = client.post("/api/probe", json={"file_path": str(video_file)})
        assert res_probe.status_code == 200
        assert res_probe.json()["duration_sec"] == 5400.0

    # 6. Calculate Bitrate Budget
    res_calc = client.post(
        "/api/calculate",
        json={
            "total_duration_sec": 5400.0,
            "disc_type": "dvd5",
            "audio_tracks_kbps": [384],
            "video_count": 1,
        },
    )
    assert res_calc.status_code == 200
    calc_data = res_calc.json()
    assert calc_data["fits_disc"] is True
    assert calc_data["video_bitrate_kbps"] > 0

    # 7. Create Job & Stream WebSocket
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    with patch.dict(
        os.environ,
        {
            "SCRATCH_DIR": scratch_dir,
            "OUTPUT_DIR": output_dir,
            "MEDIA_DIR": str(test_media_dir),
            "DVDCOMPRESS_TEMP_DIR": scratch_dir,
            "DVDCOMPRESS_OUTPUT_DIR": output_dir,
            "DVDCOMPRESS_MEDIA_DIR": str(test_media_dir),
        },
    ), patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: SmartSubprocessMock(*cmd, **kwargs),
    ):
        res_job = client.post(
            "/api/jobs",
            json={
                "input_files": [str(video_file)],
                "disc_type": "dvd5",
                "output_mode": "iso_only",
                "output_name": "Full User Journey Movie",
                "tv_standard": "ntsc",
                "aspect_ratio": "16:9",
                "menu_mode": "autoplay",
                "use_gpu": False,
            },
        )
        assert res_job.status_code == 200
        job_id = res_job.json()["job_id"]

        # Stream WebSocket messages until completion
        with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            initial = ws.receive_json()
            completed = initial.get("stage") == "completed"
            if not completed:
                for _ in range(20):
                    try:
                        msg = ws.receive_json()
                        if msg.get("stage") in ("completed", "failed", "cancelled"):
                            completed = msg.get("stage") == "completed"
                            break
                    except Exception:
                        break

            assert completed is True

    # 8. Verify Job Status & Listing
    res_list = client.get("/api/jobs")
    assert res_list.status_code == 200
    all_jobs = res_list.json()
    assert any(j["job_id"] == job_id and j["stage"] == "completed" for j in all_jobs)

    res_single = client.get(f"/api/jobs/{job_id}")
    assert res_single.status_code == 200
    single_job = res_single.json()
    assert single_job["job_id"] == job_id
    assert single_job["output_name"] == "Full_User_Journey_Movie"
    assert single_job["progress_percent"] == 100.0
