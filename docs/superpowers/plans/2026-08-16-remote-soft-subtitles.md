# Remote-Selectable Soft Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automated extraction, conversion, and disc authoring of remote-selectable soft subtitle tracks for DVD-Video and Blu-ray discs.

**Architecture:** Probe subtitle streams and disposition flags with `ffprobe`, extract text (`.srt`) and PGS bitmap (`.sup`) streams via `ffmpeg` in `JobManager`, and author multi-language selectable tracks via `tsMuxeR` (Blu-ray) and `dvdauthor` (DVD), configured with a stream inspector track selector in the web UI.

**Tech Stack:** Python 3.10+, FastAPI, FFmpeg/ffprobe, dvdauthor, tsMuxeR, Vanilla HTML5/ES6.

## Global Constraints
- Target 100% standard compliance on physical DVD and Blu-ray players.
- Subtitle extraction must not fail or abort if an individual subtitle track packet stream is corrupted.
- Preserve 100% test passing across the test suite (`pytest tests/ -v`).

---

### Task 1: Subtitle Stream Metadata & Disposition in `models.py` and `probe.py`

**Files:**
- Modify: `src/dvdcompress/models.py:48-55`
- Modify: `src/dvdcompress/probe.py:88-98`
- Test: `tests/test_probe.py`

**Interfaces:**
- `SubtitleStreamInfo`: `index: int`, `codec_name: str`, `language: Optional[str] = "und"`, `title: Optional[str] = None`, `is_default: bool = False`, `is_forced: bool = False`

- [ ] **Step 1: Write failing test in `tests/test_probe.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update `models.py` and `probe.py` to extract disposition flags**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 1**

---

### Task 2: Subtitle Extraction Command Builder & Meta Authoring

**Files:**
- Modify: `src/dvdcompress/authoring.py`
- Test: `tests/test_authoring.py`

**Interfaces:**
- `build_subtitle_extraction_command(input_file: str, stream_index: int, output_sub_path: str, is_bitmap: bool = False) -> List[str]`
- `generate_tsmuxer_meta(video_files: List[str], chapters_sec: Optional[List[float]] = None, subtitle_files: Optional[List[Dict[str, str]]] = None) -> str`
- `generate_dvdauthor_xml(...)` with `<subpicture lang="..."/>` tags.

- [ ] **Step 1: Write failing test in `tests/test_authoring.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement subtitle command builder and meta updates in `authoring.py`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Pipeline Subtitle Extraction & Multiplexing in `JobManager`

**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- `JobManager._run_pipeline`: Extracts subtitle tracks into `work_dir` and passes them to `generate_tsmuxer_meta` / `generate_dvdauthor_xml`.

- [ ] **Step 1: Write failing test in `tests/test_job_manager.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement subtitle extraction step in `JobManager._run_pipeline`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 3**

---

### Task 4: Subtitle Selection API & Domain Models

**Files:**
- Modify: `src/dvdcompress/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `CreateJobRequest`: `selected_subtitle_indices: Optional[List[int]] = None`
- `CreatePreviewRequest`: `selected_subtitle_indices: Optional[List[int]] = None`

- [ ] **Step 1: Write failing test in `tests/test_api.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Update `api.py` with `selected_subtitle_indices`**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 4**

---

### Task 5: Web UI Subtitle Track Selector

**Files:**
- Modify: `src/dvdcompress/static/index.html`
- Modify: `src/dvdcompress/static/js/app.js`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing test in `tests/test_ui.py`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement subtitle track checkboxes in `app.js` stream inspector**
- [ ] **Step 4: Run pytest to verify pass**
- [ ] **Step 5: Commit Task 5**

---

### Task 6: Comprehensive End-to-End Integration Tests

**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Write end-to-end integration tests for DVD and Blu-ray subtitle authoring**
- [ ] **Step 2: Run full test suite (`pytest tests/ -v`) and verify 100% pass**
- [ ] **Step 3: Commit Task 6**
