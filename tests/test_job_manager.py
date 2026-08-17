import asyncio
import os
import shutil
import signal
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
            progress_bytes = b"frame= 100 fps= 45.0 q=2.0 size= 1024kB time=00:30:00.00 bitrate= 4500kbits/s speed= 2.1x\n"
            self.stderr.read = AsyncMock(side_effect=[progress_bytes, b""])
            self.stderr.readline = AsyncMock(side_effect=[progress_bytes, b""])
            self.stdout = AsyncMock()
            self.stdout.read = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(return_value=b"")

        async def wait(self):
            return 0

        async def communicate(self):
            return (b"", b"")

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
            progress_bytes = b"frame= 500 fps= 60.0 q=2.0 size= 5000kB time=01:00:00.00 bitrate= 18000kbits/s speed= 2.5x\n"
            self.stderr.read = AsyncMock(side_effect=[progress_bytes, b""])
            self.stderr.readline = AsyncMock(side_effect=[progress_bytes, b""])
            self.stdout = AsyncMock()
            self.stdout.read = AsyncMock(return_value=b"")
            self.stdout.readline = AsyncMock(side_effect=burn_lines)

        async def wait(self):
            return 0

        async def communicate(self):
            return (b"", b"")

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
            self.stderr.read = AsyncMock(return_value=b"")
            self.stderr.readline = AsyncMock(return_value=b"")
            self.stdout = AsyncMock()
            self.stdout.read = AsyncMock(return_value=b"")
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
            self.stderr.read = AsyncMock(side_effect=infinite_readline)
            self.stderr.readline = AsyncMock(side_effect=infinite_readline)
            self.stdout = AsyncMock()
            self.stdout.read = AsyncMock(return_value=b"")
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


@pytest.mark.asyncio
async def test_job_pause_and_resume():
    manager = JobManager()
    manager.jobs.clear()
    job_id = manager.create_job(
        input_files=["/media/clip.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="pause_test",
    )
    job = manager.get_job(job_id)
    job.stage = JobStage.TRANSCODING

    mock_proc = MagicMock()
    mock_proc.send_signal = MagicMock()
    manager.active_processes[job_id] = mock_proc

    # Pause
    await manager.pause_job(job_id)
    assert job.stage == JobStage.PAUSED
    assert job.is_paused is True
    mock_proc.send_signal.assert_called_with(signal.SIGSTOP)

    # Resume
    await manager.resume_job(job_id)
    assert job.stage == JobStage.TRANSCODING
    assert job.is_paused is False
    mock_proc.send_signal.assert_called_with(signal.SIGCONT)


@pytest.mark.asyncio
async def test_job_auto_resume_on_complete():
    manager = JobManager()
    manager.jobs.clear()
    job1 = manager.create_job(
        input_files=["/media/clip1.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="job1",
    )
    job2 = manager.create_job(
        input_files=["/media/clip2.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="job2",
    )

    # Pause job 2
    j2 = manager.get_job(job2)
    j2.stage = JobStage.TRANSCODING
    await manager.pause_job(job2)
    assert j2.stage == JobStage.PAUSED

    # Auto-resume triggered when job1 finishes
    await manager._auto_resume_next_job(exclude_job_id=job1)
    assert j2.stage == JobStage.TRANSCODING
    assert j2.is_paused is False


@pytest.mark.asyncio
async def test_job_pipeline_preview_video_execution(tmp_path, monkeypatch):
    manager = JobManager()
    manager.jobs.clear()
    media_file = str(tmp_path / "movie.mkv")
    with open(media_file, "w") as f:
        f.write("dummy")

    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir, exist_ok=True)

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie.mkv",
            duration_sec=7200.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=23.976,
            video_codec="h264",
            size_bytes=1000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    executed_cmds = []

    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass
        async def communicate(self): return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        out = cmd[-1]
        with open(out, "w") as f:
            f.write("video_stream")
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = manager.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.PREVIEW_VIDEO,
        output_name="test_movie_preview",
    )

    await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    task = manager.active_tasks[job_id]
    await task

    job = manager.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    assert job.output_iso_path == os.path.join(output_dir, "preview_test_movie_preview.mpg")
    ffmpeg_cmd = executed_cmds[0]
    assert "-ss" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-ss") + 1] == "3570.0"
    assert "-t" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-t") + 1] == "60.0"


@pytest.mark.asyncio
async def test_job_pipeline_preview_iso_execution(tmp_path, monkeypatch):
    manager = JobManager()
    manager.jobs.clear()
    media_file = str(tmp_path / "movie.mkv")
    with open(media_file, "w") as f:
        f.write("dummy")

    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie.mkv",
            duration_sec=3600.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=23.976,
            video_codec="h264",
            size_bytes=1000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass
        async def communicate(self): return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = manager.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.PREVIEW_ISO,
        output_name="test_iso_preview",
    )

    await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    task = manager.active_tasks[job_id]
    await task

    job = manager.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    assert job.output_iso_path == os.path.join(output_dir, "preview_test_iso_preview.iso")


@pytest.mark.asyncio
async def test_job_pipeline_subtitle_extraction_and_authoring(tmp_path, monkeypatch):
    manager = JobManager()
    manager.jobs.clear()
    media_file = str(tmp_path / "movie_with_subs.mkv")
    with open(media_file, "w") as f:
        f.write("content")

    output_dir = str(tmp_path / "output")
    scratch_dir = str(tmp_path / "scratch")
    os.makedirs(output_dir, exist_ok=True)

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie_with_subs.mkv",
            duration_sec=3600.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=24.0,
            video_codec="hevc",
            audio_streams=[AudioStreamInfo(index=1, codec_name="ac3", channels=2)],
            subtitle_streams=[
                SubtitleStreamInfo(index=2, codec_name="subrip", language="eng", title="English"),
                SubtitleStreamInfo(index=3, codec_name="hdmv_pgs_subtitle", language="spa", title="Spanish Forced"),
            ],
            size_bytes=1000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    executed_cmds = []

    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass
        async def communicate(self): return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = manager.create_job(
        input_files=[media_file],
        disc_type=DiscType.BD25,
        output_mode=OutputMode.ISO_ONLY,
        output_name="bluray_with_subs",
    )

    await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    task = manager.active_tasks[job_id]
    await task

    job = manager.get_job(job_id)
    assert job.stage == JobStage.COMPLETED

    # Verify extraction commands were run for both subtitles
    sub_cmds = [c for c in executed_cmds if "-map" in c and any(c[-1].endswith(ext) for ext in (".srt", ".sup"))]
    assert len(sub_cmds) == 2
    assert sub_cmds[0] == ["ffmpeg", "-y", "-i", media_file, "-map", "0:2", "-c:s", "srt", os.path.join(scratch_dir, job_id, "title_1_sub_0.srt")]
    assert sub_cmds[1] == ["ffmpeg", "-y", "-i", media_file, "-map", "0:3", "-c:s", "copy", os.path.join(scratch_dir, job_id, "title_1_sub_1.sup")]


@pytest.mark.asyncio
async def test_job_pipeline_dvd_chained_spumux_multiplexing(tmp_path, monkeypatch):
    """Verify that multiple DVD text subtitles execute a single chained spumux pipeline with live progress."""
    manager = JobManager()
    manager.jobs.clear()
    media_file = str(tmp_path / "movie_multi_subs.mkv")
    with open(media_file, "w") as f:
        f.write("dummy_video_bytes")

    output_dir = str(tmp_path / "output")
    scratch_dir = str(tmp_path / "scratch")
    os.makedirs(output_dir, exist_ok=True)

    fake_media_info = MediaInfo(
        path=media_file,
        filename="movie_multi_subs.mkv",
        duration_sec=7200.0,
        width=720,
        height=480,
        aspect_ratio="16:9",
        frame_rate=29.97,
        video_codec="mpeg2video",
        audio_streams=[AudioStreamInfo(index=1, codec_name="ac3", channels=6)],
        subtitle_streams=[
            SubtitleStreamInfo(index=2, codec_name="subrip", language="eng", title="English Dialogue"),
            SubtitleStreamInfo(index=3, codec_name="subrip", language="eng", title="English Lyrics"),
            SubtitleStreamInfo(index=4, codec_name="subrip", language="spa", title="Spanish"),
        ],
        size_bytes=4000000000,
    )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", AsyncMock(return_value=fake_media_info))

    executed_shell_cmds = []

    class FakeSpuProc:
        returncode = 0

        def __init__(self):
            class Stream:
                def __init__(self):
                    self.chunks = [
                        b"INFO: 1000000 bytes of data written\rINFO: 2000000 bytes of data written\r",
                        b"INFO: 4000000 bytes of data written\nINFO: 3 subtitles added, 0 subtitles skipped\n",
                        b"",
                    ]
                    self.idx = 0

                async def read(self, n):
                    if self.idx < len(self.chunks):
                        res = self.chunks[self.idx]
                        self.idx += 1
                        return res
                    return b""

            self.stderr = Stream()

        async def wait(self):
            return 0

        def send_signal(self, sig):
            pass

        def kill(self):
            pass

        async def communicate(self):
            return (b"", b"")

    class FakeExecProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass
        async def communicate(self): return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            out_target = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_target)), exist_ok=True)
            with open(out_target, "wb") as f:
                f.write(b"MOCK_STREAM_BYTES")
        elif cmd[0] == "dvdauthor":
            author_dir = cmd[cmd.index("-o") + 1]
            v_ts = os.path.join(author_dir, "VIDEO_TS")
            os.makedirs(v_ts, exist_ok=True)
            with open(os.path.join(v_ts, "VIDEO_TS.IFO"), "wb") as f:
                f.write(b"DVDVIDEO-VMG")
        if "-o" in cmd:
            o_idx = cmd.index("-o")
            iso_target = cmd[o_idx + 1]
            if iso_target.endswith(".iso"):
                os.makedirs(os.path.dirname(os.path.abspath(iso_target)), exist_ok=True)
                with open(iso_target, "w") as f:
                    f.write("ISO_BYTES")
        return FakeExecProc()

    async def fake_shell(cmd_str, **kwargs):
        executed_shell_cmds.append(cmd_str)
        if ">" in cmd_str:
            out_target = cmd_str.split(">")[-1].strip().strip("'\"")
            os.makedirs(os.path.dirname(os.path.abspath(out_target)), exist_ok=True)
            with open(out_target, "wb") as f:
                f.write(b"MOCK_SUBBED_MPG_BYTES")
        return FakeSpuProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr("asyncio.create_subprocess_shell", fake_shell)

    job_id = manager.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD9,
        output_mode=OutputMode.ISO_ONLY,
        output_name="dvd_multi_sub_test",
        selected_subtitle_indices=[2, 3, 4],
    )

    await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await manager.active_tasks[job_id]

    job = manager.get_job(job_id)
    assert job.stage == JobStage.COMPLETED

    # Verify a single chained spumux pipeline was executed for all 3 subtitle tracks
    spumux_pipeline_cmds = [c for c in executed_shell_cmds if "spumux" in c]
    assert len(spumux_pipeline_cmds) == 1
    pipe_cmd = spumux_pipeline_cmds[0]
    assert "spumux -m dvd -s 0" in pipe_cmd
    assert "spumux -m dvd -s 1" in pipe_cmd
    assert "spumux -m dvd -s 2" in pipe_cmd
    assert " | " in pipe_cmd
    assert pipe_cmd.count(" | ") == 2

    # Verify log messages reflect the streaming pipeline
    assert any("Multiplexing 3 DVD subtitle track(s) in streaming pipeline" in l for l in job.logs)
    assert any("Successfully multiplexed 3 subtitle track(s)" in l for l in job.logs)



@pytest.mark.asyncio
async def test_job_pipeline_passthrough_execution(tmp_path, monkeypatch):
    """Verify that UHD Blu-ray with passthrough=True bypasses ffmpeg video transcoding."""
    manager = JobManager()
    manager.jobs.clear()
    media_file = str(tmp_path / "4k_hdr_remux.mkv")
    with open(media_file, "w") as f:
        f.write("content")

    output_dir = str(tmp_path / "output")
    scratch_dir = str(tmp_path / "scratch")
    os.makedirs(output_dir, exist_ok=True)

    fake_probe_info = MediaInfo(
        path=media_file,
        filename="4k_hdr_remux.mkv",
        duration_sec=7200.0,
        width=3840,
        height=2160,
        aspect_ratio="16:9",
        frame_rate=23.976,
        video_codec="hevc",
        pix_fmt="yuv420p10le",
        color_transfer="smpte2084",
        color_primaries="bt2020",
        is_hdr=True,
        audio_streams=[AudioStreamInfo(index=1, codec_name="ac3", channels=6)],
        subtitle_streams=[],
        size_bytes=45000000000,
    )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", AsyncMock(return_value=fake_probe_info))

    executed_cmds = []

    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass
        async def communicate(self): return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = manager.create_job(
        input_files=[media_file],
        disc_type=DiscType.BD66,
        output_mode=OutputMode.ISO_ONLY,
        output_name="uhd_passthrough_disc",
        passthrough=True,
    )

    await manager.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await manager.active_tasks[job_id]

    job = manager.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    assert any("Direct Stream Passthrough active" in log for log in job.logs)

    # Verify no ffmpeg transcode command was executed (only tsMuxeR and xorriso)
    ffmpeg_transcodes = [c for c in executed_cmds if c[0] == "ffmpeg" and "-b:v" in c]
    assert len(ffmpeg_transcodes) == 0
    assert any(c[0] == "tsMuxeR" for c in executed_cmds)



