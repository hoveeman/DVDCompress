import os
import pytest
from dvdcompress.job_manager import Job, JobManager, JobStage
from dvdcompress.models import DiscType, OutputMode

def test_save_and_load_jobs(tmp_path):
    jm = JobManager()
    jm.jobs.clear()
    
    # Create finished job and queued job
    job1_id = jm.create_job(
        input_files=["/media/test1.mp4"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="TEST_1"
    )
    jm.jobs[job1_id].stage = JobStage.COMPLETED
    jm.jobs[job1_id].progress_percent = 100.0
    
    job2_id = jm.create_job(
        input_files=["/media/test2.mp4"],
        disc_type=DiscType.DVD9,
        output_mode=OutputMode.ISO_ONLY,
        output_name="TEST_2"
    )
    # Simulate an interrupted transcoding job
    jm.jobs[job2_id].stage = JobStage.TRANSCODING
    
    jm.save_jobs(str(tmp_path))
    assert (tmp_path / "jobs.json").exists()
    
    # Simulate fresh container startup
    jm.jobs.clear()
    jm.load_jobs(str(tmp_path))
    
    assert job1_id in jm.jobs
    assert jm.jobs[job1_id].stage == JobStage.COMPLETED
    
    assert job2_id in jm.jobs
    # Interrupted job should be re-queued with a restart recovery log notice
    assert jm.jobs[job2_id].stage == JobStage.QUEUED
    jm.jobs.clear()

