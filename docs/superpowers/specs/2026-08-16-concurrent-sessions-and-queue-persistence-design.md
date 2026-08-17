# Design Specification: Maximum Concurrent Sessions & AppData Queue Persistence

**Date:** 2026-08-16  
**Status:** Approved by User  
**Target:** DVDCompress  

---

## 1. Overview & Objective

DVDCompress allows users to compress, author, and burn video files to DVD and Blu-ray optical discs. Under high concurrency (e.g. 5+ simultaneous jobs running CPU-bound `spumux` subtitle authoring and FFmpeg transcode processes), system CPU and storage I/O become bottlenecked.

This specification introduces:
1. **Configurable Maximum Concurrent Sessions:** A user-controllable concurrency ceiling (default: 5, adjustable 1–20) where excess jobs wait in a `QUEUED` state and automatically start when slots become free.
2. **Persistent Queue & Settings Storage:** Saving application settings to `/config/settings.json` and active/queued job states to `/config/jobs.json` so that jobs and history survive container restarts and can resume automatically.
3. **Frontend UI Controls:** Interactive +/- slot controller in the Job History section with real-time updates and queue status visualization.

---

## 2. Architecture & Data Flow

### 2.1 Storage Schema

#### `/config/settings.json`
```json
{
  "max_concurrent_jobs": 5
}
```

#### `/config/jobs.json`
Array of serialized `Job` objects including all configuration parameters, progress metrics, current stage, and log buffer.

```json
[
  {
    "job_id": "4cdce017",
    "stage": "transcoding",
    "previous_stage": "probing",
    "is_paused": false,
    "input_files": ["/media/movie.mkv"],
    "disc_type": "dvd9",
    "output_mode": "iso_only",
    "output_name": "MARY_POPPINS",
    "progress_percent": 45.0,
    "stage_percent": 65.0,
    "fps": 48.2,
    "speed": "2.1x",
    "eta": "00:14:32",
    "logs": ["[INFO] Starting transcode..."]
  }
]
```

### 2.2 Concurrency & Queue Execution Lifecycle

1. **Job Creation:**
   * When a job is submitted (`/api/jobs`, `/api/preview`, `/api/burn-iso`), the job is created with `JobStage.QUEUED`.
   * The queue orchestrator `_process_queue()` checks the number of actively running jobs (`PROBING`, `TRANSCODING`, `AUTHORING`, `MASTERING_ISO`, `BURNING`).
   * If `active_count < max_concurrent_jobs`, the job is transitioned to `PROBING` and started asynchronously.
   * If `active_count >= max_concurrent_jobs`, the job remains in `QUEUED`.

2. **Job Completion / Failure / Cancellation:**
   * When an active job reaches `COMPLETED`, `FAILED`, or `CANCELLED`, `_process_queue()` is invoked.
   * In FIFO order, pending `QUEUED` jobs are picked up and started until all available slots are filled.

3. **Concurrency Limit Adjustments:**
   * When `max_concurrent_jobs` is changed via `POST /api/settings`:
     * The new value is saved to `/config/settings.json`.
     * `_process_queue()` is triggered. If the limit was increased, waiting jobs immediately start. If decreased, running jobs finish without starting new ones until active count drops below the new limit.

4. **Container Startup & Crash Recovery:**
   * On application startup:
     * Load `/config/settings.json` (or default to 5).
     * Load `/config/jobs.json` if present.
     * Preserved terminal states (`COMPLETED`, `FAILED`, `CANCELLED`) remain in history.
     * Interrupted in-flight jobs (`PROBING`, `TRANSCODING`, `AUTHORING`, `MASTERING_ISO`, `BURNING`) are reset to `QUEUED` (with logs noting that the container restarted and the job was re-queued).
     * `_process_queue()` is launched to pick up to `max_concurrent_jobs` in FIFO order.

---

## 3. API Specification

### `GET /api/settings`
* **Response (200 OK):**
```json
{
  "max_concurrent_jobs": 5
}
```

### `POST /api/settings`
* **Request Body:**
```json
{
  "max_concurrent_jobs": 6
}
```
* **Response (200 OK):**
```json
{
  "status": "updated",
  "settings": {
    "max_concurrent_jobs": 6
  }
}
```

### `POST /api/jobs`
* **Response (200 OK):**
```json
{
  "job_id": "abc12345",
  "status": "started" | "queued"
}
```

---

## 4. UI Specification

1. **Job History Header (`static/index.html` & `static/js/app.js`):**
   * Place a slot adjustment widget next to the "Refresh" button:
     ```html
     <div class="slots-control-group">
       <span class="slots-label">Concurrent Slots:</span>
       <div class="stepper-widget">
         <button id="btn-slots-decrement" class="btn btn-secondary btn-xs">-</button>
         <span id="slots-value" class="slots-display">5</span>
         <button id="btn-slots-increment" class="btn btn-secondary btn-xs">+</button>
       </div>
     </div>
     ```
   * Clicking `+` / `-` sends `POST /api/settings` and updates the UI immediately.

2. **Status Pills & Stepper:**
   * Support `QUEUED` status badge styling (amber/subtle-blue glow) in the jobs table and pipeline monitor.
   * Allow user to cancel or prioritize queued jobs.

---

## 5. Testing & Verification

1. **Unit Tests:**
   * Settings persistence and validation (loading, saving, clamping between 1 and 20).
   * Job queueing and FIFO slot pickup in `JobManager`.
   * Container restart recovery simulation (loading state from JSON, re-queueing unfinished jobs).
2. **API Tests:**
   * `GET /api/settings` and `POST /api/settings` endpoint tests.
   * `POST /api/jobs` queue behavior when submitting > `max_concurrent_jobs`.
3. **Integration & E2E Tests:**
   * Full pipeline test verifying concurrent slot limits and sequential pickup upon job completion.
