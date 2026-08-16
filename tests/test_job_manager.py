import asyncio
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from dvdcompress.job_manager import Job, JobManager, JobStage
from dvdcompress.models import (
    AspectRatio,
    AudioStreamInfo,
    DiscType,
    MediaInfo,
    MenuMode,
    OutputMode,
    SubtitleStreamInfo,
    TVStandard,
)
from dvdcompress.system_info import get_hardware_telemetry


def test_job_manager_create_and_get_job():
    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/movie1.mkv", "/media/movie2.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="My Special Movie! (2024)",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.AUTOPLAY,
        burner_device=None,
        burn_speed=4,
        use_gpu=True,
    )
    job = manager.get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.stage == JobStage.IDLE
    assert job.output_name == "My_Special_Movie___2024_"
    assert job.total_files == 2
    assert job.disc_type == DiscType.DVD5
    assert job.output_mode == OutputMode.ISO_ONLY

    # Non-existent job
    assert manager.get_job("nonexistent") is None


def test_job_manager_logging_and_truncation():
    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/movie.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="movie",
    )
    job = manager.get_job(job_id)
    assert job is not None

    for i in range(550):
        manager.log(job_id, f"Log message {i}")

    assert len(job.logs) == 500
    assert job.logs[0] == "Log message 50"
    assert job.logs[-1] == "Log message 549"


@pytest.mark.asyncio
async def test_job_manager_listener_and_broadcast():
    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/movie.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_movie",
    )

    q1 = asyncio.Queue()
    q2 = asyncio.Queue()
    manager.register_listener(job_id, q1)
    manager.register_listener(job_id, q2)

    await manager.broadcast(job_id)

    msg1 = await q1.get()
    msg2 = await q2.get()
    assert msg1["job_id"] == job_id
    assert msg1["stage"] == JobStage.IDLE
    assert msg2["job_id"] == job_id

    # Unregister q1
    manager.unregister_listener(job_id, q1)
    job = manager.get_job(job_id)
    assert job is not None
    job.progress_percent = 50.0
    await manager.broadcast(job_id)

    msg2_updated = await q2.get()
    assert msg2_updated["progress_percent"] == 50.0
    assert q1.empty()


def test_hardware_telemetry_nvidia_smi_success():
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
        "subprocess.run"
    ) as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 3080, 42, 2048, 10240, 65\n",
        )
        telemetry = get_hardware_telemetry()
        assert telemetry["gpu_available"] is True
        assert telemetry["gpu_name"] == "NVIDIA GeForce RTX 3080"
        assert telemetry["gpu_utilization_percent"] == 42
        assert telemetry["gpu_memory_used_mb"] == 2048
        assert telemetry["gpu_memory_total_mb"] == 10240
        assert telemetry["gpu_temp_c"] == 65


def test_hardware_telemetry_nvidia_smi_missing_or_error():
    with patch("shutil.which", return_value=None):
        telemetry = get_hardware_telemetry()
        assert telemetry["gpu_available"] is False
        assert telemetry["gpu_name"] is None
        assert telemetry["gpu_utilization_percent"] == 0

    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
        "subprocess.run", side_effect=Exception("Failed execution")
    ):
        telemetry = get_hardware_telemetry()
        assert telemetry["gpu_available"] is False


@pytest.mark.asyncio
async def test_job_pipeline_dvd_iso_success(tmp_path):
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    fake_media_info = MediaInfo(
        path="/media/video1.mkv",
        filename="video1.mkv",
        duration_sec=3600.0,
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
                title="English",
                bitrate=384000,
            )
        ],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=1000000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/video1.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_dvd",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.AUTOPLAY,
    )

    class MockProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.stderr = AsyncMock()
            self.stderr.readline = AsyncMock(
                side_effect=[
                    b"frame= 100 fps= 45.0 q=2.0 size= 1024kB time=00:30:00.00 bitrate= 4500kbits/s speed= 2.1x\n",
                    b"",
                ]
            )
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(return_value=b"")

        async def wait(self):
            return 0

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_media_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: MockProcess(),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        # Wait for task to finish
        task = manager.active_tasks[job_id]
        await task

        job = manager.get_job(job_id)
        assert job is not None
        assert job.stage == JobStage.COMPLETED
        assert job.progress_percent == 100.0
        assert job.error_message is None
        assert job.output_iso_path == os.path.join(output_dir, "test_dvd.iso")
        # Ensure scratch work_dir cleaned up
        assert not os.path.exists(os.path.join(scratch_dir, job_id))


@pytest.mark.asyncio
async def test_job_pipeline_bluray_burn_success(tmp_path):
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    fake_media_info = MediaInfo(
        path="/media/video1.mkv",
        filename="video1.mkv",
        duration_sec=7200.0,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=24.0,
        video_codec="h264",
        audio_streams=[
            AudioStreamInfo(
                index=1,
                codec_name="ac3",
                channels=6,
                channel_layout="5.1",
                language="eng",
                title="English",
                bitrate=448000,
            )
        ],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=4000000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/video1.mkv"],
        disc_type=DiscType.BD25,
        output_mode=OutputMode.AUTHOR_AND_BURN,
        output_name="bluray_disc",
        burner_device="/dev/sr0",
        burn_speed=4,
    )

    burn_lines = [
        b"  10485760/24000000000 (  0.0%) @0.0x, remaining ??:??\n",
        b" 12000000000/24000000000 ( 50.0%) @4.0x, remaining 08:30\n",
        b" 24000000000/24000000000 (100.0%) @4.0x, remaining 00:00\n",
        b"",
    ]

    class MockProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.stderr = AsyncMock()
            self.stderr.readline = AsyncMock(
                side_effect=[
                    b"frame= 500 fps= 60.0 q=2.0 size= 5000kB time=01:00:00.00 bitrate= 18000kbits/s speed= 2.5x\n",
                    b"",
                ]
            )
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(side_effect=burn_lines)

        async def wait(self):
            return 0

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_media_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: MockProcess(),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

        job = manager.get_job(job_id)
        assert job is not None
        assert job.stage == JobStage.COMPLETED
        assert job.progress_percent == 100.0


@pytest.mark.asyncio
async def test_job_pipeline_transcode_failure(tmp_path):
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    fake_media_info = MediaInfo(
        path="/media/bad.mkv",
        filename="bad.mkv",
        duration_sec=3600.0,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=1000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/bad.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="bad_movie",
    )

    class FailingProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = 1
            self.stderr = AsyncMock()
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(return_value=b"")

        async def wait(self):
            return 1

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_media_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: FailingProcess(),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        task = manager.active_tasks[job_id]
        await task

        job = manager.get_job(job_id)
        assert job is not None
        assert job.stage == JobStage.FAILED
        assert "Transcoding failed" in (job.error_message or "")
        # Scratch directory is cleaned up even on failure
        assert not os.path.exists(os.path.join(scratch_dir, job_id))


@pytest.mark.asyncio
async def test_job_pipeline_cancellation(tmp_path):
    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    fake_media_info = MediaInfo(
        path="/media/movie.mkv",
        filename="movie.mkv",
        duration_sec=3600.0,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="h264",
        audio_streams=[],
        subtitle_streams=[],
        chapters_count=0,
        size_bytes=1000000,
    )

    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/movie.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="cancel_movie",
    )

    async def infinite_readline():
        await asyncio.sleep(10)
        return b""

    class HangingProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.stderr = AsyncMock()
            self.stderr.readline = AsyncMock(side_effect=infinite_readline)
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(return_value=b"")

        async def wait(self):
            await asyncio.sleep(10)
            return 0

    with patch(
        "dvdcompress.job_manager.probe_media_file",
        new_callable=AsyncMock,
        return_value=fake_media_info,
    ), patch(
        "asyncio.create_subprocess_exec",
        side_effect=lambda *cmd, **kwargs: HangingProcess(),
    ):
        await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
        await asyncio.sleep(0.05)  # Let the pipeline start

        await manager.cancel_job(job_id)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.stage == JobStage.CANCELLED
        # Scratch directory cleaned up
        assert not os.path.exists(os.path.join(scratch_dir, job_id))
