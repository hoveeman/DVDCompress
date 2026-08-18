# Job History Retry & Edit Design Specification

## Overview

This specification details the addition of **Retry** and **Edit** functionality to the Job History table in DVDCompress. This allows users to either re-run a previous (completed, failed, or cancelled) job with identical settings with one click, or load a previous job's complete configuration and playlist back into the Disc Authoring & Compression tab to make modifications and tweaks.

---

## 1. Requirements & User Stories

1. **One-Click Retry:** As a user whose job completed or failed, I want a "Retry" button on that job in the history table so I can immediately re-enqueue and monitor the job without reconfiguring all settings.
2. **Interactive Edit/Tweak:** As a user, I want an "Edit" button on any past job in the history table so that its files, format settings, aspect ratio, TV standard, and device configurations are pre-populated into the Disc Authoring tab, allowing me to tweak options and author a new project.
3. **Responsive Action Buttons:** The Job History table row actions should display appropriate controls based on job state (Active jobs show Pause/Resume and Cancel; Inactive jobs show Monitor, Edit, Retry, and Remove).

---

## 2. Architecture & Data Flow

### 2.1 Backend Endpoint (`POST /api/jobs/{job_id}/retry`)
- **Location:** `src/dvdcompress/api.py`
- **Method:** `POST`
- **Path:** `/api/jobs/{job_id}/retry`
- **Behavior:**
  1. Retrieves the existing job by `job_id` from `job_manager.jobs`.
  2. If the job does not exist, raises HTTP 404 (`Job not found`).
  3. Constructs a new `JobRequest` from the historical job's attributes:
     - `input_files`
     - `disc_type`
     - `output_mode`
     - `output_name`
     - `tv_standard`
     - `aspect_ratio`
     - `menu_mode`
     - `burner_device`
     - `burn_speed`
     - `use_gpu`
     - `passthrough`
     - `selected_subtitle_indices`
  4. Calls `job_manager.create_job(req)` to enqueue the new job.
  5. Returns HTTP 201 with the newly created `Job` object.

### 2.2 Frontend History Table
- **Location:** `src/dvdcompress/static/js/app.js` (`loadJobHistory()`)
- For finished/inactive jobs (`stage` in `['completed', 'failed', 'cancelled']`), the action cell renders:
  - `<button class="btn btn-secondary btn-sm btn-monitor-job">Monitor</button>`
  - `<button class="btn btn-secondary btn-sm btn-edit-job-row" style="margin-left: 4px;" title="Edit and tweak this job in authoring">Edit</button>`
  - `<button class="btn btn-primary btn-sm btn-retry-job-row" style="margin-left: 4px;" title="Re-run this job with identical parameters">Retry</button>`
  - `<button class="btn btn-danger btn-sm btn-delete-job-row" style="margin-left: 4px;" title="Remove this job from history">Remove</button>`

### 2.3 Frontend Edit Workflow (`editJobInAuthoring(job)`)
When "Edit" is clicked on a job:
1. Updates `state.config`:
   - `output_name` -> `#input-output-name`
   - `disc_type` -> calls `setDiscType(...)`
   - `tv_standard` -> updates `#control-tv-standard` segmented button
   - `aspect_ratio` -> updates `#control-aspect-ratio` segmented button
   - `menu_mode` -> updates `#control-menu-mode` segmented button
   - `output_mode` -> updates `#select-output-mode` and toggles `#burner-options-group`
   - `burner_device` -> updates `#select-burner-device`
   - `burn_speed` -> updates `#select-burn-speed`
   - `use_gpu` -> updates `#toggle-gpu` and `#gpu-toggle-desc`
   - `passthrough` -> updates `#toggle-passthrough`
2. Clears existing `state.playlist`.
3. Iterates over `job.input_files` and calls `probe_media_file` for each file, adding to `state.playlist`.
4. If `job.selected_subtitle_indices` is present, marks the selected subtitles on the corresponding playlist item(s).
5. Triggers `recalculateBudget()` and `renderPlaylist()`.
6. Calls `switchTab('view-authoring')` and smoothly scrolls to top.
7. Displays info toast: `"Loaded job '<output_name>' into project authoring"`.

### 2.4 Frontend Retry Workflow (`retryJob(jobId)`)
When "Retry" is clicked on a job:
1. Calls `POST /api/jobs/${jobId}/retry`.
2. On success:
   - Displays toast: `"Retrying job: <output_name>"`.
   - Connects WebSocket to new job ID (`connectJobWebSocket(newJob.job_id)`).
   - Smoothly scrolls to the top of the Active Pipeline tab.
   - Refreshes history (`loadJobHistory()`).
3. On error: displays error toast.

---

## 3. Testing & Validation Plan

1. **API Tests (`tests/test_api.py`):**
   - Test `POST /api/jobs/{job_id}/retry` returns 201 and creates a new job with identical parameters.
   - Test `POST /api/jobs/invalid_id/retry` returns 404.
2. **UI Tests (`tests/test_ui.py`):**
   - Test presence of `btn-retry-job-row` and `btn-edit-job-row` in `app.js`.
   - Test JavaScript syntax validation.
3. **Full Suite Regression:**
   - Execute all pytest tests to ensure 100% pass rate.
