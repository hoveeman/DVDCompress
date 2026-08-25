# Job History Sorting, Metrics (Duration & Size), and Pagination Design Specification

## Overview

This specification details enhancements to the **Job History** table in DVDCompress:
1. **Chronological Sorting:** Displaying jobs sorted newest to oldest at the top of the table.
2. **Execution Duration Column:** Tracking and displaying the elapsed time taken to complete each job.
3. **Completed Size Column:** Tracking and displaying the final generated size (master ISO / preview file / burned ISO size).
4. **Pagination (10 Jobs Per Page):** Client-side pagination limiting the visible table rows to 10 jobs per page with intuitive page navigation controls and item counters.

---

## 1. Requirements & User Stories

1. **Newest to Oldest Ordering:** As a user, I want recently enqueued and completed jobs to appear at the very top of the history list so I can immediately see the status of recent tasks without scrolling to the bottom.
2. **Completion Time / Duration Metric:** As a user, I want to see how long each job took to execute (or current elapsed time if active) so I can gauge encoding performance and compare disc authoring speeds.
3. **Completed Output Size Metric:** As a user, I want to see the final file size of the generated master ISO or preview video so I can quickly verify disc budgeting and storage footprint.
4. **Clean 10-Item Pagination:** As a user with many past jobs, I want the history table split into pages of 10 items with previous/next and page number controls, keeping the dashboard compact and responsive.

---

## 2. Technical Architecture & Implementation

### 2.1 Backend Data Model Extensions (`Job` in `src/dvdcompress/job_manager.py`)

Extend the `Job` Pydantic model with timestamp and metric fields:
```python
class Job(BaseModel):
    # Existing fields...
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_sec: Optional[float] = None
    completed_size_bytes: Optional[int] = None
```

- **`created_at`**: Set automatically to `time.time()` when `JobManager.create_job(...)` is called.
- **`started_at`**: Set to `time.time()` when the async worker begins `_run_pipeline(...)` or `_run_burn_iso_pipeline(...)`.
- **`completed_at`**: Set to `time.time()` when the job reaches a terminal stage (`COMPLETED`, `FAILED`, `CANCELLED`).
- **`duration_sec`**: Calculated as `completed_at - started_at` (or stored if already computed).
- **`completed_size_bytes`**:
  - For standard authoring (`iso_path` or `PREVIEW_VIDEO` / `PREVIEW_ISO` output file): captured via `os.path.getsize(output_path)` upon completion.
  - For standalone burn jobs: captured via `os.path.getsize(iso_path)`.

All fields serialize to `jobs.json` so historical metrics persist across container restarts. For legacy records without `created_at`, fallback sorting uses reverse list order.

### 2.2 Frontend Sorting & Metrics Formatting (`src/dvdcompress/static/js/app.js`)

1. **Sorting Logic:**
   ```javascript
   const sortedJobs = [...jobs].sort((a, b) => {
     const tA = a.created_at || 0;
     const tB = b.created_at || 0;
     if (tA !== tB) return tB - tA; // Newest first
     return 0;
   });
   ```
2. **Duration Formatter:**
   ```javascript
   function formatDuration(job) {
     if (job.duration_sec != null && job.duration_sec >= 0) {
       return formatSeconds(job.duration_sec);
     }
     if (job.started_at && !['completed', 'failed', 'cancelled', 'idle', 'queued'].includes(job.stage)) {
       const elapsed = Math.max(0, (Date.now() / 1000) - job.started_at);
       return formatSeconds(elapsed);
     }
     return '—';
   }
   ```
   `formatSeconds` converts seconds into concise human-readable strings:
   - `< 60s`: e.g. `45s`
   - `< 1h`: e.g. `12m 34s`
   - `>= 1h`: e.g. `1h 24m 10s`

3. **Size Formatter:**
   Uses standard `formatBytes(job.completed_size_bytes)`:
   - e.g. `4.32 GB`, `7.85 GB`, `450.1 MB`.
   - Returns `—` if `completed_size_bytes` is null/empty or job didn't produce output.

### 2.3 Table Layout & HTML Updates (`src/dvdcompress/static/index.html`)

Update the table `<thead>`:
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
  <tbody id="jobs-table-body"></tbody>
</table>
```

Add pagination container directly beneath the table in `<div class="jobs-table-container">`:
```html
<div class="jobs-pagination" id="jobs-pagination-controls" style="display: none;">
  <span class="pagination-info" id="jobs-pagination-info">Showing 1–10 of 25 jobs</span>
  <div class="pagination-buttons" id="jobs-pagination-buttons">
    <!-- Rendered dynamically: Prev, 1, 2, 3..., Next -->
  </div>
</div>
```

### 2.4 Pagination Logic in JavaScript

- State variable: `state.jobHistoryPage = 1`, `ITEMS_PER_PAGE = 10`.
- Calculate `totalPages = Math.ceil(sortedJobs.length / ITEMS_PER_PAGE)`.
- Clamp `state.jobHistoryPage` between 1 and `totalPages`.
- Slice `sortedJobs.slice((page - 1) * 10, page * 10)` to render current page rows.
- Render pagination buttons:
  - `Prev` button (disabled on page 1).
  - Numbered pills for pages with active highlight on `state.jobHistoryPage`.
  - `Next` button (disabled on last page).
- Event listeners for page switching trigger `renderJobHistoryPage()` without full network re-fetch.
- Preserves current page index during automatic WebSocket updates or polling.

---

## 3. Testing & Verification Plan

1. **Unit & Pipeline Tests (`tests/test_job_manager.py`, `tests/test_api.py`):**
   - Verify `created_at`, `started_at`, `completed_at`, `duration_sec`, and `completed_size_bytes` are correctly populated and serialized.
   - Verify job listing returns jobs with these attributes.
2. **UI Tests (`tests/test_ui.py`):**
   - Verify table headers include Duration and Size.
   - Verify pagination controls element IDs and helper functions in `app.js`.
   - Verify JavaScript syntax validity.
3. **Full Automated Test Suite:**
   - Execute all pytest tests to ensure 100% pass rate.
