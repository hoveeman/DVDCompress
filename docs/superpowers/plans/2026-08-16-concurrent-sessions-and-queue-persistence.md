# Maximum Concurrent Sessions & AppData Queue Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a configurable maximum concurrent sessions ceiling (default: 5, adjustable 1–20) with automatic FIFO queue execution, full AppData persistence (`/config/settings.json` and `/config/jobs.json`) across container restarts, and interactive slot stepper controls in the Job History web UI.

**Architecture:** A centralized `AppSettings` model and persistence engine loads/saves user configuration and job state into `/config`. `JobManager` acts as a concurrency orchestrator with a `_process_queue()` loop that starts queued jobs whenever running jobs drop below `max_concurrent_jobs`. The FastAPI backend exposes `/api/settings` and initializes state on startup, and the Single-Page frontend adds interactive slot controls in the Job History header.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, asyncio, Vanilla HTML5 / ES6 JavaScript / CSS3, pytest.

## Global Constraints
- Target persistent config path: `CONFIG_DIR` (`/config` by default, configurable via `DVDCOMPRESS_CONFIG_DIR`).
- Target scratch temp path: `TEMP_DIR` (`/tmp/dvdcompress`).
- Default `max_concurrent_jobs`: 5 (min: 1, max: 20).
- Running active stages: `PROBING`, `TRANSCODING`, `AUTHORING`, `MASTERING_ISO`, `BURNING`.
- Preserved stages across restarts: `COMPLETED`, `FAILED`, `CANCELLED` (terminal), `QUEUED` (pending). Interrupted running stages reset to `QUEUED`.
- All tests must pass with 100% success rate.

---

### Task 1: App Settings Model & Persistent Storage

**Files:**
- Modify: `src/dvdcompress/config.py`
- Modify: `src/dvdcompress/models.py`
- Create: `tests/test_settings.py`

**Interfaces:**
- Consumes: `config.py` settings paths
- Produces: `AppSettings(BaseModel)`, `load_app_settings(config_dir: Path) -> AppSettings`, `save_app_settings(settings: AppSettings, config_dir: Path) -> None`

- [ ] **Step 1: Write the failing test for settings model and persistence**

```python
# tests/test_settings.py
import json
import os
import pytest
from pathlib import Path
from dvdcompress.config import AppSettings, load_app_settings, save_app_settings

def test_app_settings_defaults(tmp_path):
    settings = load_app_settings(tmp_path)
    assert settings.max_concurrent_jobs == 5

def test_app_settings_save_and_load(tmp_path):
    settings = AppSettings(max_concurrent_jobs=8)
    save_app_settings(settings, tmp_path)
    
    loaded = load_app_settings(tmp_path)
    assert loaded.max_concurrent_jobs == 8
    
    settings_file = tmp_path / "settings.json"
    assert settings_file.exists()
    data = json.loads(settings_file.read_text())
    assert data["max_concurrent_jobs"] == 8

def test_app_settings_validation():
    with pytest.raises(Exception):
        AppSettings(max_concurrent_jobs=0)
    with pytest.raises(Exception):
        AppSettings(max_concurrent_jobs=25)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_settings.py -v`  
Expected: FAIL with ImportErrors

- [ ] **Step 3: Implement AppSettings and persistence in `config.py` and `models.py`**

In `src/dvdcompress/config.py`:
```python
import json
from pathlib import Path
from pydantic import BaseModel, Field

class AppSettings(BaseModel):
    max_concurrent_jobs: int = Field(default=5, ge=1, le=20)

def load_app_settings(config_dir: Path) -> AppSettings:
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.json"
    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return AppSettings(**data)
        except Exception:
            pass
    settings = AppSettings()
    save_app_settings(settings, config_dir)
    return settings

def save_app_settings(settings: AppSettings, config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    settings_file = config_dir / "settings.json"
    settings_file.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_settings.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/config.py tests/test_settings.py
git commit -m "feat(config): add AppSettings model and JSON persistence in config_dir"
```

---

### Task 2: Job Persistence & Restart Recovery in `JobManager`

**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Create: `tests/test_job_persistence.py`

**Interfaces:**
- Consumes: `Job`, `JobStage`, `config.settings`
- Produces: `JobManager.save_jobs(config_dir: str)`, `JobManager.load_jobs(config_dir: str)`

- [ ] **Step 1: Write the failing test for job persistence and recovery**

```python
# tests/test_job_persistence.py
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
    # Interrupted job should be re-queued
    assert jm.jobs[job2_id].stage == JobStage.QUEUED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_job_persistence.py -v`  
Expected: FAIL (methods not implemented)

- [ ] **Step 3: Implement `save_jobs` and `load_jobs` in `JobManager`**

Add JSON serialization and deserialization in `src/dvdcompress/job_manager.py`, ensuring atomicity and re-queueing of interrupted running jobs.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_job_persistence.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/job_manager.py tests/test_job_persistence.py
git commit -m "feat(jobs): add job state JSON persistence and crash recovery"
```

---

### Task 3: Queue Orchestration & Concurrency Limiter in `JobManager`

**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Create: `tests/test_queue_orchestration.py`

**Interfaces:**
- Consumes: `AppSettings.max_concurrent_jobs`
- Produces: `JobManager.max_concurrent_jobs`, `JobManager.set_max_concurrent_jobs(limit: int)`, `JobManager.process_queue()`, `JobManager.get_active_jobs_count()`

- [ ] **Step 1: Write failing tests for queue limits and auto-start**

```python
# tests/test_queue_orchestration.py
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
    
    with patch.object(jm, "_run_pipeline", side_effect=mock_pipeline):
        # Create 3 jobs
        id1 = jm.create_job(["/media/1.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB1")
        id2 = jm.create_job(["/media/2.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB2")
        id3 = jm.create_job(["/media/3.mp4"], DiscType.DVD5, OutputMode.ISO_ONLY, "JOB3")
        
        await jm.queue_job(id1, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
        await jm.queue_job(id2, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
        await jm.queue_job(id3, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
        
        # 2 should be active, 1 should be queued
        assert jm.jobs[id1].stage == JobStage.TRANSCODING
        assert jm.jobs[id2].stage == JobStage.TRANSCODING
        assert jm.jobs[id3].stage == JobStage.QUEUED
        
        # Increase slots to 3 -> id3 should automatically start
        await jm.set_max_concurrent_jobs(3, scratch_dir=str(tmp_path), output_dir=str(tmp_path))
        assert jm.jobs[id3].stage == JobStage.TRANSCODING
        
        run_event.set()
        await asyncio.sleep(0.05)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_queue_orchestration.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement concurrency orchestration in `JobManager`**

Update `JobManager`:
- Add `max_concurrent_jobs: int = 5`
- Add `active_stages = {JobStage.PROBING, JobStage.TRANSCODING, JobStage.AUTHORING, JobStage.MASTERING_ISO, JobStage.BURNING}`
- Add `async def process_queue(scratch_dir: str, output_dir: str)`:
  - Iterates over `self.jobs.values()` in insertion order.
  - If active count < `max_concurrent_jobs` and job is in `JobStage.QUEUED`, starts `_run_pipeline` task.
- Call `process_queue()` after job completes, cancels, fails, or when `set_max_concurrent_jobs` is updated.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_queue_orchestration.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/job_manager.py tests/test_queue_orchestration.py
git commit -m "feat(jobs): implement queue scheduler and max concurrent job slots"
```

---

### Task 4: REST API Settings & Queue Integration

**Files:**
- Modify: `src/dvdcompress/api.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `AppSettings`, `JobManager`
- Produces: `GET /api/settings`, `POST /api/settings`, updated `POST /api/jobs`

- [ ] **Step 1: Write failing tests in `tests/test_api.py`**

```python
def test_get_settings(client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "max_concurrent_jobs" in data
    assert data["max_concurrent_jobs"] >= 1

def test_update_settings(client):
    res = client.post("/api/settings", json={"max_concurrent_jobs": 7})
    assert res.status_code == 200
    assert res.json()["settings"]["max_concurrent_jobs"] == 7
    
    # Check get returns 7
    res2 = client.get("/api/settings")
    assert res2.json()["max_concurrent_jobs"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_api.py -k "settings" -v`  
Expected: FAIL 404 Not Found

- [ ] **Step 3: Implement endpoints in `src/dvdcompress/api.py`**

- Add lifespan/startup routine to load settings & persisted jobs.
- Add `GET /api/settings` and `POST /api/settings`.
- Update `POST /api/jobs`, `POST /api/preview`, `POST /api/burn-iso` to queue jobs and return queue status.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/api.py tests/test_api.py
git commit -m "feat(api): add /api/settings endpoints and job queueing lifecycle"
```

---

### Task 5: Web UI Interactive Slot Stepper & Queue Badges

**Files:**
- Modify: `src/dvdcompress/static/index.html`
- Modify: `src/dvdcompress/static/css/style.css`
- Modify: `src/dvdcompress/static/js/app.js`
- Modify: `tests/test_ui.py`

**Interfaces:**
- Consumes: `/api/settings`
- Produces: UI Slot controller `[-] 5 [+]`, live updates, `QUEUED` status pills

- [ ] **Step 1: Write UI layout tests in `tests/test_ui.py`**

```python
def test_ui_contains_slots_control(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "slots-control" in html or "btn-slots-decrement" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_ui.py -k "slots" -v`  
Expected: FAIL

- [ ] **Step 3: Update `index.html`, `style.css`, and `app.js`**

In `static/index.html`:
Add the slot stepper control into the Job History header.

In `static/css/style.css`:
Add styles for `.slots-control-group`, `.stepper-widget`, `.slots-display`, and `.status-pill.queued`.

In `static/js/app.js`:
- Fetch `/api/settings` on startup and display current `max_concurrent_jobs`.
- Add event listeners for `#btn-slots-decrement` and `#btn-slots-increment` to POST to `/api/settings`.
- Display `QUEUED` status badge in table with clean styling.

- [ ] **Step 4: Run UI tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_ui.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/static/index.html src/dvdcompress/static/css/style.css src/dvdcompress/static/js/app.js tests/test_ui.py
git commit -m "feat(ui): add concurrent slots stepper control and queued status badge"
```

---

### Task 6: Full Integration Test & Verification

**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Add end-to-end queue and persistence verification tests**
- [ ] **Step 2: Run complete test suite**

Run: `./.venv/bin/pytest tests/ -v`  
Expected: All 120+ tests passing 100%.

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add e2e verification for queue persistence and concurrency limits"
```
