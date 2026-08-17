"""FastAPI Application Server & REST/WebSocket Endpoints for DVDCompress."""

import asyncio
import glob
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dvdcompress.burner import (
    OpticalDrive,
    build_burn_command,
    parse_burn_progress_line,
    scan_optical_drives,
)
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.config import AppSettings, load_app_settings, save_app_settings, settings
from dvdcompress.job_manager import Job, JobManager, JobStage
from dvdcompress.models import (
    AspectRatio,
    BitrateBudget,
    DiscType,
    MediaInfo,
    MenuMode,
    OutputMode,
    TVStandard,
)
from dvdcompress.probe import probe_media_file
from dvdcompress.system_info import get_hardware_telemetry

app = FastAPI(title="DVDCompress API", version="1.0.0")
job_manager = JobManager()

# Load persisted settings and jobs on startup
app_settings = load_app_settings(settings.config_dir)
job_manager.max_concurrent_jobs = app_settings.max_concurrent_jobs
job_manager.load_jobs(str(settings.config_dir))


@app.on_event("startup")
async def startup_event():
    current_settings = load_app_settings(settings.config_dir)
    job_manager.max_concurrent_jobs = current_settings.max_concurrent_jobs
    job_manager.load_jobs(str(settings.config_dir))
    await job_manager.process_queue(get_scratch_dir(), get_output_dir())


def get_media_dir() -> str:
    return os.environ.get("DVDCOMPRESS_MEDIA_DIR", os.environ.get("MEDIA_DIR", "/media"))


def get_output_dir() -> str:
    return os.environ.get("DVDCOMPRESS_OUTPUT_DIR", os.environ.get("OUTPUT_DIR", "/output"))


def get_scratch_dir() -> str:
    return os.environ.get("DVDCOMPRESS_TEMP_DIR", os.environ.get("SCRATCH_DIR", "/tmp/dvdcompress"))

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".wmv",
    ".ts",
    ".m2ts",
    ".webm",
    ".flv",
    ".mpg",
    ".vob",
}


class CalculateRequest(BaseModel):
    total_duration_sec: float
    disc_type: DiscType
    audio_tracks_kbps: List[int] = Field(default_factory=lambda: [192])
    video_count: int = 1


class ProbeRequest(BaseModel):
    file_path: str


class CreateJobRequest(BaseModel):
    input_files: List[str]
    disc_type: DiscType
    output_mode: OutputMode
    output_name: str
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    burner_device: Optional[str] = None
    burn_speed: int = 4
    use_gpu: bool = True
    passthrough: bool = False
    selected_subtitle_indices: Optional[List[int]] = None


class BurnIsoRequest(BaseModel):
    iso_path: str
    device_path: str
    burn_speed: int = 4
    is_bluray: bool = False


class CreatePreviewRequest(BaseModel):
    input_file: str
    preview_mode: OutputMode = OutputMode.PREVIEW_VIDEO
    disc_type: DiscType = DiscType.DVD5
    output_name: str = "preview_sample"
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    use_gpu: bool = True
    passthrough: bool = False
    custom_bitrate_kbps: Optional[int] = None
    selected_subtitle_indices: Optional[List[int]] = None



async def _run_burn_iso_pipeline(
    job_id: str, iso_path: str, device_path: str, speed: int, is_bluray: bool
):
    """Pipeline for burning a standalone existing ISO image to optical disc."""
    job = job_manager.get_job(job_id)
    if not job:
        return

    job.stage = JobStage.BURNING
    job.output_iso_path = iso_path
    job_manager.log(
        job_id, f"Burning ISO {iso_path} to {device_path} at {speed}x..."
    )
    await job_manager.broadcast(job_id)

    current_process: Optional[asyncio.subprocess.Process] = None

    try:
        burn_cmd = build_burn_command(
            device_path, iso_path, speed=speed, is_bluray=is_bluray
        )
        proc = await asyncio.create_subprocess_exec(
            *burn_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        current_process = proc

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            decoded = line.decode(errors="replace").strip()
            if decoded:
                job_manager.log(job_id, decoded)
            prog = parse_burn_progress_line(decoded)
            if "percent" in prog:
                job.stage_percent = prog["percent"]
                job.progress_percent = prog["percent"]
                job.eta = prog.get("remaining", job.eta)
                if "speed" in prog:
                    job.speed = prog["speed"]
            await job_manager.broadcast(job_id)

        await proc.wait()
        current_process = None
        if proc.returncode != 0:
            raise RuntimeError(f"Burning failed with exit code {proc.returncode}")

        job.stage = JobStage.COMPLETED
        job.progress_percent = 100.0
        job.stage_percent = 100.0
        job_manager.log(job_id, "Burn completed successfully!")
        await job_manager.broadcast(job_id)

    except asyncio.CancelledError:
        if current_process:
            try:
                current_process.kill()
            except Exception:
                pass
        job.stage = JobStage.CANCELLED
        job.error_message = "Burn cancelled by user"
        job_manager.log(job_id, "Burn job was cancelled.")
        await job_manager.broadcast(job_id)
    except Exception as e:
        if current_process:
            try:
                current_process.kill()
            except Exception:
                pass
        job.stage = JobStage.FAILED
        job.error_message = str(e)
        job_manager.log(job_id, f"ERROR: {str(e)}")
        await job_manager.broadcast(job_id)
    finally:
        if job_id in job_manager.active_tasks:
            del job_manager.active_tasks[job_id]


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "DVDCompress"}


@app.get("/api/files")
def list_files(path: Optional[str] = None):
    media_dir = get_media_dir()
    target = path or media_dir
    if not os.path.exists(target):
        return {
            "current_path": target,
            "parent_path": None,
            "directories": [],
            "files": [],
        }

    try:
        entries = os.listdir(target)
    except Exception:
        return {
            "current_path": target,
            "parent_path": None,
            "directories": [],
            "files": [],
        }

    dirs = []
    files = []

    for e in sorted(entries):
        if e.startswith("."):
            continue
        full = os.path.join(target, e)
        if os.path.isdir(full):
            dirs.append({"name": e, "path": full})
        elif os.path.isfile(full):
            ext = os.path.splitext(e)[1].lower()
            if ext in VIDEO_EXTENSIONS or ext == ".iso":
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                files.append(
                    {
                        "name": e,
                        "path": full,
                        "size_bytes": size,
                        "is_video": ext in VIDEO_EXTENSIONS,
                        "is_iso": ext == ".iso",
                    }
                )

    norm_target = os.path.abspath(target)
    norm_media = os.path.abspath(media_dir)
    parent = (
        os.path.dirname(norm_target)
        if norm_target != norm_media and norm_target != "/"
        else None
    )

    return {
        "current_path": target,
        "parent_path": parent,
        "directories": dirs,
        "files": files,
    }


@app.post("/api/probe", response_model=MediaInfo)
async def probe_file(req: ProbeRequest):
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        return await probe_media_file(req.file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate", response_model=BitrateBudget)
def calculate_budget(req: CalculateRequest):
    return calculate_bitrate_budget(
        total_duration_sec=req.total_duration_sec,
        disc_type=req.disc_type,
        audio_tracks_kbps=req.audio_tracks_kbps,
        video_count=req.video_count,
    )


@app.get("/api/drives", response_model=List[OpticalDrive])
def list_drives():
    return scan_optical_drives()


@app.get("/api/system")
def get_system():
    return get_hardware_telemetry()


@app.get("/api/settings", response_model=AppSettings)
def get_settings():
    return load_app_settings(settings.config_dir)


@app.post("/api/settings")
async def update_settings(req: AppSettings):
    save_app_settings(req, settings.config_dir)
    await job_manager.set_max_concurrent_jobs(req.max_concurrent_jobs, get_scratch_dir(), get_output_dir())
    return {"status": "updated", "settings": req.model_dump()}


@app.post("/api/jobs")
async def create_job(req: CreateJobRequest):
    for f in req.input_files:
        if not os.path.exists(f):
            raise HTTPException(
                status_code=400, detail=f"Input file does not exist: {f}"
            )

    job_id = job_manager.create_job(
        input_files=req.input_files,
        disc_type=req.disc_type,
        output_mode=req.output_mode,
        output_name=req.output_name,
        tv_standard=req.tv_standard,
        aspect_ratio=req.aspect_ratio,
        menu_mode=req.menu_mode,
        burner_device=req.burner_device,
        burn_speed=req.burn_speed,
        use_gpu=req.use_gpu,
        passthrough=req.passthrough,
        selected_subtitle_indices=req.selected_subtitle_indices,
    )
    await job_manager.start_job(
        job_id, scratch_dir=get_scratch_dir(), output_dir=get_output_dir()
    )
    job = job_manager.get_job(job_id)
    status_val = "queued" if (job and job.stage == JobStage.QUEUED) else "started"
    return {"job_id": job_id, "status": status_val}



@app.post("/api/burn-iso")
async def burn_iso(req: BurnIsoRequest):
    if not os.path.exists(req.iso_path):
        raise HTTPException(
            status_code=404, detail=f"ISO file does not exist: {req.iso_path}"
        )

    disc_type = DiscType.BD25 if req.is_bluray else DiscType.DVD5
    output_name = os.path.splitext(os.path.basename(req.iso_path))[0]
    job_id = job_manager.create_job(
        input_files=[req.iso_path],
        disc_type=disc_type,
        output_mode=OutputMode.BURN_DIRECT,
        output_name=output_name,
        burner_device=req.device_path,
        burn_speed=req.burn_speed,
    )
    task = asyncio.create_task(
        _run_burn_iso_pipeline(
            job_id=job_id,
            iso_path=req.iso_path,
            device_path=req.device_path,
            speed=req.burn_speed,
            is_bluray=req.is_bluray,
        )
    )
    job_manager.active_tasks[job_id] = task
    return {"job_id": job_id, "status": "started"}


@app.post("/api/preview")
async def create_preview(req: CreatePreviewRequest):
    if not os.path.exists(req.input_file):
        raise HTTPException(
            status_code=404, detail=f"Input file does not exist: {req.input_file}"
        )

    clean_name = "".join([c if c.isalnum() else "_" for c in req.output_name.strip()]) or "preview_sample"
    if clean_name.startswith("preview_"):
        clean_name = clean_name[len("preview_"):]

    job_id = job_manager.create_job(
        input_files=[req.input_file],
        disc_type=req.disc_type,
        output_mode=req.preview_mode,
        output_name=clean_name,
        tv_standard=req.tv_standard,
        aspect_ratio=req.aspect_ratio,
        menu_mode=req.menu_mode,
        use_gpu=req.use_gpu,
        passthrough=req.passthrough,
        selected_subtitle_indices=req.selected_subtitle_indices,
    )

    await job_manager.start_job(
        job_id, scratch_dir=get_scratch_dir(), output_dir=get_output_dir()
    )

    ext = ".iso" if req.preview_mode == OutputMode.PREVIEW_ISO else (
        ".m2ts" if req.disc_type in (DiscType.BD25, DiscType.BD50, DiscType.BD66, DiscType.BD100, DiscType.BD128) else ".mpg"
    )
    output_path = os.path.join(get_output_dir(), f"preview_{clean_name}{ext}")

    return {
        "job_id": job_id,
        "status": "started",
        "preview_mode": req.preview_mode.value,
        "output_path": output_path,
    }


@app.get("/api/jobs")
def list_jobs():
    return list(job_manager.jobs.values())


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.cancel_job(job_id)
    return {"status": "cancelled"}


@app.post("/api/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.pause_job(job_id)
    return {"status": "paused"}


@app.post("/api/jobs/{job_id}/resume")
async def resume_job_endpoint(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.resume_job(job_id)
    return {"status": "resumed"}


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    queue = asyncio.Queue()
    job_manager.register_listener(job_id, queue)

    # Send initial state if job exists
    job = job_manager.get_job(job_id)
    if job:
        await websocket.send_json(job.model_dump(mode="json"))

    try:
        while True:
            data = await queue.get()
            # If data is already a dict, convert any models/enums or send directly
            if hasattr(data, "model_dump"):
                data = data.model_dump(mode="json")
            await websocket.send_json(data)
    except WebSocketDisconnect:
        job_manager.unregister_listener(job_id, queue)
    except Exception:
        job_manager.unregister_listener(job_id, queue)


# Locate and mount static frontend assets
def _resolve_static_directory() -> Optional[str]:
    candidates = [
        os.path.join(os.path.dirname(__file__), "static"),
        "/app/src/dvdcompress/static",
        os.path.abspath(os.path.join(os.getcwd(), "src", "dvdcompress", "static")),
    ]
    for p in candidates:
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "index.html")):
            return p
    return None

static_dir = _resolve_static_directory()
if static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
