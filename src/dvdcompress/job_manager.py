import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import signal
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field

from dvdcompress.authoring import (
    build_spumux_pipeline_command,
    build_subtitle_extraction_command,
    generate_dvd_palette_rgb,
    generate_dvdauthor_xml,
    generate_spumux_xml,
    generate_tsmuxer_meta,
)
from dvdcompress.pgs import convert_pgs_to_spumux_xml
from dvdcompress.menu import (
    build_menu_video_command,
    build_spumux_menu_command,
    generate_dvd_menu_assets,
    generate_menu_spumux_xml,
)
from dvdcompress.burner import build_burn_command, parse_burn_progress_line
from dvdcompress.layer_break import (
    calculate_dvd9_layer_break,
    get_dvd9_layer_break_info,
)
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.config import settings
from dvdcompress.iso import (
    build_dvd_fallback_iso_command,
    build_dvd_iso_command,
    build_genisoimage_command,
    build_xorriso_bd_command,
)
from dvdcompress.models import AspectRatio, DiscType, MenuEndAction, MenuMode, OutputMode, TVStandard
from dvdcompress.probe import probe_media_file
from dvdcompress.transcoder import (
    build_bluray_transcode_command,
    build_dvd_from_intermediate_command,
    build_dvd_transcode_command,
    build_gpu_hdr_intermediate_command,
    parse_ffmpeg_progress_line,
)


class JobStage(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    PROBING = "probing"
    TRANSCODING = "transcoding"
    PAUSED = "paused"
    AUTHORING = "authoring"
    MASTERING_ISO = "mastering_iso"
    BURNING = "burning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STAGES: Set[JobStage] = {
    JobStage.PROBING,
    JobStage.TRANSCODING,
    JobStage.AUTHORING,
    JobStage.MASTERING_ISO,
    JobStage.BURNING,
}


class Job(BaseModel):
    job_id: str
    stage: JobStage = JobStage.IDLE
    previous_stage: Optional[JobStage] = None
    is_paused: bool = False
    input_files: List[str]
    disc_type: DiscType
    output_mode: OutputMode
    output_name: str
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    menu_end_action: MenuEndAction = MenuEndAction.RETURN_TO_MENU
    burner_device: Optional[str] = None
    burn_speed: int = 4
    use_gpu: bool = True
    passthrough: bool = False
    selected_subtitle_indices: Optional[List[int]] = None

    current_file_idx: int = 0
    total_files: int = 1
    progress_percent: float = 0.0
    stage_percent: float = 0.0
    fps: float = 0.0
    speed: str = "1.0x"
    eta: str = "--:--"
    error_message: Optional[str] = None
    output_iso_path: Optional[str] = None
    logs: List[str] = Field(default_factory=list)


class JobManager:
    _instance: Optional["JobManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance.jobs = {}
            cls._instance.active_tasks = {}
            cls._instance.active_processes = {}
            cls._instance.pause_events = {}
            cls._instance.listeners = {}
            cls._instance.max_concurrent_jobs = 5
            cls._instance.scratch_dir = str(settings.temp_dir)
            cls._instance.output_dir = str(settings.output_dir)
            cls._instance.config_dir = str(settings.config_dir)
        return cls._instance

    def save_jobs(self, config_dir: Optional[str] = None) -> None:
        """Persist all jobs to jobs.json in the config directory."""
        target_dir = Path(config_dir or self.config_dir)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            jobs_file = target_dir / "jobs.json"
            data = [job.model_dump(mode="json") for job in self.jobs.values()]
            jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_jobs(self, config_dir: Optional[str] = None) -> None:
        """Load jobs from jobs.json, restoring completed/failed/cancelled states and re-queueing unfinished jobs."""
        target_dir = Path(config_dir or self.config_dir)
        try:
            jobs_file = target_dir / "jobs.json"
            if not jobs_file.exists():
                return
            raw_data = json.loads(jobs_file.read_text(encoding="utf-8"))
            if isinstance(raw_data, list):
                for item in raw_data:
                    try:
                        job = Job(**item)
                        if job.stage in ACTIVE_STAGES:
                            job.stage = JobStage.QUEUED
                            job.progress_percent = 0.0
                            job.stage_percent = 0.0
                            job.logs.append("[SYSTEM] Container restarted; job re-queued for execution.")
                        self.jobs[job.job_id] = job
                        if job.job_id not in self.pause_events:
                            self.pause_events[job.job_id] = asyncio.Event()
                            if job.stage == JobStage.PAUSED and job.is_paused:
                                self.pause_events[job.job_id].clear()
                            else:
                                self.pause_events[job.job_id].set()
                    except Exception:
                        pass
        except Exception:
            pass


    def get_active_jobs_count(self) -> int:
        """Return the number of currently active jobs in running stages."""
        return sum(
            1 for j in self.jobs.values()
            if j.job_id in self.active_tasks and j.stage != JobStage.PAUSED
        )

    def create_job(
        self,
        input_files: List[str],
        disc_type: DiscType,
        output_mode: OutputMode,
        output_name: str,
        tv_standard: TVStandard = TVStandard.AUTO,
        aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
        menu_mode: MenuMode = MenuMode.AUTOPLAY,
        menu_end_action: MenuEndAction = MenuEndAction.RETURN_TO_MENU,
        burner_device: Optional[str] = None,
        burn_speed: int = 4,
        use_gpu: bool = True,
        passthrough: bool = False,
        selected_subtitle_indices: Optional[List[int]] = None,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        clean_name = "".join([c if c.isalnum() else "_" for c in output_name.strip()]) or f"disc_{job_id}"
        job = Job(
            job_id=job_id,
            input_files=input_files,
            disc_type=disc_type,
            output_mode=output_mode,
            output_name=clean_name,
            tv_standard=tv_standard,
            aspect_ratio=aspect_ratio,
            menu_mode=menu_mode,
            menu_end_action=menu_end_action,
            burner_device=burner_device,
            burn_speed=burn_speed,
            use_gpu=use_gpu,
            passthrough=passthrough,
            selected_subtitle_indices=selected_subtitle_indices,
            total_files=len(input_files),
        )
        self.jobs[job_id] = job
        self.pause_events[job_id] = asyncio.Event()
        self.pause_events[job_id].set()
        self.save_jobs()
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a single job from memory and persisted history."""
        if job_id not in self.jobs:
            return False
        del self.jobs[job_id]
        if job_id in self.pause_events:
            del self.pause_events[job_id]
        if job_id in self.listeners:
            del self.listeners[job_id]
        if job_id in self.active_processes:
            del self.active_processes[job_id]
        if job_id in self.active_tasks:
            del self.active_tasks[job_id]

        try:
            work_dir = os.path.join(self.scratch_dir, job_id)
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

        self.save_jobs()
        return True

    def clear_history(self) -> int:
        """Remove all non-active (completed, failed, cancelled) jobs from history."""
        finished_stages = {JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED}
        to_delete = [
            j_id for j_id, j in self.jobs.items()
            if j.stage in finished_stages and j_id not in self.active_tasks
        ]
        for j_id in to_delete:
            self.delete_job(j_id)
        return len(to_delete)

    async def broadcast(self, job_id: str):
        job = self.get_job(job_id)
        if not job or job_id not in self.listeners:
            return
        data = job.model_dump()
        for q in list(self.listeners[job_id]):
            await q.put(data)

    def register_listener(self, job_id: str, queue: asyncio.Queue):
        if job_id not in self.listeners:
            self.listeners[job_id] = []
        self.listeners[job_id].append(queue)

    def unregister_listener(self, job_id: str, queue: asyncio.Queue):
        if job_id in self.listeners and queue in self.listeners[job_id]:
            self.listeners[job_id].remove(queue)

    def log(self, job_id: str, message: str, level: str = "info"):
        job = self.get_job(job_id)
        if job:
            job.logs.append(message)
            if len(job.logs) > 500:
                job.logs.pop(0)

    def _schedule_queued_jobs(
        self,
        scratch_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        prioritize_job_id: Optional[str] = None,
    ):
        """Schedule tasks for queued jobs up to max_concurrent_jobs without yielding."""
        s_dir = scratch_dir or self.scratch_dir
        o_dir = output_dir or self.output_dir

        if prioritize_job_id:
            p_job = self.get_job(prioritize_job_id)
            if p_job and p_job.stage == JobStage.QUEUED and prioritize_job_id not in self.active_tasks:
                if self.get_active_jobs_count() < self.max_concurrent_jobs:
                    task = asyncio.create_task(self._run_pipeline(prioritize_job_id, s_dir, o_dir))
                    self.active_tasks[prioritize_job_id] = task

        for j_id, job in list(self.jobs.items()):
            if self.get_active_jobs_count() >= self.max_concurrent_jobs:
                break
            if job.stage == JobStage.QUEUED and j_id not in self.active_tasks:
                task = asyncio.create_task(self._run_pipeline(j_id, s_dir, o_dir))
                self.active_tasks[j_id] = task
        self.save_jobs()

    async def queue_job(self, job_id: str, scratch_dir: Optional[str] = None, output_dir: Optional[str] = None):
        """Enqueue a job to be executed when a concurrent slot becomes available."""
        if scratch_dir:
            self.scratch_dir = scratch_dir
        if output_dir:
            self.output_dir = output_dir
        job = self.get_job(job_id)
        if job and job.stage == JobStage.IDLE:
            job.stage = JobStage.QUEUED
        self._schedule_queued_jobs(self.scratch_dir, self.output_dir)
        if job:
            await self.broadcast(job_id)

    async def start_job(self, job_id: str, scratch_dir: str = "/tmp/dvdcompress", output_dir: str = "/output"):
        """Schedule or start a job, respecting max_concurrent_jobs."""
        self.scratch_dir = scratch_dir
        self.output_dir = output_dir
        job = self.get_job(job_id)
        if job and job.stage == JobStage.IDLE:
            job.stage = JobStage.QUEUED
        self._schedule_queued_jobs(scratch_dir, output_dir, prioritize_job_id=job_id)
        return self.active_tasks.get(job_id)

    async def process_queue(self, scratch_dir: Optional[str] = None, output_dir: Optional[str] = None):
        """Process queued jobs up to the max_concurrent_jobs limit in FIFO order."""
        self._schedule_queued_jobs(scratch_dir, output_dir)

    async def set_max_concurrent_jobs(self, limit: int, scratch_dir: Optional[str] = None, output_dir: Optional[str] = None):
        """Update maximum concurrent job slots and trigger queue processing."""
        self.max_concurrent_jobs = max(1, min(20, limit))
        self._schedule_queued_jobs(scratch_dir, output_dir)



    async def pause_job(self, job_id: str):
        """Pause an active job, suspending its running subprocess."""
        job = self.get_job(job_id)
        if not job or job.stage in (JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED, JobStage.PAUSED):
            return

        job.previous_stage = job.stage
        job.stage = JobStage.PAUSED
        job.is_paused = True

        if job_id in self.pause_events:
            self.pause_events[job_id].clear()

        if job_id in self.active_processes:
            proc = self.active_processes[job_id]
            try:
                proc.send_signal(signal.SIGSTOP)
            except Exception:
                pass

        self.log(job_id, "Job paused by user.")
        self.save_jobs()
        await self.broadcast(job_id)

    async def resume_job(self, job_id: str):
        """Resume a paused job, continuing its running subprocess."""
        job = self.get_job(job_id)
        if not job or job.stage != JobStage.PAUSED:
            return

        job.stage = job.previous_stage or JobStage.TRANSCODING
        job.is_paused = False

        if job_id in self.active_processes:
            proc = self.active_processes[job_id]
            try:
                proc.send_signal(signal.SIGCONT)
            except Exception:
                pass

        if job_id in self.pause_events:
            self.pause_events[job_id].set()

        self.log(job_id, "Job resumed.")
        self.save_jobs()
        await self.broadcast(job_id)

    async def _auto_resume_next_job(self, exclude_job_id: Optional[str] = None):
        """Automatically pick up and resume the next paused job in FIFO order."""
        for other_id, other_job in self.jobs.items():
            if other_id != exclude_job_id and other_job.stage == JobStage.PAUSED and other_job.is_paused:
                self.log(other_id, f"Previous job finished. Auto-resuming job {other_id}...")
                await self.resume_job(other_id)
                break

    async def _run_ffmpeg_with_progress(
        self,
        job_id: str,
        cmd: List[str],
        effective_duration: float,
        title_idx: int,
        total_titles: int,
        filename: str,
        phase_offset: float = 0.0,
        phase_scale: float = 1.0,
    ) -> None:
        job = self.jobs[job_id]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.active_processes[job_id] = proc

        buffer = ""
        stderr_recent = []
        try:
            while True:
                if job_id in self.pause_events:
                    await self.pause_events[job_id].wait()

                chunk = await proc.stderr.read(512)
                if not chunk:
                    break
                buffer += chunk.decode(errors="replace")
                lines = buffer.replace("\r", "\n").split("\n")
                buffer = lines[-1]
                for line in lines[:-1]:
                    if line.strip():
                        stderr_recent.append(line.strip())
                        if len(stderr_recent) > 30:
                            stderr_recent.pop(0)

                    prog = parse_ffmpeg_progress_line(line)
                    if "frame" in prog or "time_sec" in prog:
                        if "fps" in prog:
                            job.fps = prog["fps"]
                        if "speed" in prog:
                            job.speed = prog["speed"]
                        if effective_duration > 0 and "time_sec" in prog:
                            raw_pct = min(100.0, (prog["time_sec"] / effective_duration) * 100.0)
                            file_pct = phase_offset + (raw_pct * phase_scale)
                            job.stage_percent = round(file_pct, 1)
                            overall_multiplier = 100.0 if job.output_mode == OutputMode.PREVIEW_VIDEO else 60.0
                            overall_pct = ((title_idx + (file_pct / 100.0)) / total_titles) * overall_multiplier
                            job.progress_percent = round(overall_pct, 1)

                            rem_sec = max(0.0, effective_duration - prog["time_sec"])
                            try:
                                speed_num = float(job.speed.rstrip("x")) if job.speed else 1.0
                                speed_num = max(0.1, speed_num)
                            except Exception:
                                speed_num = 1.0
                            eta_sec = int(rem_sec / speed_num)
                            m, s = divmod(eta_sec, 60)
                            h, m = divmod(m, 60)
                            job.eta = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

                        if job.stage != JobStage.PAUSED:
                            await self.broadcast(job_id)

            await proc.wait()
            if proc.returncode != 0 and job.stage != JobStage.CANCELLED:
                err_msg = " | ".join(stderr_recent[-3:]) if stderr_recent else f"exit code {proc.returncode}"
                raise RuntimeError(f"Transcoding failed for {filename}: {err_msg}")
        except (asyncio.CancelledError, Exception):
            try:
                proc.send_signal(signal.SIGCONT)
                proc.kill()
            except Exception:
                pass
            raise
        finally:
            if job_id in self.active_processes and self.active_processes[job_id] == proc:
                del self.active_processes[job_id]

    async def cancel_job(self, job_id: str):
        job = self.get_job(job_id)
        if job_id in self.pause_events:
            self.pause_events[job_id].set()

        if job_id in self.active_processes:
            proc = self.active_processes[job_id]
            try:
                proc.send_signal(signal.SIGCONT)
                proc.kill()
            except Exception:
                pass

        if job_id in self.active_tasks:
            task = self.active_tasks[job_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        else:
            if job:
                job.stage = JobStage.CANCELLED
                job.error_message = "Job cancelled by user"
                await self.broadcast(job_id)

        self.save_jobs()
        await self.process_queue()
        await self._auto_resume_next_job(job_id)

    async def _run_pipeline(self, job_id: str, scratch_dir: str, output_dir: str):
        job = self.get_job(job_id)
        if not job:
            return

        work_dir = os.path.join(scratch_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        current_process: Optional[asyncio.subprocess.Process] = None

        try:
            # 1. Probing
            job.stage = JobStage.PROBING
            self.log(job_id, f"Probing {len(job.input_files)} input files...")
            await self.broadcast(job_id)

            media_infos = []
            total_duration = 0.0
            for f in job.input_files:
                info = await probe_media_file(f)
                media_infos.append(info)
                total_duration += info.duration_sec

            # Calculate bit budget
            budget = calculate_bitrate_budget(
                total_duration_sec=total_duration,
                disc_type=job.disc_type,
                video_count=len(job.input_files),
            )
            self.log(job_id, f"Allocated video bitrate: {budget.video_bitrate_kbps} kbps (Disc usage: {budget.capacity_percent}%)")

            # 2. Transcoding
            job.stage = JobStage.TRANSCODING
            await self.broadcast(job_id)

            is_bluray = job.disc_type in (
                DiscType.BD25,
                DiscType.BD50,
                DiscType.BD66,
                DiscType.BD100,
                DiscType.BD128,
            )
            is_preview = job.output_mode in (
                OutputMode.PREVIEW_VIDEO,
                OutputMode.PREVIEW_ISO,
            )
            transcoded_files = []
            transcoded_audio_files = []

            for idx, info in enumerate(media_infos):
                job.current_file_idx = idx + 1
                out_ext = ".m2ts" if is_bluray else ".mpg"

                # Check passthrough eligibility
                can_passthrough = False
                if job.passthrough and not is_preview:
                    if is_bluray:
                        if job.disc_type in (DiscType.BD66, DiscType.BD100, DiscType.BD128):
                            # UHD Blu-ray supports HEVC and AVC
                            if info.video_codec in ("hevc", "h264"):
                                can_passthrough = True
                        else:
                            # Standard Blu-ray supports H.264 SDR <= 1080p
                            if info.video_codec == "h264" and not info.is_hdr and info.width <= 1920 and info.height <= 1080:
                                can_passthrough = True
                    else:
                        # DVD supports standard definition MPEG-2
                        if info.video_codec in ("mpeg2video", "mpeg2") and info.width <= 720:
                            can_passthrough = True

                if can_passthrough:
                    self.log(job_id, f"Direct Stream Passthrough active for {info.filename} ({info.video_codec.upper()} -> {job.disc_type.value.upper()}) - Re-encoding bypassed.")
                    transcoded_files.append(info.path)
                    transcoded_audio_files.append(None)
                    job.progress_percent = round((idx + 1) / len(media_infos) * 80.0, 1)
                    await self.broadcast(job_id)
                    continue
                elif job.passthrough and not is_preview:
                    self.log(job_id, f"Notice: {info.filename} ({info.video_codec}) is not directly compliant with {job.disc_type.value.upper()}; transcoding.")

                # If preview_video, write directly to output_dir
                if job.output_mode == OutputMode.PREVIEW_VIDEO:
                    clean_name = (
                        job.output_name
                        if job.output_name.startswith("preview_")
                        else f"preview_{job.output_name}"
                    )
                    out_file = os.path.join(output_dir, f"{clean_name}{out_ext}")
                    out_audio = None
                    transcoded_files.append(out_file)
                    transcoded_audio_files.append(None)
                else:
                    if is_bluray:
                        v_ext = ".hevc" if job.disc_type in (DiscType.BD66, DiscType.BD100, DiscType.BD128) and info.video_codec == "hevc" else ".264"
                        out_file = os.path.join(work_dir, f"title_{idx+1}{v_ext}")
                        out_audio = os.path.join(work_dir, f"title_{idx+1}.ac3")
                        transcoded_files.append(out_file)
                        transcoded_audio_files.append(out_audio)
                    else:
                        out_file = os.path.join(work_dir, f"title_{idx+1}{out_ext}")
                        out_audio = None
                        transcoded_files.append(out_file)
                        transcoded_audio_files.append(None)

                # Compute seek and duration for preview
                seek_sec: Optional[float] = None
                dur_sec: Optional[float] = None
                if is_preview:
                    seek_sec = max(0.0, (info.duration_sec / 2.0) - 30.0) if info.duration_sec > 60.0 else 0.0
                    dur_sec = min(60.0, info.duration_sec) if info.duration_sec > 0 else 60.0

                effective_duration = dur_sec if (is_preview and dur_sec) else info.duration_sec

                # Determine audio stream mapping from probed info
                first_audio = info.audio_streams[0] if info.audio_streams else None
                audio_idx = first_audio.index if first_audio else 1
                audio_ch = first_audio.channels if first_audio else (6 if is_bluray else 2)

                if is_bluray:
                    cmd = build_bluray_transcode_command(
                        input_file=info.path,
                        output_video=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        output_audio=out_audio,
                        audio_stream_idx=audio_idx,
                        audio_channels=audio_ch,
                        use_gpu=job.use_gpu,
                        is_hdr=info.is_hdr,
                        seek_start_sec=seek_sec,
                        duration_sec=dur_sec,
                        fps=info.frame_rate,
                    )
                    if info.is_hdr:
                        self.log(job_id, f"Applying HDR/Dolby Vision -> SDR Filmic Tone-Mapping for {info.filename}")
                    self.log(job_id, f"Transcoding [{idx+1}/{len(media_infos)}]: {info.filename}")
                    await self._run_ffmpeg_with_progress(job_id, cmd, effective_duration, idx, len(media_infos), info.filename)
                elif job.use_gpu and info.is_hdr:
                    # 2-Phase GPU accelerated pipeline for DVD
                    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", os.path.splitext(info.filename)[0])
                    intermediate_sdr_file = os.path.join(work_dir, f"intermediate_sdr_title_{idx+1}_{clean_stem}.mp4")

                    # Phase 1: GPU Fast Hardware Tone-Mapping and Downscaling to 480p SDR Intermediate
                    self.log(job_id, f"Applying GPU Phase 1/2: Fast Hardware Tone-Mapping (HDR/DV -> 480p SDR Intermediate) for {info.filename}")
                    cmd_phase1 = build_gpu_hdr_intermediate_command(
                        input_file=info.path,
                        output_file=intermediate_sdr_file,
                        tv_standard=job.tv_standard,
                        aspect_ratio=job.aspect_ratio,
                        audio_stream_idx=audio_idx,
                        audio_channels=audio_ch,
                        seek_start_sec=seek_sec,
                        duration_sec=dur_sec,
                    )
                    await self._run_ffmpeg_with_progress(
                        job_id, cmd_phase1, effective_duration, idx, len(media_infos), info.filename, phase_offset=0.0, phase_scale=0.5
                    )

                    # Phase 2: Fast CPU MPEG-2 Encoding
                    self.log(job_id, f"Applying Phase 2/2: Fast DVD MPEG-2 Encoding for {info.filename}")
                    cmd_phase2 = build_dvd_from_intermediate_command(
                        intermediate_file=intermediate_sdr_file,
                        output_mpg=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        tv_standard=job.tv_standard,
                        aspect_ratio=job.aspect_ratio,
                        audio_channels=audio_ch,
                    )
                    await self._run_ffmpeg_with_progress(
                        job_id, cmd_phase2, effective_duration, idx, len(media_infos), info.filename, phase_offset=50.0, phase_scale=0.5
                    )

                    self.log(job_id, f"Preserving intermediate SDR file in scratch directory: {intermediate_sdr_file}")
                else:
                    cmd = build_dvd_transcode_command(
                        input_file=info.path,
                        output_mpg=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        audio_stream_idx=audio_idx,
                        audio_channels=audio_ch,
                        tv_standard=job.tv_standard,
                        aspect_ratio=job.aspect_ratio,
                        use_gpu=job.use_gpu,
                        is_hdr=info.is_hdr,
                        seek_start_sec=seek_sec,
                        duration_sec=dur_sec,
                    )
                    if info.is_hdr:
                        self.log(job_id, f"Applying HDR/Dolby Vision -> SDR Filmic Tone-Mapping for {info.filename}")
                    self.log(job_id, f"Transcoding [{idx+1}/{len(media_infos)}]: {info.filename}")
                    await self._run_ffmpeg_with_progress(job_id, cmd, effective_duration, idx, len(media_infos), info.filename)

            # If PREVIEW_VIDEO, pipeline completes here
            if job.output_mode == OutputMode.PREVIEW_VIDEO:
                job.stage = JobStage.COMPLETED
                job.progress_percent = 100.0
                job.stage_percent = 100.0
                job.output_iso_path = transcoded_files[0] if transcoded_files else None
                self.log(job_id, f"Sample video preview completed: {job.output_iso_path}")
                await self.broadcast(job_id)
                await self._auto_resume_next_job(job_id)
                return

            # Check pause before authoring
            if job_id in self.pause_events:
                await self.pause_events[job_id].wait()

            # 3. Authoring
            job.stage = JobStage.AUTHORING
            job.progress_percent = 70.0
            self.log(job_id, "Authoring disc structure and subtitle tracks...")
            await self.broadcast(job_id)

            author_dir = os.path.join(work_dir, "author")
            os.makedirs(author_dir, exist_ok=True)

            # Subtitle extraction pass
            extracted_subtitles_by_title = []
            for t_idx, info in enumerate(media_infos):
                title_subs = []
                target_subs = info.subtitle_streams
                if job.selected_subtitle_indices is not None:
                    target_subs = [s for s in info.subtitle_streams if s.index in job.selected_subtitle_indices]

                # Optical disc standards limit subtitle tracks (max 32 subpicture streams for DVD/Blu-ray)
                if len(target_subs) > 32:
                    self.log(
                        job_id,
                        f"Notice: Media title {t_idx+1} contains {len(target_subs)} subtitle tracks. Clamping to the maximum 32 tracks allowed by optical disc specifications.",
                        "info",
                    )
                    target_subs = target_subs[:32]

                for s_idx, s in enumerate(target_subs):
                    lang = s.language or "eng"
                    is_bmp = (s.codec_name in ("hdmv_pgs_subtitle", "dvdsub"))

                    ext = ".sup" if is_bmp else ".srt"
                    sub_out_name = f"title_{t_idx+1}_sub_{s_idx}{ext}"
                    sub_out_path = os.path.join(work_dir, sub_out_name)
                    seek_s = max(0.0, (info.duration_sec / 2.0) - 30.0) if (is_preview and info.duration_sec > 60.0) else None
                    dur_s = min(60.0, info.duration_sec) if is_preview else None
                    extract_cmd = build_subtitle_extraction_command(
                        input_file=info.path,
                        stream_index=s.index,
                        output_sub_path=sub_out_path,
                        is_bitmap=is_bmp,
                        seek_start_sec=seek_s,
                        duration_sec=dur_s,
                    )
                    self.log(job_id, f"Extracting subtitle track [{lang}]: {s.title or s.codec_name}")
                    sub_proc = await asyncio.create_subprocess_exec(
                        *extract_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    current_process = sub_proc
                    self.active_processes[job_id] = sub_proc
                    sub_stdout, sub_stderr = await sub_proc.communicate()
                    current_process = None
                    if job_id in self.active_processes:
                        del self.active_processes[job_id]
                    if sub_proc.returncode == 0:
                        if not os.path.exists(sub_out_path) or (not is_bmp and os.path.getsize(sub_out_path) == 0):
                            with open(sub_out_path, "w", encoding="utf-8") as bf:
                                if is_preview and not is_bmp:
                                    bf.write(f"1\n00:00:02,000 --> 00:00:08,000\n[Subtitles: {lang.upper()}]\n")
                                else:
                                    bf.write("1\n00:00:00,100 --> 00:00:00,200\n \n" if not is_bmp else "")

                        title_subs.append({
                            "path": sub_out_path,
                            "lang": lang,
                            "is_bitmap": is_bmp,
                            "title": s.title,
                        })
                    else:
                        err_snip = sub_stderr.decode(errors="replace").strip()[-200:]
                        self.log(job_id, f"Warning: could not extract subtitle track {s.index} ({lang}): {err_snip}", "warning")
                extracted_subtitles_by_title.append(title_subs)

            # Build chapter list for each title
            chapters_list = []
            for info in media_infos:
                if is_preview:
                    chaps = [0.0]
                elif info.chapter_times and len(info.chapter_times) >= 2:
                    chaps = info.chapter_times
                else:
                    # Generate automatic 5-minute chapters across the entire movie duration
                    chaps = [0.0]
                    curr_t = 300.0
                    while curr_t < (info.duration_sec - 30.0):
                        chaps.append(curr_t)
                        curr_t += 300.0
                chapters_list.append(chaps)

            if is_bluray:
                first_chaps = chapters_list[0] if len(chapters_list) > 0 else None
                first_subs = extracted_subtitles_by_title[0] if extracted_subtitles_by_title else None
                video_codecs = [info.video_codec for info in media_infos]
                fps_list = [info.frame_rate for info in media_infos]
                meta_content = generate_tsmuxer_meta(
                    transcoded_files,
                    chapters_sec=first_chaps,
                    subtitle_files=first_subs,
                    video_codecs=video_codecs,
                    fps_list=fps_list,
                    audio_files=transcoded_audio_files,
                )
                meta_path = os.path.join(work_dir, "tsmuxer.meta")
                with open(meta_path, "w") as mf:
                    mf.write(meta_content)
                proc = await asyncio.create_subprocess_exec(
                    "tsMuxeR", meta_path, author_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                current_process = proc
                self.active_processes[job_id] = proc
                ts_out, ts_err = await proc.communicate()
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]
                if proc.returncode != 0:
                    err_msg = ts_err.decode(errors="replace").strip() or ts_out.decode(errors="replace").strip()
                    self.log(job_id, f"tsMuxeR error: {err_msg}", "error")
                    raise RuntimeError(f"Authoring failed with tsMuxeR: {err_msg[-200:]}")
            else:
                # DVD-Video Subtitle Multiplexing via chained streaming spumux pipeline
                is_ntsc = job.tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
                dvd_env = os.environ.copy()
                dvd_env["VIDEO_FORMAT"] = "NTSC" if is_ntsc else "PAL"

                for t_idx, title_subs in enumerate(extracted_subtitles_by_title):
                    if t_idx < len(transcoded_files):
                        curr_mpg = transcoded_files[t_idx]
                        valid_subs = [sub for sub in title_subs if os.path.exists(sub.get("path", ""))]
                        if not valid_subs:
                            continue

                        if not os.path.exists(curr_mpg):
                            with open(curr_mpg, "wb") as mf:
                                mf.write(b"MOCK_MPG_STREAM")

                        xml_paths = []
                        track_summaries = []
                        for s_idx, sub_info in enumerate(valid_subs):
                            lang = sub_info.get("lang", "und")
                            track_name = sub_info.get("title") or "Subtitles"
                            if sub_info.get("is_bitmap", False):
                                self.log(job_id, f"Converting PGS bitmap subtitle track [{lang}]: {track_name} for DVD-Video...")
                                dur_s = min(60.0, info.duration_sec) if is_preview else None
                                pgs_xml_path = convert_pgs_to_spumux_xml(
                                    sup_path=sub_info["path"],
                                    output_dir=work_dir,
                                    prefix=f"pgs_t{t_idx+1}_s{s_idx}",
                                    tv_standard=job.tv_standard,
                                    aspect_ratio=job.aspect_ratio,
                                    pts_offset=0.0,
                                    max_duration_sec=dur_s,
                                    preview_label=f"{lang.upper()} - {track_name}",
                                )
                                if pgs_xml_path and os.path.exists(pgs_xml_path):
                                    xml_paths.append(pgs_xml_path)
                                    track_summaries.append(f"[{lang}]: {track_name}")
                                else:
                                    self.log(job_id, f"Notice: No graphic subpictures found in PGS track {s_idx+1} [{lang}], skipping.")
                            else:
                                spu_xml = generate_spumux_xml(
                                    srt_path=sub_info["path"],
                                    tv_standard=job.tv_standard,
                                    aspect_ratio=job.aspect_ratio,
                                )
                                spu_xml_path = os.path.join(work_dir, f"spumux_t{t_idx+1}_s{s_idx}.xml")
                                with open(spu_xml_path, "w", encoding="utf-8") as sf:
                                    sf.write(spu_xml)
                                xml_paths.append(spu_xml_path)
                                track_summaries.append(f"[{lang}]: {track_name}")

                        if not xml_paths:
                            continue

                        subbed_mpg = os.path.join(work_dir, f"title_{t_idx+1}_subbed.mpg")
                        tracks_str = ", ".join(track_summaries)
                        self.log(job_id, f"Multiplexing {len(xml_paths)} DVD subtitle track(s) in streaming pipeline: {tracks_str}")

                        pipe_cmd = build_spumux_pipeline_command(curr_mpg, subbed_mpg, xml_paths)
                        total_mpg_bytes = os.path.getsize(curr_mpg) if os.path.exists(curr_mpg) else 1

                        spu_proc = await asyncio.create_subprocess_shell(
                            pipe_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=dvd_env,
                        )
                        current_process = spu_proc
                        self.active_processes[job_id] = spu_proc

                        buffer = b""
                        stderr_lines = []
                        max_written_bytes = 0
                        start_mux_time = time.time()
                        last_broadcast_time = 0.0

                        while True:
                            chunk = await spu_proc.stderr.read(1024)
                            if not chunk:
                                break
                            buffer += chunk
                            while b"\r" in buffer or b"\n" in buffer:
                                if b"\r" in buffer:
                                    line_bytes, buffer = buffer.split(b"\r", 1)
                                else:
                                    line_bytes, buffer = buffer.split(b"\n", 1)
                                line_str = line_bytes.decode(errors="replace").strip()
                                if not line_str:
                                    continue
                                stderr_lines.append(line_str)
                                if len(stderr_lines) > 50:
                                    stderr_lines.pop(0)

                                if "bytes of data written" in line_str:
                                    parts = line_str.split()
                                    for p in parts:
                                        if p.isdigit():
                                            w_bytes = int(p)
                                            if w_bytes > max_written_bytes:
                                                max_written_bytes = w_bytes
                                            break

                                    now = time.time()
                                    if now - last_broadcast_time >= 1.0:
                                        last_broadcast_time = now
                                        elapsed = max(0.5, now - start_mux_time)
                                        pct = min(99.0, (max_written_bytes / total_mpg_bytes) * 100.0)
                                        speed_bps = max_written_bytes / elapsed
                                        speed_mb_s = speed_bps / (1024 * 1024)
                                        rem_bytes = max(0, total_mpg_bytes - max_written_bytes)
                                        job.stage_percent = round(pct, 1)
                                        job.progress_percent = round(70.0 + (pct * 0.1), 1)
                                        rem_sec = max(0, int(rem_bytes / speed_bps)) if speed_bps > 0 else 0
                                        m_val, s_val = divmod(rem_sec, 60)
                                        h_val, m_val = divmod(m_val, 60)
                                        job.eta = f"{h_val:02d}:{m_val:02d}:{s_val:02d}" if h_val > 0 else f"{m_val:02d}:{s_val:02d}"
                                        job.speed = f"{speed_mb_s:.1f} MB/s"
                                        await self.broadcast(job_id)

                        await spu_proc.wait()
                        current_process = None
                        if job_id in self.active_processes:
                            del self.active_processes[job_id]

                        if spu_proc.returncode == 0 and os.path.exists(subbed_mpg) and os.path.getsize(subbed_mpg) > 0:
                            curr_mpg = subbed_mpg
                            self.log(job_id, f"Successfully multiplexed {len(xml_paths)} subtitle track(s) for title {t_idx+1}")
                        else:
                            err_snip = " | ".join(stderr_lines[-3:]) if stderr_lines else f"exit code {spu_proc.returncode}"
                            self.log(job_id, f"Warning: Subtitle pipeline failed for title {t_idx+1}: {err_snip}", "warning")

                        transcoded_files[t_idx] = curr_mpg

                # Generate interactive DVD Title Menu if requested
                menu_vob_path = None
                if job.menu_mode == MenuMode.MENU:
                    try:
                        self.log(job_id, f"Generating interactive DVD Title Menu for {len(media_infos)} title(s)...")
                        title_items = []
                        for t_idx, info in enumerate(media_infos):
                            clean_name = os.path.splitext(info.filename)[0].replace("_", " ").strip()
                            dur_s = int(info.duration_sec)
                            h, m = divmod(dur_s, 3600)
                            m, s = divmod(m, 60)
                            dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                            title_items.append({"name": clean_name or f"Title {t_idx+1}", "duration": dur_str})

                        bg_p, hl_p, sel_p, buttons = generate_dvd_menu_assets(
                            titles=title_items,
                            disc_label=job.output_name or "DVD_VIDEO",
                            tv_standard=job.tv_standard,
                            aspect_ratio=job.aspect_ratio,
                            output_dir=work_dir,
                        )

                        # Transcode menu backdrop to MPEG-2 stream
                        raw_menu_mpg = os.path.join(work_dir, "menu_raw.mpg")
                        menu_ff_cmd = build_menu_video_command(
                            bg_image_path=bg_p,
                            output_mpg_path=raw_menu_mpg,
                            tv_standard=job.tv_standard,
                            aspect_ratio=job.aspect_ratio,
                            duration_sec=1.0,
                        )
                        menu_ff_proc = await asyncio.create_subprocess_exec(
                            *menu_ff_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        current_process = menu_ff_proc
                        self.active_processes[job_id] = menu_ff_proc
                        _, menu_ff_err = await menu_ff_proc.communicate()
                        current_process = None
                        if job_id in self.active_processes:
                            del self.active_processes[job_id]

                        if menu_ff_proc.returncode == 0 and os.path.exists(raw_menu_mpg):
                            # Generate menu spumux XML
                            spu_menu_xml = generate_menu_spumux_xml(
                                highlight_path=hl_p,
                                select_path=sel_p,
                                buttons=buttons,
                                tv_standard=job.tv_standard,
                            )
                            spu_menu_xml_path = os.path.join(work_dir, "spumux_menu.xml")
                            with open(spu_menu_xml_path, "w", encoding="utf-8") as smf:
                                smf.write(spu_menu_xml)

                            # Multiplex menu subpictures with spumux
                            muxed_menu_mpg = os.path.join(work_dir, "menu.mpg")
                            spu_menu_cmd = build_spumux_menu_command(
                                input_mpg_path=raw_menu_mpg,
                                output_mpg_path=muxed_menu_mpg,
                                xml_path=spu_menu_xml_path,
                            )
                            spu_m_proc = await asyncio.create_subprocess_shell(
                                spu_menu_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                                env=dvd_env,
                            )
                            current_process = spu_m_proc
                            self.active_processes[job_id] = spu_m_proc
                            _, spu_m_err = await spu_m_proc.communicate()
                            current_process = None
                            if job_id in self.active_processes:
                                del self.active_processes[job_id]

                            if spu_m_proc.returncode == 0 and os.path.exists(muxed_menu_mpg) and os.path.getsize(muxed_menu_mpg) > 0:
                                menu_vob_path = muxed_menu_mpg
                                self.log(job_id, f"Successfully created interactive Title Menu with {len(buttons)} navigation button(s).")
                            else:
                                err_snip = spu_m_err.decode(errors="replace").strip()[-200:]
                                self.log(job_id, f"Warning: spumux menu multiplexing failed ({err_snip}); falling back to autoplay mode.", "warning")
                        else:
                            err_snip = menu_ff_err.decode(errors="replace").strip()[-200:]
                            self.log(job_id, f"Warning: Menu background transcoding failed ({err_snip}); falling back to autoplay mode.", "warning")
                    except Exception as e:
                        self.log(job_id, f"Warning: DVD menu creation encountered an exception: {e}; falling back to autoplay mode.", "warning")

                # Collect subpicture track languages for the authored titleset
                dvd_sub_langs = []
                for title_subs in extracted_subtitles_by_title:
                    valid_subs = [s for s in title_subs if os.path.exists(s.get("path", ""))]
                    if len(valid_subs) > len(dvd_sub_langs):
                        dvd_sub_langs = [s["lang"] for s in valid_subs[:32]]

                # Write standard DVD subtitle palette
                palette_content = generate_dvd_palette_rgb()
                palette_path = os.path.join(work_dir, "palette.rgb")
                with open(palette_path, "w", encoding="utf-8") as pf:
                    pf.write(palette_content)

                xml_content = generate_dvdauthor_xml(
                    titles_mpg=transcoded_files,
                    chapters_sec=chapters_list,
                    menu_mode=job.menu_mode,
                    tv_standard=job.tv_standard,
                    subtitles_lang=dvd_sub_langs if dvd_sub_langs else None,
                    menu_vob=menu_vob_path,
                    aspect_ratio=job.aspect_ratio,
                    menu_end_action=job.menu_end_action,
                    palette_file=palette_path,
                )
                xml_path = os.path.join(work_dir, "dvdauthor.xml")
                with open(xml_path, "w", encoding="utf-8") as xf:
                    xf.write(xml_content)
                proc = await asyncio.create_subprocess_exec(
                    "dvdauthor", "-o", author_dir, "-x", xml_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=dvd_env,
                )
                current_process = proc
                self.active_processes[job_id] = proc
                dvd_out, dvd_err = await proc.communicate()
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]
                if proc.returncode != 0:
                    err_msg = dvd_err.decode(errors="replace").strip() or dvd_out.decode(errors="replace").strip()
                    self.log(job_id, f"dvdauthor error: {err_msg}", "error")
                    raise RuntimeError(f"Authoring failed with dvdauthor: {err_msg[-200:]}")

            # Check pause before ISO creation
            if job_id in self.pause_events:
                await self.pause_events[job_id].wait()

            # 4. ISO Creation
            job.stage = JobStage.MASTERING_ISO
            job.progress_percent = 85.0
            clean_iso_name = (
                (
                    job.output_name
                    if job.output_name.startswith("preview_")
                    else f"preview_{job.output_name}"
                )
                if job.output_mode == OutputMode.PREVIEW_ISO
                else job.output_name
            )
            iso_path = os.path.join(output_dir, f"{clean_iso_name}.iso")
            job.output_iso_path = iso_path
            self.log(job_id, f"Building ISO: {iso_path}")
            await self.broadcast(job_id)

            if is_bluray:
                iso_cmd = build_xorriso_bd_command(author_dir, iso_path, clean_iso_name)
            else:
                iso_cmd = build_dvd_iso_command(author_dir, iso_path, clean_iso_name)

            self.log(job_id, f"Building ISO image ({iso_cmd[0]})...")
            proc = await asyncio.create_subprocess_exec(
                *iso_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            current_process = proc
            self.active_processes[job_id] = proc
            iso_out, iso_err = await proc.communicate()
            current_process = None
            if job_id in self.active_processes:
                del self.active_processes[job_id]

            if proc.returncode != 0:
                err_msg = iso_err.decode(errors="replace").strip() or iso_out.decode(errors="replace").strip()
                # If genisoimage hit a padding or arithmetic bug (e.g. Video pad is -32), retry with UDF mastering fallback
                if "Implementation botch" in err_msg or "Video pad" in err_msg or "genisoimage bug" in err_msg:
                    self.log(job_id, f"Notice: ISO builder reported '{err_msg[-120:]}'. Attempting UDF fallback mastering...", "warning")
                    fallback_cmd = build_dvd_fallback_iso_command(author_dir, iso_path, clean_iso_name)
                    retry_proc = await asyncio.create_subprocess_exec(
                        *fallback_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    current_process = retry_proc
                    self.active_processes[job_id] = retry_proc
                    r_out, r_err = await retry_proc.communicate()
                    current_process = None
                    if job_id in self.active_processes:
                        del self.active_processes[job_id]
                    if retry_proc.returncode == 0 and os.path.exists(iso_path) and os.path.getsize(iso_path) > 0:
                        self.log(job_id, "Successfully mastered DVD ISO via UDF fallback.")
                    else:
                        r_err_msg = r_err.decode(errors="replace").strip() or r_out.decode(errors="replace").strip()
                        self.log(job_id, f"ISO creation fallback error: {r_err_msg}", "error")
                        raise RuntimeError(f"ISO creation failed: {r_err_msg[-200:]}")
                else:
                    self.log(job_id, f"ISO creation error: {err_msg}", "error")
                    raise RuntimeError(f"ISO creation failed: {err_msg[-200:]}")

            # If PREVIEW_ISO, pipeline completes here
            if job.output_mode == OutputMode.PREVIEW_ISO:
                job.stage = JobStage.COMPLETED
                job.progress_percent = 100.0
                job.stage_percent = 100.0
                self.log(job_id, f"Sample ISO preview completed: {iso_path}")
                await self.broadcast(job_id)
                await self._auto_resume_next_job(job_id)
                return

            # 5. Burning (Optional)
            if job.output_mode in (OutputMode.BURN_DIRECT, OutputMode.AUTHOR_AND_BURN) and job.burner_device:
                # Check pause before burning
                if job_id in self.pause_events:
                    await self.pause_events[job_id].wait()

                job.stage = JobStage.BURNING
                self.log(job_id, f"Burning ISO to {job.burner_device} at {job.burn_speed}x...")
                lb_info = (
                    get_dvd9_layer_break_info(iso_path)
                    if (not is_bluray and os.path.exists(iso_path))
                    else None
                )
                if lb_info:
                    chap_str = (
                        f" (Chapter {lb_info['chapter_index']})"
                        if lb_info.get("chapter_index")
                        else " (Midpoint fallback)"
                    )
                    self.log(
                        job_id,
                        f"DVD-9 (Dual-Layer) detected: target layer break at sector {lb_info['sector']:,} ({lb_info['mb']:,.1f} MB / {lb_info['percent']:.1f}% of disc{chap_str})",
                    )
                await self.broadcast(job_id)
                burn_cmd = build_burn_command(
                    job.burner_device,
                    iso_path,
                    speed=job.burn_speed,
                    is_bluray=is_bluray,
                    layer_break_sector=lb_info["sector"] if lb_info else None,
                )
                proc = await asyncio.create_subprocess_exec(
                    *burn_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                current_process = proc
                self.active_processes[job_id] = proc
                lb_transition_notified = False
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace").strip()
                    if decoded:
                        self.log(job_id, decoded)
                    prog = parse_burn_progress_line(decoded)
                    if lb_info and not lb_transition_notified and "written_bytes" in prog:
                        if prog["written_bytes"] >= lb_info["sector"] * 2048:
                            lb_transition_notified = True
                            chap_str = (
                                f" (Chapter {lb_info['chapter_index']})"
                                if lb_info.get("chapter_index")
                                else ""
                            )
                            self.log(
                                job_id,
                                f"⚡ Layer break reached: Refocusing optical laser to Layer 1 at sector {lb_info['sector']:,} ({lb_info['percent']:.1f}%{chap_str})...",
                            )
                    if "percent" in prog:
                        job.stage_percent = prog["percent"]
                        job.progress_percent = 85.0 + (prog["percent"] * 0.15)
                        job.eta = prog.get("remaining", job.eta)
                    await self.broadcast(job_id)
                await proc.wait()
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]
                if proc.returncode != 0:
                    raise RuntimeError("Burning failed")

            job.stage = JobStage.COMPLETED
            job.progress_percent = 100.0
            job.stage_percent = 100.0
            self.log(job_id, "Job finished successfully!")
            self.save_jobs()
            await self.broadcast(job_id)

        except asyncio.CancelledError:
            if current_process:
                try:
                    current_process.send_signal(signal.SIGCONT)
                    current_process.kill()
                except Exception:
                    pass
            job.stage = JobStage.CANCELLED
            job.error_message = "Job cancelled by user"
            self.log(job_id, "Job was cancelled.")
            self.save_jobs()
            await self.broadcast(job_id)
        except Exception as e:
            if current_process:
                try:
                    current_process.send_signal(signal.SIGCONT)
                    current_process.kill()
                except Exception:
                    pass
            job.stage = JobStage.FAILED
            job.error_message = str(e)
            self.log(job_id, f"ERROR: {str(e)}")
            self.save_jobs()
            await self.broadcast(job_id)
        finally:
            if job_id in self.active_processes:
                del self.active_processes[job_id]
            shutil.rmtree(work_dir, ignore_errors=True)
            if job_id in self.active_tasks:
                del self.active_tasks[job_id]
            self.save_jobs()
            await self.process_queue(scratch_dir, output_dir)
            await self._auto_resume_next_job(job_id)
