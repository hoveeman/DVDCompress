"""Async job manager and orchestration pipeline for DVDCompress with pause/resume and sequential queuing."""

import asyncio
import os
import shutil
import signal
import uuid
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from dvdcompress.authoring import generate_dvdauthor_xml, generate_tsmuxer_meta
from dvdcompress.burner import build_burn_command, parse_burn_progress_line
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.iso import build_genisoimage_command, build_xorriso_bd_command
from dvdcompress.models import AspectRatio, DiscType, MenuMode, OutputMode, TVStandard
from dvdcompress.probe import probe_media_file
from dvdcompress.transcoder import (
    build_bluray_transcode_command,
    build_dvd_transcode_command,
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
    burner_device: Optional[str] = None
    burn_speed: int = 4
    use_gpu: bool = True

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
        return cls._instance

    def create_job(
        self,
        input_files: List[str],
        disc_type: DiscType,
        output_mode: OutputMode,
        output_name: str,
        tv_standard: TVStandard = TVStandard.AUTO,
        aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
        menu_mode: MenuMode = MenuMode.AUTOPLAY,
        burner_device: Optional[str] = None,
        burn_speed: int = 4,
        use_gpu: bool = True,
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
            burner_device=burner_device,
            burn_speed=burn_speed,
            use_gpu=use_gpu,
            total_files=len(input_files),
        )
        self.jobs[job_id] = job
        self.pause_events[job_id] = asyncio.Event()
        self.pause_events[job_id].set()
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

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

    def log(self, job_id: str, message: str):
        job = self.get_job(job_id)
        if job:
            job.logs.append(message)
            if len(job.logs) > 500:
                job.logs.pop(0)

    async def start_job(self, job_id: str, scratch_dir: str = "/tmp/dvdcompress", output_dir: str = "/output"):
        task = asyncio.create_task(self._run_pipeline(job_id, scratch_dir, output_dir))
        self.active_tasks[job_id] = task
        return task

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
        await self.broadcast(job_id)

    async def _auto_resume_next_job(self, exclude_job_id: Optional[str] = None):
        """Automatically pick up and resume the next paused job in FIFO order."""
        for other_id, other_job in self.jobs.items():
            if other_id != exclude_job_id and other_job.stage == JobStage.PAUSED and other_job.is_paused:
                self.log(other_id, f"Previous job finished. Auto-resuming job {other_id}...")
                await self.resume_job(other_id)
                break

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
            transcoded_files = []

            for idx, info in enumerate(media_infos):
                job.current_file_idx = idx + 1
                out_ext = ".m2ts" if is_bluray else ".mpg"
                out_file = os.path.join(work_dir, f"title_{idx+1}{out_ext}")
                transcoded_files.append(out_file)

                if is_bluray:
                    cmd = build_bluray_transcode_command(
                        input_file=info.path,
                        output_m2ts=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        use_gpu=job.use_gpu,
                    )
                else:
                    cmd = build_dvd_transcode_command(
                        input_file=info.path,
                        output_mpg=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        tv_standard=job.tv_standard,
                        aspect_ratio=job.aspect_ratio,
                        use_gpu=job.use_gpu,
                    )

                self.log(job_id, f"Transcoding [{idx+1}/{len(media_infos)}]: {info.filename}")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                current_process = proc
                self.active_processes[job_id] = proc

                buffer = ""
                while True:
                    # If paused, wait for resume
                    if job_id in self.pause_events:
                        await self.pause_events[job_id].wait()

                    chunk = await proc.stderr.read(512)
                    if not chunk:
                        break
                    buffer += chunk.decode(errors="replace")
                    lines = buffer.replace("\r", "\n").split("\n")
                    buffer = lines[-1]
                    for line in lines[:-1]:
                        prog = parse_ffmpeg_progress_line(line)
                        if "frame" in prog or "time_sec" in prog:
                            if "fps" in prog:
                                job.fps = prog["fps"]
                            if "speed" in prog:
                                job.speed = prog["speed"]
                            if info.duration_sec > 0 and "time_sec" in prog:
                                file_pct = min(100.0, (prog["time_sec"] / info.duration_sec) * 100.0)
                                job.stage_percent = round(file_pct, 1)
                                overall_pct = ((idx + (file_pct / 100.0)) / len(media_infos)) * 60.0
                                job.progress_percent = round(overall_pct, 1)

                                # Calculate live ETA
                                rem_sec = max(0.0, info.duration_sec - prog["time_sec"])
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
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]

                if proc.returncode != 0 and job.stage != JobStage.CANCELLED:
                    raise RuntimeError(f"Transcoding failed for {info.filename}")

            # Check pause before authoring
            if job_id in self.pause_events:
                await self.pause_events[job_id].wait()

            # 3. Authoring
            job.stage = JobStage.AUTHORING
            job.progress_percent = 70.0
            self.log(job_id, "Authoring disc structure...")
            await self.broadcast(job_id)

            author_dir = os.path.join(work_dir, "author")
            os.makedirs(author_dir, exist_ok=True)

            # Build chapter list for each title
            chapters_list = []
            for info in media_infos:
                if info.chapter_times and len(info.chapter_times) >= 2:
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
                meta_content = generate_tsmuxer_meta(transcoded_files, chapters_sec=first_chaps)
                meta_path = os.path.join(work_dir, "tsmuxer.meta")
                with open(meta_path, "w") as mf:
                    mf.write(meta_content)
                proc = await asyncio.create_subprocess_exec("tsMuxeR", meta_path, author_dir)
                current_process = proc
                self.active_processes[job_id] = proc
                await proc.wait()
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]
                if proc.returncode != 0:
                    raise RuntimeError("Authoring failed with tsMuxeR")
            else:
                xml_content = generate_dvdauthor_xml(
                    titles_mpg=transcoded_files,
                    chapters_sec=chapters_list,
                    menu_mode=job.menu_mode,
                    tv_standard=job.tv_standard,
                )
                xml_path = os.path.join(work_dir, "dvdauthor.xml")
                with open(xml_path, "w") as xf:
                    xf.write(xml_content)
                proc = await asyncio.create_subprocess_exec("dvdauthor", "-o", author_dir, "-x", xml_path)
                current_process = proc
                self.active_processes[job_id] = proc
                await proc.wait()
                current_process = None
                if job_id in self.active_processes:
                    del self.active_processes[job_id]
                if proc.returncode != 0:
                    raise RuntimeError("Authoring failed with dvdauthor")

            # Check pause before ISO creation
            if job_id in self.pause_events:
                await self.pause_events[job_id].wait()

            # 4. ISO Creation
            job.stage = JobStage.MASTERING_ISO
            job.progress_percent = 85.0
            iso_path = os.path.join(output_dir, f"{job.output_name}.iso")
            job.output_iso_path = iso_path
            self.log(job_id, f"Building ISO: {iso_path}")
            await self.broadcast(job_id)

            if is_bluray:
                iso_cmd = build_xorriso_bd_command(author_dir, iso_path, job.output_name)
            else:
                iso_cmd = build_genisoimage_command(author_dir, iso_path, job.output_name)

            proc = await asyncio.create_subprocess_exec(*iso_cmd)
            current_process = proc
            self.active_processes[job_id] = proc
            await proc.wait()
            current_process = None
            if job_id in self.active_processes:
                del self.active_processes[job_id]
            if proc.returncode != 0:
                raise RuntimeError("ISO creation failed")

            # 5. Burning (Optional)
            if job.output_mode in (OutputMode.BURN_DIRECT, OutputMode.AUTHOR_AND_BURN) and job.burner_device:
                # Check pause before burning
                if job_id in self.pause_events:
                    await self.pause_events[job_id].wait()

                job.stage = JobStage.BURNING
                self.log(job_id, f"Burning ISO to {job.burner_device} at {job.burn_speed}x...")
                await self.broadcast(job_id)
                burn_cmd = build_burn_command(job.burner_device, iso_path, speed=job.burn_speed, is_bluray=is_bluray)
                proc = await asyncio.create_subprocess_exec(
                    *burn_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                current_process = proc
                self.active_processes[job_id] = proc
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace").strip()
                    if decoded:
                        self.log(job_id, decoded)
                    prog = parse_burn_progress_line(decoded)
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
            await self.broadcast(job_id)

            # Auto-resume next paused job
            await self._auto_resume_next_job(job_id)

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
            await self.broadcast(job_id)
            await self._auto_resume_next_job(job_id)
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
            await self.broadcast(job_id)
            await self._auto_resume_next_job(job_id)
        finally:
            if job_id in self.active_processes:
                del self.active_processes[job_id]
            shutil.rmtree(work_dir, ignore_errors=True)
            if job_id in self.active_tasks:
                del self.active_tasks[job_id]
