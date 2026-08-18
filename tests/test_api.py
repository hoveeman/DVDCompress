import asyncio
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from dvdcompress.api import _run_burn_iso_pipeline, app, job_manager
from dvdcompress.burner import OpticalDrive
from dvdcompress.job_manager import JobStage
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

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["app"] == "DVDCompress"


def test_api_files_nonexistent_and_permission_error():
    res = client.get("/api/files?path=/nonexistent/path/xyz")
    assert res.status_code == 200
    data = res.json()
    assert data["current_path"] == "/nonexistent/path/xyz"
    assert data["parent_path"] is None
    assert data["directories"] == []
    assert data["files"] == []


def test_api_files_with_real_directory(tmp_path):
    # Create test directory structure
    sub_dir = tmp_path / "subfolder"
    sub_dir.mkdir()
    hidden_dir = tmp_path / ".hidden_folder"
    hidden_dir.mkdir()

    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"dummy mp4 content")
    iso_file = tmp_path / "disc.iso"
    iso_file.write_bytes(b"dummy iso content")
    mkv_file = tmp_path / "show.mkv"
    mkv_file.write_bytes(b"dummy mkv content")
    text_file = tmp_path / "notes.txt"
    text_file.write_bytes(b"dummy text")
    hidden_file = tmp_path / ".hidden.mp4"
    hidden_file.write_bytes(b"dummy hidden")

    # Browse root tmp_path
    res = client.get(f"/api/files?path={tmp_path}")
    assert res.status_code == 200
    data = res.json()
    assert data["current_path"] == str(tmp_path)
    # Check directory listing (excludes hidden)
    dir_names = [d["name"] for d in data["directories"]]
    assert "subfolder" in dir_names
    assert ".hidden_folder" not in dir_names

    # Check files listing (includes videos and iso, excludes .txt and hidden)
    file_names = [f["name"] for f in data["files"]]
    assert "movie.mp4" in file_names
    assert "disc.iso" in file_names
    assert "show.mkv" in file_names
    assert "notes.txt" not in file_names
    assert ".hidden.mp4" not in file_names

    # Check file details
    movie_item = next(f for f in data["files"] if f["name"] == "movie.mp4")
    assert movie_item["is_video"] is True
    assert movie_item["is_iso"] is False
    assert movie_item["size_bytes"] > 0

    iso_item = next(f for f in data["files"] if f["name"] == "disc.iso")
    assert iso_item["is_video"] is False
    assert iso_item["is_iso"] is True

    # Browse subfolder - should have parent_path
    res_sub = client.get(f"/api/files?path={sub_dir}")
    assert res_sub.status_code == 200
    data_sub = res_sub.json()
    assert data_sub["parent_path"] == str(tmp_path)


def test_api_probe_success(tmp_path):
    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"video data")

    mock_info = MediaInfo(
        path=str(dummy_video),
        filename="sample.mp4",
        duration_sec=120.5,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        frame_rate=24.0,
        video_codec="h264",
        audio_streams=[
            AudioStreamInfo(
                index=1,
                codec_name="aac",
                channels=2,
                channel_layout="stereo",
                language="eng",
            )
        ],
        subtitle_streams=[],
        chapters_count=3,
        size_bytes=1024,
    )

    with patch("dvdcompress.api.probe_media_file", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_info
        res = client.post("/api/probe", json={"file_path": str(dummy_video)})
        assert res.status_code == 200
        data = res.json()
        assert data["filename"] == "sample.mp4"
        assert data["duration_sec"] == 120.5
        assert data["width"] == 1920
        assert len(data["audio_streams"]) == 1


def test_api_probe_file_not_found():
    res = client.post("/api/probe", json={"file_path": "/nonexistent/video.mp4"})
    assert res.status_code == 404
    assert "File not found" in res.json()["detail"]


def test_api_probe_error(tmp_path):
    dummy_video = tmp_path / "bad.mp4"
    dummy_video.write_bytes(b"corrupt")

    with patch("dvdcompress.api.probe_media_file", new_callable=AsyncMock) as mock_probe:
        mock_probe.side_effect = RuntimeError("ffprobe parsing failure")
        res = client.post("/api/probe", json={"file_path": str(dummy_video)})
        assert res.status_code == 500
        assert "ffprobe parsing failure" in res.json()["detail"]


def test_api_calculate():
    res = client.post(
        "/api/calculate",
        json={
            "total_duration_sec": 7200,
            "disc_type": "dvd5",
            "audio_tracks_kbps": [192],
            "video_count": 1,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["video_bitrate_kbps"] > 0
    assert data["target_capacity_mb"] == 4300.0
    assert data["fits_disc"] is True


def test_api_calculate_validation_error():
    res = client.post(
        "/api/calculate",
        json={
            "total_duration_sec": 7200,
            "disc_type": "invalid_disc_type",
        },
    )
    assert res.status_code == 422


def test_api_drives():
    mock_drives = [
        OpticalDrive(
            device_path="/dev/sr0",
            sg_device="/dev/sg0",
            vendor="ASUS",
            model="BW-16D1HT",
            is_writable=True,
            media_status="Ready",
        )
    ]
    with patch("dvdcompress.api.scan_optical_drives", return_value=mock_drives):
        res = client.get("/api/drives")
        assert res.status_code == 200
        drives = res.json()
        assert len(drives) == 1
        assert drives[0]["device_path"] == "/dev/sr0"
        assert drives[0]["vendor"] == "ASUS"


def test_api_system():
    mock_telemetry = {
        "gpu_available": True,
        "gpu_name": "NVIDIA GeForce RTX 3080",
        "gpu_utilization_percent": 25,
        "gpu_memory_used_mb": 1024,
        "gpu_memory_total_mb": 10240,
        "gpu_temp_c": 55,
    }
    with patch("dvdcompress.api.get_hardware_telemetry", return_value=mock_telemetry):
        res = client.get("/api/system")
        assert res.status_code == 200
        data = res.json()
        assert data["gpu_available"] is True
        assert data["gpu_name"] == "NVIDIA GeForce RTX 3080"


def test_api_jobs_lifecycle(tmp_path):
    input_file = tmp_path / "clip.mp4"
    input_file.write_bytes(b"dummy clip data")

    # Non-existent input file returns 400
    res_bad = client.post(
        "/api/jobs",
        json={
            "input_files": ["/nonexistent/clip.mp4"],
            "disc_type": "dvd5",
            "output_mode": "iso_only",
            "output_name": "my_disc",
        },
    )
    assert res_bad.status_code == 400
    assert "Input file does not exist" in res_bad.json()["detail"]

    # Valid job creation with mocked start_job
    with patch.object(job_manager, "start_job", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = None
        res_create = client.post(
            "/api/jobs",
            json={
                "input_files": [str(input_file)],
                "disc_type": "dvd5",
                "output_mode": "iso_only",
                "output_name": "my_disc",
                "tv_standard": "auto",
                "aspect_ratio": "16:9",
                "menu_mode": "autoplay",
                "use_gpu": False,
            },
        )
        assert res_create.status_code == 200
        data_create = res_create.json()
        job_id = data_create["job_id"]
        assert data_create["status"] == "started"
        mock_start.assert_called_once()

    # Get job status
    res_get = client.get(f"/api/jobs/{job_id}")
    assert res_get.status_code == 200
    job_data = res_get.json()
    assert job_data["job_id"] == job_id
    assert job_data["output_name"] == "my_disc"
    assert job_data["disc_type"] == "dvd5"

    # Get non-existent job returns 404
    res_get_404 = client.get("/api/jobs/nonexistent_id")
    assert res_get_404.status_code == 404

    # Pause job
    with patch.object(job_manager, "pause_job", new_callable=AsyncMock) as mock_pause:
        res_pause = client.post(f"/api/jobs/{job_id}/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "paused"
        mock_pause.assert_called_once_with(job_id)

    # Resume job
    with patch.object(job_manager, "resume_job", new_callable=AsyncMock) as mock_resume:
        res_resume = client.post(f"/api/jobs/{job_id}/resume")
        assert res_resume.status_code == 200
        assert res_resume.json()["status"] == "resumed"
        mock_resume.assert_called_once_with(job_id)

    # Cancel job
    with patch.object(job_manager, "cancel_job", new_callable=AsyncMock) as mock_cancel:
        res_cancel = client.post(f"/api/jobs/{job_id}/cancel")
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "cancelled"
        mock_cancel.assert_called_once_with(job_id)

    # Cancel non-existent job returns 404
    res_cancel_404 = client.post("/api/jobs/nonexistent_id/cancel")
    assert res_cancel_404.status_code == 404

    # Pause non-existent job returns 404
    res_pause_404 = client.post("/api/jobs/nonexistent_id/pause")
    assert res_pause_404.status_code == 404

    # Resume non-existent job returns 404
    res_resume_404 = client.post("/api/jobs/nonexistent_id/resume")
    assert res_resume_404.status_code == 404


def test_api_burn_iso(tmp_path):
    iso_file = tmp_path / "standalone.iso"
    iso_file.write_bytes(b"dummy iso image")

    # Non-existent ISO returns 404
    res_404 = client.post(
        "/api/burn-iso",
        json={
            "iso_path": "/nonexistent/disc.iso",
            "device_path": "/dev/sr0",
            "burn_speed": 4,
            "is_bluray": False,
        },
    )
    assert res_404.status_code == 404

    # Valid ISO starts burn job
    res = client.post(
        "/api/burn-iso",
        json={
            "iso_path": str(iso_file),
            "device_path": "/dev/sr0",
            "burn_speed": 4,
            "is_bluray": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "started"

    job = job_manager.get_job(data["job_id"])
    assert job is not None
    assert job.output_mode == OutputMode.BURN_DIRECT
    assert job.disc_type == DiscType.DVD5


def test_api_burn_iso_auto_detect_dvd9(tmp_path):
    iso_file = tmp_path / "mary_poppins.iso"
    with open(iso_file, "wb") as f:
        f.truncate(6_800_000_000)  # Sparse 6.8 GB file for DVD-9

    res = client.post(
        "/api/burn-iso",
        json={
            "iso_path": str(iso_file),
            "device_path": "/dev/sr0",
            "burn_speed": 8,
            "is_bluray": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    job = job_manager.get_job(data["job_id"])
    assert job is not None
    assert job.disc_type == DiscType.DVD9
    assert job.burn_speed == 8


def test_api_burn_iso_auto_detect_bd50(tmp_path):
    iso_file = tmp_path / "movie_bd50.iso"
    with open(iso_file, "wb") as f:
        f.truncate(45_000_000_000)  # Sparse 45 GB file for BD-50

    res = client.post(
        "/api/burn-iso",
        json={
            "iso_path": str(iso_file),
            "device_path": "/dev/sr0",
            "burn_speed": 4,
            "is_bluray": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    job = job_manager.get_job(data["job_id"])
    assert job is not None
    assert job.disc_type == DiscType.BD50


def test_api_burn_iso_explicit_disc_type(tmp_path):
    iso_file = tmp_path / "custom.iso"
    iso_file.write_bytes(b"small iso")

    res = client.post(
        "/api/burn-iso",
        json={
            "iso_path": str(iso_file),
            "device_path": "/dev/sr0",
            "burn_speed": 8,
            "disc_type": "dvd9",
            "is_bluray": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    job = job_manager.get_job(data["job_id"])
    assert job is not None
    assert job.disc_type == DiscType.DVD9



@pytest.mark.asyncio
async def test_run_burn_iso_pipeline_success(tmp_path):
    iso_file = tmp_path / "image.iso"
    iso_file.write_bytes(b"iso bytes")

    job_id = job_manager.create_job(
        input_files=[str(iso_file)],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.BURN_DIRECT,
        output_name="image",
        burner_device="/dev/sr0",
        burn_speed=4,
    )

    mock_proc = AsyncMock()
    mock_proc.stdout.readline = AsyncMock(
        side_effect=[
            b" ( 45.0%) @4.0x, remaining 05:00\n",
            b" (100.0%) @4.0x, remaining 00:00\n",
            b"",
        ]
    )
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        await _run_burn_iso_pipeline(
            job_id=job_id,
            iso_path=str(iso_file),
            device_path="/dev/sr0",
            speed=4,
            is_bluray=False,
        )

    job = job_manager.get_job(job_id)
    assert job.stage == "completed"
    assert job.progress_percent == 100.0


@pytest.mark.asyncio
async def test_run_burn_iso_pipeline_failure(tmp_path):
    iso_file = tmp_path / "image2.iso"
    iso_file.write_bytes(b"iso bytes")

    job_id = job_manager.create_job(
        input_files=[str(iso_file)],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.BURN_DIRECT,
        output_name="image2",
        burner_device="/dev/sr0",
        burn_speed=4,
    )

    mock_proc = AsyncMock()
    mock_proc.stdout.readline = AsyncMock(return_value=b"")
    mock_proc.wait = AsyncMock(return_value=1)
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        await _run_burn_iso_pipeline(
            job_id=job_id,
            iso_path=str(iso_file),
            device_path="/dev/sr0",
            speed=4,
            is_bluray=False,
        )

    job = job_manager.get_job(job_id)
    assert job.stage == "failed"
    assert "Burning failed" in job.error_message


def test_api_websocket_endpoint():
    job_id = job_manager.create_job(
        input_files=["/media/dummy.mp4"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="ws_test",
    )

    with client.websocket_connect(f"/ws/jobs/{job_id}") as websocket:
        # Initial message received upon connection
        initial_data = websocket.receive_json()
        assert initial_data["job_id"] == job_id
        assert initial_data["output_name"] == "ws_test"

        # Broadcast an update to listeners
        job = job_manager.get_job(job_id)
        job.progress_percent = 50.0
        job.stage = JobStage.TRANSCODING
        asyncio.run(job_manager.broadcast(job_id))

        update_data = websocket.receive_json()
        assert update_data["progress_percent"] == 50.0
        assert update_data["stage"] == "transcoding"


def test_api_static_files_serving(tmp_path):
    static_dir = os.path.join(os.path.dirname(__file__), "..", "src", "dvdcompress", "static")
    os.makedirs(static_dir, exist_ok=True)
    index_file = os.path.join(static_dir, "index.html")
    created = False
    if not os.path.exists(index_file):
        with open(index_file, "w") as f:
            f.write("<html><body>DVDCompress</body></html>")
        created = True

    try:
        res = client.get("/")
        assert res.status_code == 200
        assert "DVDCompress" in res.text
    finally:
        if created and os.path.exists(index_file):
            os.remove(index_file)


def test_api_preview_endpoint_validation_and_launch(tmp_path, monkeypatch):
    # 1. Validation error if input file doesn't exist
    resp = client.post("/api/preview", json={
        "input_file": "/nonexistent/video.mkv",
        "preview_mode": "preview_video",
        "disc_type": "dvd5",
        "output_name": "sample_prev"
    })
    assert resp.status_code == 404

    # 2. Success case with real file
    test_media = tmp_path / "sample.mp4"
    test_media.write_bytes(b"dummy")

    async def fake_start(job_id, scratch_dir, output_dir):
        pass

    monkeypatch.setattr(job_manager, "start_job", fake_start)

    resp = client.post("/api/preview", json={
        "input_file": str(test_media),
        "preview_mode": "preview_video",
        "disc_type": "dvd5",
        "output_name": "sample_prev"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "started"
    assert data["preview_mode"] == "preview_video"
    assert "preview_sample_prev.mpg" in data["output_path"]


def test_api_jobs_with_selected_subtitles(tmp_path, monkeypatch):
    test_media = tmp_path / "sample_subs.mp4"
    test_media.write_bytes(b"dummy")

    async def fake_start(job_id, scratch_dir, output_dir):
        pass

    monkeypatch.setattr(job_manager, "start_job", fake_start)

    resp = client.post("/api/jobs", json={
        "input_files": [str(test_media)],
        "disc_type": "bd25",
        "output_mode": "iso_only",
        "output_name": "subs_disc",
        "selected_subtitle_indices": [2, 3],
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    job = job_manager.get_job(job_id)
    assert job is not None
    assert job.selected_subtitle_indices == [2, 3]


def test_api_jobs_with_passthrough_toggle(tmp_path, monkeypatch):
    test_media = tmp_path / "remux.mkv"
    test_media.write_bytes(b"dummy")

    async def fake_start(job_id, scratch_dir, output_dir):
        pass

    monkeypatch.setattr(job_manager, "start_job", fake_start)

    resp = client.post("/api/jobs", json={
        "input_files": [str(test_media)],
        "disc_type": "bd66",
        "output_mode": "iso_only",
        "output_name": "uhd_passthrough",
        "passthrough": True,
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    job = job_manager.get_job(job_id)
    assert job is not None
    assert job.passthrough is True


def test_api_settings_get_and_post():
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "max_concurrent_jobs" in data
    assert data["max_concurrent_jobs"] >= 1

    # Update settings
    res = client.post("/api/settings", json={"max_concurrent_jobs": 7})
    assert res.status_code == 200
    assert res.json()["settings"]["max_concurrent_jobs"] == 7

    # Verify update persisted
    res2 = client.get("/api/settings")
    assert res2.status_code == 200
    assert res2.json()["max_concurrent_jobs"] == 7

    # Validation error for invalid range
    res_err = client.post("/api/settings", json={"max_concurrent_jobs": 0})
    assert res_err.status_code == 422 or res_err.status_code == 400

    # Reset back to 5
    client.post("/api/settings", json={"max_concurrent_jobs": 5})


def test_api_delete_job_success():
    # Create a job and set it to completed
    job_id = job_manager.create_job(
        input_files=["/media/dummy.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_delete",
    )
    job = job_manager.get_job(job_id)
    job.stage = JobStage.COMPLETED

    res = client.delete(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"
    assert job_manager.get_job(job_id) is None


def test_api_delete_job_not_found():
    res = client.delete("/api/jobs/nonexistent_id")
    assert res.status_code == 404


def test_api_delete_job_active_error():
    job_id = job_manager.create_job(
        input_files=["/media/dummy.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_delete_active",
    )
    job = job_manager.get_job(job_id)
    job.stage = JobStage.TRANSCODING
    job_manager.active_tasks[job_id] = "mock_task"

    try:
        res = client.delete(f"/api/jobs/{job_id}")
        assert res.status_code == 400
        assert "Cannot delete an active running job" in res.json()["detail"]
    finally:
        del job_manager.active_tasks[job_id]
        job_manager.delete_job(job_id)


def test_api_clear_jobs_history():
    job_id1 = job_manager.create_job(
        input_files=["/media/dummy1.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_clear_1",
    )
    job_id2 = job_manager.create_job(
        input_files=["/media/dummy2.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_clear_2",
    )
    job1 = job_manager.get_job(job_id1)
    job2 = job_manager.get_job(job_id2)
    job1.stage = JobStage.COMPLETED
    job2.stage = JobStage.FAILED

    res = client.delete("/api/jobs")
    assert res.status_code == 200
    assert res.json()["status"] == "cleared"
    assert res.json()["count"] >= 2
    assert job_manager.get_job(job_id1) is None
    assert job_manager.get_job(job_id2) is None


def test_api_analyze_complexity(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"dummy")

    with patch("dvdcompress.api.analyze_video_complexity", new_callable=AsyncMock) as mock_analyze:
        from dvdcompress.models import ComplexityAnalysisResult
        mock_analyze.return_value = ComplexityAnalysisResult(
            empirical_video_bitrate_kbps=3200,
            projected_iso_size_mb=2900.0,
            projected_iso_size_gb=2.9,
            recommended_disc_type=DiscType.DVD5,
            recommendation_text="Optimal for DVD-5",
            complexity_level="Low (Clean Digital)",
            sample_count=5,
        )

        res = client.post(
            "/api/analyze-complexity",
            json={
                "input_files": [str(clip)],
                "disc_type": "dvd5",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["empirical_video_bitrate_kbps"] == 3200
        assert data["projected_iso_size_gb"] == 2.9
        assert data["recommended_disc_type"] == "dvd5"
        assert "Low" in data["complexity_level"]


def test_api_retry_job(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"dummy")

    # 1. Create a job first
    with patch.object(job_manager, "start_job", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = None
        res_create = client.post(
            "/api/jobs",
            json={
                "input_files": [str(clip)],
                "disc_type": "dvd9",
                "output_mode": "iso_only",
                "output_name": "hp_movie",
                "tv_standard": "ntsc",
                "aspect_ratio": "16:9",
                "menu_mode": "autoplay",
                "use_gpu": False,
                "passthrough": False,
            },
        )
        assert res_create.status_code == 200
        orig_id = res_create.json()["job_id"]

    # 2. Retry non-existent job returns 404
    res_404 = client.post("/api/jobs/nonexistent_id/retry")
    assert res_404.status_code == 404

    # 3. Retry the valid job
    with patch.object(job_manager, "start_job", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = None
        res_retry = client.post(f"/api/jobs/{orig_id}/retry")
        assert res_retry.status_code == 200
        data_retry = res_retry.json()
        new_id = data_retry["job_id"]
        assert new_id != orig_id
        assert data_retry["output_name"] == "hp_movie"
        assert data_retry["disc_type"] == "dvd9"
        assert data_retry["input_files"] == [str(clip)]
        mock_start.assert_called_once()








