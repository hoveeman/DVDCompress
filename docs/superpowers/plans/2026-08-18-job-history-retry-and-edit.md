# Job History Retry & Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Retry" button and an "Edit" button to the Job History table in DVDCompress so users can re-run previous jobs with one click or restore them into Disc Authoring to tweak settings.

**Architecture:** A new REST endpoint `POST /api/jobs/{job_id}/retry` duplicates and re-enqueues historical jobs in `JobManager`. In the frontend SPA (`app.js`), finished job rows render "Edit" and "Retry" buttons, wiring up instantaneous re-queueing and complete state/playlist restoration into the authoring wizard.

**Tech Stack:** Python 3.10+ / FastAPI / Vanilla ES6 JavaScript / HTML5 / CSS3 / pytest

## Global Constraints

- No external JS frameworks or CDN dependencies; strictly Vanilla JS/CSS.
- Preserve all existing tests and ensure 100% pytest pass rate.
- Follow dark mode design system tokens.

---

### Task 1: Backend `POST /api/jobs/{job_id}/retry` Endpoint

**Files:**
- Modify: `src/dvdcompress/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `POST /api/jobs/{job_id}/retry -> Job` (HTTP 201 on success, HTTP 404 if not found)

- [ ] **Step 1: Write failing tests for job retry endpoint in `tests/test_api.py`**

```python
def test_retry_job_success_and_not_found(client, sample_mp4):
    # 1. Create a job first
    payload = {
        "input_files": [sample_mp4],
        "disc_type": "dvd9",
        "output_mode": "iso_only",
        "output_name": "original_job",
        "tv_standard": "ntsc",
        "aspect_ratio": "16:9",
        "menu_mode": "autoplay",
        "use_gpu": False,
        "passthrough": False,
    }
    res = client.post("/api/jobs", json=payload)
    assert res.status_code == 201
    job_id = res.json()["job_id"]

    # 2. Retry the job
    retry_res = client.post(f"/api/jobs/{job_id}/retry")
    assert retry_res.status_code == 201
    new_job = retry_res.json()
    assert new_job["job_id"] != job_id
    assert new_job["output_name"] == "original_job"
    assert new_job["disc_type"] == "dvd9"
    assert new_job["input_files"] == [sample_mp4]

    # 3. Retry non-existent job
    bad_res = client.post("/api/jobs/nonexistent-id/retry")
    assert bad_res.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_api.py::test_retry_job_success_and_not_found -v`
Expected: FAIL with HTTP 404/405 (Method Not Allowed / Not Found)

- [ ] **Step 3: Implement `POST /api/jobs/{job_id}/retry` in `src/dvdcompress/api.py`**

```python
@app.post("/api/jobs/{job_id}/retry", response_model=Job, status_code=201)
async def retry_job(job_id: str):
    """Re-enqueue an existing historical job with identical parameters."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    req = JobRequest(
        input_files=job.input_files,
        disc_type=job.disc_type,
        output_mode=job.output_mode,
        output_name=job.output_name,
        tv_standard=job.tv_standard,
        aspect_ratio=job.aspect_ratio,
        menu_mode=job.menu_mode,
        burner_device=job.burner_device,
        burn_speed=job.burn_speed,
        use_gpu=job.use_gpu,
        passthrough=job.passthrough,
        selected_subtitle_indices=job.selected_subtitle_indices,
    )
    new_job = await job_manager.create_job(req)
    return new_job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_api.py::test_retry_job_success_and_not_found -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/api.py tests/test_api.py
git commit -m "feat(api): add POST /api/jobs/{job_id}/retry endpoint"
```

---

### Task 2: Frontend History Table Edit & Retry Buttons and Workflows

**Files:**
- Modify: `src/dvdcompress/static/js/app.js`
- Test: `tests/test_ui.py`

**Interfaces:**
- Produces: `editJobInAuthoring(job)` and `retryJob(jobId)` wired up in `loadJobHistory()`

- [ ] **Step 1: Write UI tests in `tests/test_ui.py`**

```python
def test_job_history_retry_and_edit_ui_elements(client):
    res = client.get("/static/js/app.js")
    assert res.status_code == 200
    content = res.text
    assert "btn-retry-job-row" in content
    assert "btn-edit-job-row" in content
    assert "editJobInAuthoring" in content or "retryJob" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_ui.py::test_job_history_retry_and_edit_ui_elements -v`
Expected: FAIL

- [ ] **Step 3: Implement `editJobInAuthoring` and `retryJob` in `src/dvdcompress/static/js/app.js`**

1. In `loadJobHistory()`, render:
   - `<button class="btn btn-secondary btn-sm btn-edit-job-row" style="margin-left: 4px;" title="Edit and tweak this job in authoring">Edit</button>`
   - `<button class="btn btn-primary btn-sm btn-retry-job-row" style="margin-left: 4px;" title="Re-run this job with identical parameters">Retry</button>`
2. Attach event listeners:
   - `.btn-edit-job-row`: calls `editJobInAuthoring(j)`
   - `.btn-retry-job-row`: calls `retryJob(j.job_id, j.output_name)`
3. Implement `editJobInAuthoring(job)` to:
   - Restore `state.config` (output name, disc type, tv standard, aspect ratio, menu mode, output mode, GPU, passthrough, burner device/speed).
   - Clear and rebuild `state.playlist` from `job.input_files`, re-probing files and reapplying `selected_subtitle_indices`.
   - Update UI inputs/selects and segmented buttons.
   - Call `recalculateBudget()` and `renderPlaylist()`.
   - Switch tab to `view-authoring` and smoothly scroll to top.
   - Show toast notification.
4. Implement `retryJob(jobId, outputName)` to:
   - POST `/api/jobs/${jobId}/retry`.
   - Connect WebSocket to new job ID.
   - Switch to active pipeline view, scroll to top, and show toast.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_ui.py::test_job_history_retry_and_edit_ui_elements -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/static/js/app.js tests/test_ui.py
git commit -m "feat(ui): add retry and edit buttons to job history table"
```

---

### Task 3: Version Bump, Full Regression Test, and Push to Main

**Files:**
- Modify: `pyproject.toml`, `src/dvdcompress/__init__.py`, `src/dvdcompress/api.py`, `src/dvdcompress/static/index.html`, `GEMINI.md`

- [ ] **Step 1: Bump version to 1.0.3**
- [ ] **Step 2: Run complete pytest suite**
Run: `./.venv/bin/pytest -v`
Expected: 100% pass across all tests
- [ ] **Step 3: Commit and push to origin main**
Run: `git push origin main`
Expected: Successful push triggering GitHub Actions workflow
