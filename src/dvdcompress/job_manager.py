"""Async job manager and orchestration pipeline for DVDCompress."""

import asyncio
import os
import shutil
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
    PROBING = "probing"
    TRANSCODING = "transcoding"
    AUTHORING = "authoring"
    MASTERING_ISO = "mastering_iso"
    BURNING = "burning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    job_id: str
    stage: JobStage = JobStage.IDLE
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
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.listeners: Dict[str, List[asyncio.Queue]] = {}

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

    async def cancel_job(self, job_id: str):
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
            job = self.get_job(job_id)
            if job:
                job.stage = JobStage.CANCELLED
                job.error_message = "Job cancelled by user"
                await self.broadcast(job_id)

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

            is_bluray = job.disc_type in (DiscType.BD25, DiscType.BD50)
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

                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace")
                    prog = parse_ffmpeg_progress_line(decoded)
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
                        await self.broadcast(job_id)

                await proc.wait()
                current_process = None
                if proc.returncode != 0:
                    raise RuntimeError(f"Transcoding failed for {info.filename}")

            # 3. Authoring
            job.stage = JobStage.AUTHORING
            job.progress_percent = 70.0
            self.log(job_id, "Authoring disc structure...")
            await self.broadcast(job_id)

            author_dir = os.path.join(work_dir, "author")
            os.makedirs(author_dir, exist_ok=True)

            if is_bluray:
                meta_content = generate_tsmuxer_meta(transcoded_files)
                meta_path = os.path.join(work_dir, "tsmuxer.meta")
                with open(meta_path, "w") as mf:
                    mf.write(meta_content)
                proc = await asyncio.create_subprocess_exec("tsMuxeR", meta_path, author_dir)
                current_process = proc
                await proc.wait()
                current_process = None
                if proc.returncode != 0:
                    raise RuntimeError("Authoring failed with tsMuxeR")
            else:
                xml_content = generate_dvdauthor_xml(
                    titles_mpg=transcoded_files,
                    chapters_sec=[[0.0, 300.0, 600.0, 900.0] for _ in transcoded_files],
                    menu_mode=job.menu_mode,
                    tv_standard=job.tv_standard,
                )
                xml_path = os.path.join(work_dir, "dvdauthor.xml")
                with open(xml_path, "w") as xf:
                    xf.write(xml_content)
                proc = await asyncio.create_subprocess_exec("dvdauthor", "-o", author_dir, "-x", xml_path)
                current_process = proc
                await proc.wait()
                current_process = None
                if proc.returncode != 0:
                    raise RuntimeError("Authoring failed with dvdauthor")

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
            await proc.wait()
            current_process = None
            if proc.returncode != 0:
                raise RuntimeError("ISO creation failed")

            # 5. Burning (Optional)
            if job.output_mode in (OutputMode.BURN_DIRECT, OutputMode.AUTHOR_AND_BURN) and job.burner_device:
                job.stage = JobStage.BURNING
                self.log(job_id, f"Burning ISO to {job.burner_device} at {job.burn_speed}x...")
                await self.broadcast(job_id)
                burn_cmd = build_burn_command(job.burner_device, iso_path, speed=job.burn_speed, is_bluray=is_bluray)
                proc = await asyncio.create_subprocess_exec(
                    *burn_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                current_process = proc
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace")
                    prog = parse_burn_progress_line(decoded)
                    if "percent" in prog:
                        job.stage_percent = prog["percent"]
                        job.progress_percent = 85.0 + (prog["percent"] * 0.15)
                        job.eta = prog.get("remaining", job.eta)
                        await self.broadcast(job_id)
                await proc.wait()
                current_process = None
                if proc.returncode != 0:
                    raise RuntimeError("Burning failed")

            job.stage = JobStage.COMPLETED
            job.progress_percent = 100.0
            self.log(job_id, "Job finished successfully!")
            await self.broadcast(job_id)

        except asyncio.CancelledError:
            if current_process:
                try:
                    current_process.kill()
                except Exception:
                    pass
            job.stage = JobStage.CANCELLED
            job.error_message = "Job cancelled by user"
            self.log(job_id, "Job was cancelled.")
            await self.broadcast(job_id)
        except Exception as e:
            if current_process:
                try:
                    current_process.kill()
                except Exception:
                    pass
            job.stage = JobStage.FAILED
            job.error_message = str(e)
            self.log(job_id, f"ERROR: {str(e)}")
            await self.broadcast(job_id)
        finally:
            # Clean scratch work dir
            shutil.rmtree(work_dir, ignore_errors=True)
            if job_id in self.active_tasks:
                del self.active_tasks[job_id]
