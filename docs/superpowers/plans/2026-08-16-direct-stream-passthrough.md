# Direct Stream Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Direct Stream Passthrough / Remux mode to skip re-encoding for disc-compliant video streams when target disc capacity allows.

**Architecture:** Add `passthrough: bool = False` to `Job` and API request models, enhance `generate_tsmuxer_meta` to support HEVC and AVC streams, implement eligibility checks in `JobManager._run_pipeline`, and add a UI toggle switch.

**Tech Stack:** Python 3.10+, FastAPI, tsMuxeR, dvdauthor, Vanilla HTML5/ES6.

---

### Task 1: tsMuxeR HEVC/AVC Codec Support in `authoring.py`
**Files:**
- Modify: `src/dvdcompress/authoring.py`
- Test: `tests/test_authoring.py`

- [ ] **Step 1: Write failing test in `tests/test_authoring.py` for HEVC meta generation**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update `generate_tsmuxer_meta` to support `video_codecs` list (`hevc` vs `h264`)**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 1**

---

### Task 2: Models & API Passthrough Field
**Files:**
- Modify: `src/dvdcompress/models.py`
- Modify: `src/dvdcompress/api.py`
- Modify: `src/dvdcompress/job_manager.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing test in `tests/test_api.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update models, `api.py`, and `JobManager.create_job` with `passthrough: bool = False`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Passthrough Execution Logic in `JobManager`
**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Test: `tests/test_job_manager.py`

- [ ] **Step 1: Write failing test in `tests/test_job_manager.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement passthrough bypass in `JobManager._run_pipeline`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 3**

---

### Task 4: Web UI Passthrough Toggle & Payload
**Files:**
- Modify: `src/dvdcompress/static/index.html`
- Modify: `src/dvdcompress/static/js/app.js`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing test in `tests/test_ui.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Add `toggle-passthrough` to `index.html` and wire event listeners in `app.js`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 4**

---

### Task 5: End-to-End Tests & Final Verification
**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Add E2E tests for 4K UHD HEVC HDR passthrough to BD-66/100 and H.264 passthrough to BD-25**
- [ ] **Step 2: Run full test suite (`pytest tests/ -v`) and verify 100% pass**
- [ ] **Step 3: Commit Task 5 and push to main**
