# Job History Sorting, Metrics (Duration & Size), and Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the Job History table in DVDCompress to sort newest to oldest, display completion duration and final completed size columns, and paginate the list at 10 items per page with page controls.

**Architecture:** Extend the `Job` model and execution pipelines in `job_manager.py` to record `created_at`, `started_at`, `completed_at`, `duration_sec`, and `completed_size_bytes`. Update `index.html`, `style.css`, and `app.js` to render Duration and Size columns, enforce descending sort by `created_at`, and implement a 10-item client-side pagination controller.

**Tech Stack:** Python 3.10+ / FastAPI / Pydantic v2 / Vanilla HTML5 & ES6 JavaScript & CSS3 / Pytest

## Global Constraints
- Sort order MUST display newest jobs at the top of the table.
- Duration column MUST format seconds concisely (`Xs`, `Xm Ys`, `Xh Ym Zs`) and display live elapsed time for running jobs or `—` for queued/idle jobs.
- Size column MUST format bytes (`X.XX GB`, `XXX MB`) or display `—` if not applicable.
- Pagination MUST limit table display to 10 items per page and include item counters and page navigation buttons.
- All existing tests in `tests/` must continue to pass 100%.

---

### Task 1: Backend Data Model & Job Timing / Size Metrics

**Files:**
- Modify: `src/dvdcompress/job_manager.py:77-106`, `src/dvdcompress/job_manager.py:695-705`, `src/dvdcompress/job_manager.py:1162-1171`, `src/dvdcompress/job_manager.py:1243-1280`, `src/dvdcompress/api.py:168-278`, `src/dvdcompress/api.py:520-525`
- Test: `tests/test_job_manager.py`, `tests/test_api.py`

**Interfaces:**
- `Job`:
  - `created_at: float = Field(default_factory=time.time)`
  - `started_at: Optional[float] = None`
  - `completed_at: Optional[float] = None`
  - `duration_sec: Optional[float] = None`
  - `completed_size_bytes: Optional[int] = None`

- [ ] **Step 1: Write failing unit test for job metrics and timestamps**

Add test to `tests/test_job_manager.py`:
```python
def test_job_timestamps_and_metrics():
    from dvdcompress.job_manager import JobManager, JobStage
    from dvdcompress.models import DiscType, OutputMode
    import time
    
    jm = JobManager()
    job_id = jm.create_job(
        input_files=["/media/test.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="metrics_test",
    )
    job = jm.get_job(job_id)
    assert job is not None
    assert job.created_at > 0
    assert abs(job.created_at - time.time()) < 5
    assert job.started_at is None
    assert job.completed_at is None
    assert job.duration_sec is None
    assert job.completed_size_bytes is None
```

- [ ] **Step 2: Run test to verify it fails if fields do not exist**

Run: `.venv/bin/pytest tests/test_job_manager.py::test_job_timestamps_and_metrics -v`

- [ ] **Step 3: Update `Job` model and execution pipelines in `job_manager.py` and `api.py`**

In `src/dvdcompress/job_manager.py`:
- Add fields to `Job` model:
  ```python
  created_at: float = Field(default_factory=time.time)
  started_at: Optional[float] = None
  completed_at: Optional[float] = None
  duration_sec: Optional[float] = None
  completed_size_bytes: Optional[int] = None
  ```
- In `_run_pipeline`:
  - At start: `if not job.started_at: job.started_at = time.time()`
  - At completion (`PREVIEW_VIDEO`):
    ```python
    job.completed_at = time.time()
    if job.started_at:
        job.duration_sec = max(0.0, job.completed_at - job.started_at)
    if job.output_iso_path and os.path.exists(job.output_iso_path):
        job.completed_size_bytes = os.path.getsize(job.output_iso_path)
    ```
  - At completion (`PREVIEW_ISO` / standard ISO completion):
    ```python
    job.completed_at = time.time()
    if job.started_at:
        job.duration_sec = max(0.0, job.completed_at - job.started_at)
    if os.path.exists(iso_path):
        job.completed_size_bytes = os.path.getsize(iso_path)
    ```
  - In exception/cancellation handlers:
    ```python
    job.completed_at = time.time()
    if job.started_at:
        job.duration_sec = max(0.0, job.completed_at - job.started_at)
    ```
- In `api.py` (`_run_burn_iso_pipeline`):
  - Track `job.started_at`, `job.completed_at`, `job.duration_sec`, and `job.completed_size_bytes = os.path.getsize(iso_path)` if exists.
- In `api.py` (`list_jobs`):
  - Return jobs sorted by `created_at` descending (`sorted(job_manager.jobs.values(), key=lambda j: getattr(j, 'created_at', 0.0), reverse=True)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_job_manager.py tests/test_api.py -v`

---

### Task 2: Frontend Table Headers, CSS Styling, and Pagination Controls

**Files:**
- Modify: `src/dvdcompress/static/index.html:580-605`
- Modify: `src/dvdcompress/static/css/style.css:1430-1480`
- Modify: `src/dvdcompress/static/js/app.js:1690-1785`
- Test: `tests/test_ui.py`

**Interfaces:**
- HTML elements:
  - Table headers: `Job ID`, `Project Name`, `Format`, `Mode`, `Status`, `Progress`, `Duration`, `Size`, `Action`
  - Container `#jobs-pagination-controls` with `#jobs-pagination-info` and `#jobs-pagination-buttons`
- JS Functions in `app.js`:
  - `formatDuration(job)`
  - `formatBytes(bytes)`
  - `renderJobHistoryPage(jobs)`
  - Sorting: newest first by `created_at` descending
  - Pagination size: 10 items per page

- [ ] **Step 1: Write UI tests for table headers and pagination elements**

In `tests/test_ui.py`:
```python
def test_job_history_table_headers_and_pagination():
    from fastapi.testclient import TestClient
    from dvdcompress.api import app
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "<th>Duration</th>" in html
    assert "<th>Size</th>" in html
    assert 'id="jobs-pagination-controls"' in html
    assert 'id="jobs-pagination-info"' in html
    assert 'id="jobs-pagination-buttons"' in html
```

- [ ] **Step 2: Update HTML in `src/dvdcompress/static/index.html`**

Update the table header and add pagination controls:
```html
<table class="jobs-table" id="jobs-history-table">
  <thead>
    <tr>
      <th>Job ID</th>
      <th>Project Name</th>
      <th>Format</th>
      <th>Mode</th>
      <th>Status</th>
      <th>Progress</th>
      <th>Duration</th>
      <th>Size</th>
      <th style="text-align: right;">Action</th>
    </tr>
  </thead>
  <tbody id="jobs-table-body">
    <!-- Populated dynamically -->
  </tbody>
</table>

<div class="jobs-pagination" id="jobs-pagination-controls" style="display: none;">
  <span class="pagination-info" id="jobs-pagination-info">Showing 1–10 of 0 jobs</span>
  <div class="pagination-buttons" id="jobs-pagination-buttons"></div>
</div>
```

- [ ] **Step 3: Add CSS styling for pagination in `src/dvdcompress/static/css/style.css`**

Add responsive styling matching dark theme:
```css
.jobs-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  border-top: 1px solid var(--border-color);
  background: var(--bg-surface);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.pagination-buttons {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.pagination-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 0.3rem 0.65rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  font-family: var(--font-sans);
  transition: all 0.15s ease;
}

.pagination-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.pagination-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  font-weight: 600;
}

.pagination-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

- [ ] **Step 4: Update JavaScript logic in `src/dvdcompress/static/js/app.js`**

Implement:
1. `formatDuration(job)`: formats seconds to `Xs`, `Xm Ys`, `Xh Ym Zs` or live elapsed time.
2. Descending sort by `j.created_at || 0`.
3. Pagination state: `state.jobHistoryPage = state.jobHistoryPage || 1`, `ITEMS_PER_PAGE = 10`.
4. Render 10 items per page with updated cells (`Duration` and `Size`).
5. Render page controls (`Prev`, page pills, `Next`) and counter info (`Showing 1–10 of 25 jobs`).
6. Clamp `state.jobHistoryPage` if item count changes.

- [ ] **Step 5: Run UI tests and verify syntax**

Run: `.venv/bin/pytest tests/test_ui.py -v`

---

### Task 3: Full End-to-End Regression & Verification

**Files:**
- Test: `tests/`

- [ ] **Step 1: Run complete test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: 100% tests passing.
