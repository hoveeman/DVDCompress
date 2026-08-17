import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from dvdcompress.job_manager import JobManager, JobStage
from dvdcompress.models import DiscType, OutputMode

@pytest.mark.asyncio
async def test_queue_orchestration_limits(tmp_path):
    jm = JobManager()
    jm.jobs.clear()
    jm.max_concurrent_jobs = 2
    
    # Mock _run_pipeline to wait on an event
    run_event = asyncio.Event()
    
    async def mock_pipeline(job_id, scratch_dir, output_dir):
        job = jm.get_job(job_id)
        job.stage = JobStage.TRANSCODING
        await run_event.wait()
        job.stage = JobStage.COMPLETED
    
    try:
        with patch.object(jm, "_run_pipeline", side_effect=mock_pipeline):
            id1 = jm.create_job(["/media/1.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB1")
            id2 = jm.create_job(["/media/2.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB2")
            id3 = jm.create_job(["/media/3.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB3")
            
            await jm.queue_job(id1, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
            await jm.queue_job(id2, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
            await jm.queue_job(id3, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
            await asyncio.sleep(0.01)
            
            # 2 should be active, 1 should be queued
            assert jm.jobs[id1].stage == JobStage.TRANSCODING
            assert jm.jobs[id2].stage == JobStage.TRANSCODING
            assert jm.jobs[id3].stage == JobStage.QUEUED
            
            # Increase slots to 3 -> id3 should automatically start
            await jm.set_max_concurrent_jobs(3, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
            await asyncio.sleep(0.01)
            assert jm.jobs[id3].stage == JobStage.TRANSCODING
            
            # Complete all
            run_event.set()
            await asyncio.sleep(0.05)
    finally:
        run_event.set()
        jm.jobs.clear()
        jm.active_tasks.clear()
        jm.max_concurrent_jobs = 5


