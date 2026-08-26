# Audio Track Selection & Smart Default Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to select one or multiple audio tracks per title in the UI with smart settings-based defaults, integrating seamlessly across transcoding, optical disc authoring, and bitrate budgeting.

**Architecture:** Extend `AppSettings` with audio preferences (`preferred_audio_language`, `prefer_surround_audio`); update `Job` models and REST endpoints with `selected_audio_indices`; upgrade Transcoder and Authoring engines to support multi-audio mapping and elementary stream extraction; enhance Web UI playlist inspector with interactive checkboxes and settings controls.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, FFmpeg, dvdauthor, tsMuxeR, Vanilla ES6 JavaScript, HTML5/CSS3, pytest.

---

## Global Constraints

- Preserve 100% test suite pass rate (198+ tests).
- Follow existing codebase style, type annotations, and Pydantic v2 patterns.
- Ensure backwards compatibility for existing jobs (defaulting to primary audio stream if `selected_audio_indices` is omitted).
- Strictly obey optical disc specifications (maximum 8 audio streams for DVD-Video, maximum 32 for Blu-ray).

---

### Task 1: Configuration, Data Models & API

**Files:**
- Modify: `src/dvdcompress/config.py`
- Modify: `src/dvdcompress/models.py`
- Modify: `src/dvdcompress/api.py`
- Test: `tests/test_settings.py`, `tests/test_api.py`

**Interfaces:**
- `AppSettings`: add `preferred_audio_language: str = "eng"`, `prefer_surround_audio: bool = True`
- `JobCreateRequest` / `Job`: add `selected_audio_indices: Optional[List[int]] = None`
- `/api/settings` GET/POST: persists and returns new audio settings

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings.py` and `tests/test_api.py`:
```python
def test_audio_settings_persistence(tmp_path):
    from dvdcompress.config import AppSettings, load_app_settings, save_app_settings
    cfg = AppSettings(
        max_concurrent_jobs=4,
        preferred_audio_language="jpn",
        prefer_surround_audio=False,
    )
    save_app_settings(cfg, tmp_path)
    loaded = load_app_settings(tmp_path)
    assert loaded.preferred_audio_language == "jpn"
    assert loaded.prefer_surround_audio is False

def test_api_create_job_with_selected_audio(test_client):
    payload = {
        "input_files": ["/media/movie.mkv"],
        "disc_type": "dvd5",
        "output_mode": "iso_only",
        "output_name": "MULTI_AUDIO_TEST",
        "selected_audio_indices": [1, 2],
        "selected_subtitle_indices": [3],
    }
    res = test_client.post("/api/jobs", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["job"]["selected_audio_indices"] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_settings.py tests/test_api.py -k "test_audio_settings_persistence or test_api_create_job_with_selected_audio" -v`  
Expected: FAIL (missing fields in `AppSettings` or `JobCreateRequest`)

- [ ] **Step 3: Implement data models, config, and API changes**

1. In `src/dvdcompress/config.py`:
```python
class AppSettings(BaseModel):
    max_concurrent_jobs: int = Field(default=5, ge=1, le=20)
    preferred_audio_language: str = Field(default="eng")
    prefer_surround_audio: bool = Field(default=True)
```
2. In `src/dvdcompress/models.py`:
Add `selected_audio_indices: Optional[List[int]] = None` to `ProjectConfig`.
3. In `src/dvdcompress/job_manager.py`:
Add `selected_audio_indices: Optional[List[int]] = None` to `Job` model and `create_job` method.
4. In `src/dvdcompress/api.py`:
Add `selected_audio_indices: Optional[List[int]] = None` to `JobCreateRequest` and `BurnOnlyRequest`, and pass `selected_audio_indices` to `job_manager.create_job()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_settings.py tests/test_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/config.py src/dvdcompress/models.py src/dvdcompress/job_manager.py src/dvdcompress/api.py tests/test_settings.py tests/test_api.py
git commit -m "feat: add audio settings and selected_audio_indices to domain models and API"
```

---

### Task 2: Bitrate Budgeting for Multi-Audio Streams

**Files:**
- Modify: `src/dvdcompress/calculator.py`
- Test: `tests/test_calculator.py`

**Interfaces:**
- `calculate_bitrate_budget(total_duration_sec: float, disc_type: DiscType, audio_tracks_kbps: Optional[List[int]] = None, video_count: int = 1) -> BitrateBudget`

- [ ] **Step 1: Write the failing test**

In `tests/test_calculator.py`:
```python
def test_multi_audio_tracks_bitrate_budget():
    # 2 hour movie with dual audio: 5.1 (384 kbps) + Stereo Commentary (192 kbps) = 576 kbps total audio
    budget = calculate_bitrate_budget(
        total_duration_sec=7200,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[384, 192],
        video_count=1,
    )
    assert budget.audio_bitrate_kbps == 576
    assert budget.fits_disc is True
    # Verify video bitrate adjusts down to accommodate 576 kbps audio + mux overhead
    single_audio_budget = calculate_bitrate_budget(
        total_duration_sec=7200,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1,
    )
    assert budget.video_bitrate_kbps < single_audio_budget.video_bitrate_kbps
```

- [ ] **Step 2: Run test to verify it passes/fails**

Run: `./.venv/bin/pytest tests/test_calculator.py -k "test_multi_audio_tracks_bitrate_budget" -v`  
Expected: PASS (or verification of accurate multi-track budgeting calculation)

- [ ] **Step 3: Verify and refine budget calculations**

Ensure `calculate_bitrate_budget` accurately handles arbitrary audio stream lists, including empty/None fallbacks, and properly calculates `audio_bitrate_kbps = sum(audio_tracks_kbps)`.

- [ ] **Step 4: Run tests**

Run: `./.venv/bin/pytest tests/test_calculator.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/calculator.py tests/test_calculator.py
git commit -m "feat: enhance bitrate budget calculator for multi-audio tracks"
```

---

### Task 3: Transcoding Command Builder for Multi-Audio Streams

**Files:**
- Modify: `src/dvdcompress/transcoder.py`
- Test: `tests/test_transcoder.py`

**Interfaces:**
- `build_dvd_transcode_command(..., audio_stream_indices: Optional[List[int]] = None, audio_stream_channels: Optional[List[int]] = None)`
- `build_gpu_hdr_intermediate_command(..., audio_stream_indices: Optional[List[int]] = None, audio_stream_channels: Optional[List[int]] = None)`
- `build_dvd_from_intermediate_command(..., audio_stream_channels: Optional[List[int]] = None)`
- `build_bluray_transcode_command(..., audio_stream_indices: Optional[List[int]] = None, audio_stream_channels: Optional[List[int]] = None, output_audio_files: Optional[List[str]] = None)`

- [ ] **Step 1: Write the failing tests**

In `tests/test_transcoder.py`:
```python
def test_dvd_transcode_multi_audio_command():
    cmd = build_dvd_transcode_command(
        input_file="/media/movie.mkv",
        output_mpg="/tmp/title_1.mpg",
        video_bitrate_kbps=4500,
        audio_stream_indices=[1, 2],
        audio_stream_channels=[6, 2],
    )
    # Check that both audio streams are mapped
    assert "-map" in cmd
    assert "0:1" in cmd
    assert "0:2" in cmd
    # Check audio encoders and bitrates
    cmd_str = " ".join(cmd)
    assert "-c:a:0 ac3" in cmd_str or ("-c:a" in cmd_str and "-b:a:0 384k" in cmd_str)
    assert "-b:a:0 384k" in cmd_str
    assert "-b:a:1 192k" in cmd_str

def test_bluray_transcode_multi_audio_command():
    cmd = build_bluray_transcode_command(
        input_file="/media/movie.mkv",
        output_video="/tmp/title_1.264",
        video_bitrate_kbps=25000,
        audio_stream_indices=[1, 2],
        audio_stream_channels=[6, 2],
        output_audio_files=["/tmp/title_1_track1.ac3", "/tmp/title_1_track2.ac3"],
    )
    cmd_str = " ".join(cmd)
    assert "/tmp/title_1_track1.ac3" in cmd
    assert "/tmp/title_1_track2.ac3" in cmd
    assert "0:1" in cmd
    assert "0:2" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_transcoder.py -k "test_dvd_transcode_multi_audio_command or test_bluray_transcode_multi_audio_command" -v`  
Expected: FAIL

- [ ] **Step 3: Implement multi-audio support in `transcoder.py`**

1. Update `build_dvd_transcode_command`:
   - Support `audio_stream_indices: Optional[List[int]] = None` and `audio_stream_channels: Optional[List[int]] = None` (with backwards-compatible `audio_stream_idx: int = 1` and `audio_channels: int = 2` fallback).
   - Map video `0:v:0` and all audio streams `0:{idx}`.
   - For each audio stream $i$: `-c:a:{i} ac3 -ar:a:{i} 48000 -ac:a:{i} {6|2} -b:a:{i} {384k|192k}`.
2. Update `build_gpu_hdr_intermediate_command` & `build_dvd_from_intermediate_command`:
   - Pass through / encode all selected audio streams.
3. Update `build_bluray_transcode_command`:
   - Support `output_audio_files: Optional[List[str]] = None`, mapping each audio stream index to its corresponding `.ac3` destination.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_transcoder.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/transcoder.py tests/test_transcoder.py
git commit -m "feat: support multi-audio mapping and encoding in transcode command builders"
```

---

### Task 4: Optical Disc Authoring (dvdauthor XML & tsMuxeR meta)

**Files:**
- Modify: `src/dvdcompress/authoring.py`
- Test: `tests/test_authoring.py`

**Interfaces:**
- `generate_dvdauthor_xml(titles: List[Dict[str, Any]], ...)` where each title dictionary can provide `audio_streams: List[Dict[str, str]]` with language tags
- `generate_tsmuxer_meta(video_file: str, audio_files: List[Dict[str, Any]], ...)` supporting multiple audio entries

- [ ] **Step 1: Write the failing tests**

In `tests/test_authoring.py`:
```python
def test_dvdauthor_xml_multi_audio_tracks():
    titles = [
        {
            "vob": "/tmp/title_1.mpg",
            "chapters": "00:00:00,00:05:00",
            "audio_streams": [
                {"format": "ac3", "lang": "en"},
                {"format": "ac3", "lang": "es"},
            ],
            "subtitles_lang": ["en"],
        }
    ]
    xml = generate_dvdauthor_xml(titles=titles)
    assert '<audio format="ac3" lang="en"' in xml
    assert '<audio format="ac3" lang="es"' in xml

def test_tsmuxer_meta_multi_audio_tracks():
    audio_files = [
        {"path": "/tmp/title_1_track1.ac3", "lang": "eng"},
        {"path": "/tmp/title_1_track2.ac3", "lang": "spa"},
    ]
    meta = generate_tsmuxer_meta(
        video_file="/tmp/title_1.264",
        audio_files=audio_files,
    )
    assert 'A_AC3, "/tmp/title_1_track1.ac3", lang=eng' in meta
    assert 'A_AC3, "/tmp/title_1_track2.ac3", lang=spa' in meta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_authoring.py -k "test_dvdauthor_xml_multi_audio_tracks or test_tsmuxer_meta_multi_audio_tracks" -v`  
Expected: FAIL

- [ ] **Step 3: Implement multi-audio support in `authoring.py`**

1. In `generate_dvdauthor_xml`:
   - For each title, inspect `audio_streams` (or fallback to single `audio_format="ac3"`).
   - Render `<audio format="{fmt}" lang="{lang}" />` for each selected audio stream (up to max 8 audio streams).
2. In `generate_tsmuxer_meta`:
   - Allow `audio_files: Optional[List[Dict[str, Any]]] = None` alongside backwards-compatible single `audio_file: Optional[str] = None`.
   - Render `A_AC3, "{path}", lang={lang}, track={idx}` for each audio stream.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_authoring.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/authoring.py tests/test_authoring.py
git commit -m "feat: add multi-audio track declarations in dvdauthor XML and tsMuxeR meta"
```

---

### Task 5: JobManager Pipeline Execution & State Persistence

**Files:**
- Modify: `src/dvdcompress/job_manager.py`
- Test: `tests/test_job_manager.py`, `tests/test_e2e.py`

**Interfaces:**
- `_run_pipeline`: extracts selected audio streams per title according to `job.selected_audio_indices`, passes them to transcoding and authoring stages.

- [ ] **Step 1: Write the failing test**

In `tests/test_job_manager.py`:
```python
@pytest.mark.asyncio
async def test_job_pipeline_audio_selection(tmp_path):
    jm = JobManager()
    job = jm.create_job(
        input_files=["/dummy/test.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="AUDIO_SEL_TEST",
        selected_audio_indices=[2],
    )
    assert job.selected_audio_indices == [2]
```

- [ ] **Step 2: Run test to verify it fails/passes**

Run: `./.venv/bin/pytest tests/test_job_manager.py -k "test_job_pipeline_audio_selection" -v`

- [ ] **Step 3: Update `_run_pipeline` in `job_manager.py`**

1. In `_run_pipeline`:
   - When probing media files, determine target audio streams for each title:
     ```python
     target_audio = info.audio_streams
     if job.selected_audio_indices is not None and len(job.selected_audio_indices) > 0:
         target_audio = [a for a in info.audio_streams if a.index in job.selected_audio_indices]
     if not target_audio and info.audio_streams:
         target_audio = [info.audio_streams[0]]
     ```
   - Cap target audio streams (max 8 for DVD, max 32 for Blu-ray).
   - Compute total audio bitrates and pass to `calculate_bitrate_budget`.
   - In DVD transcoding: pass all `target_audio` stream indices and channels to `build_dvd_transcode_command` / intermediate commands.
   - In Blu-ray transcoding: generate `.ac3` for each target audio stream and pass to `generate_tsmuxer_meta`.
   - In DVD authoring: generate `<audio format="ac3" lang="{lang}" />` for each target audio stream.

- [ ] **Step 4: Run test suite**

Run: `./.venv/bin/pytest tests/test_job_manager.py tests/test_e2e.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/job_manager.py tests/test_job_manager.py
git commit -m "feat: integrate audio track selection into job manager pipeline execution"
```

---

### Task 6: Web UI: Settings & Playlist Stream Inspector

**Files:**
- Modify: `src/dvdcompress/static/index.html`
- Modify: `src/dvdcompress/static/js/app.js`
- Modify: `src/dvdcompress/static/css/style.css`
- Test: `tests/test_ui.py`

**Interfaces:**
- UI Settings: Preferred Audio Language dropdown + Prefer Surround Audio toggle.
- UI Playlist Inspector: Interactive audio track checkboxes with smart initial selection based on settings.
- UI API Payloads: Include `selected_audio_indices` in `/api/jobs` and restore on job retry.

- [ ] **Step 1: Write test in `tests/test_ui.py`**

In `tests/test_ui.py`:
```python
def test_ui_contains_audio_settings_and_inspector(test_client):
    res = test_client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "preferred-audio-language" in html or "Preferred Audio Language" in html
    assert "prefer-surround-audio" in html or "Surround" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_ui.py -k "test_ui_contains_audio_settings" -v`  
Expected: FAIL

- [ ] **Step 3: Update `index.html`, `app.js`, and `style.css`**

1. In `src/dvdcompress/static/index.html`:
   - In the Settings modal/tab, add:
     - Preferred Audio Language dropdown (`select-preferred-audio-lang`).
     - Prefer Surround Sound (5.1ch) checkbox (`checkbox-prefer-surround-audio`).
2. In `src/dvdcompress/static/js/app.js`:
   - Load and save audio preferences via `/api/settings`.
   - Update `renderPlaylist()`:
     - Replace static audio stream list with interactive checkboxes:
       `<input type="checkbox" class="audio-track-checkbox" data-track-index="${a.index}" ${a._excluded ? '' : 'checked'} />`
     - Header actions: "Select Default" and "Select All".
     - Display badges: Index `#1`, Codec (`AC3`/`AAC`/`DTS`), Channels (`5.1ch`/`Stereo`), Language `[ENG]`, Title, Bitrate.
   - **Smart Default Logic on File Probe:**
     - Match audio tracks against `state.settings.preferred_audio_language` (e.g. "eng").
     - If multiple match and `state.settings.prefer_surround_audio` is true, pick the 5.1/surround track.
     - If none match, pick the first audio track.
     - Pre-select exactly **1** track (`_excluded = false` for the matched track, `_excluded = true` for others).
   - In `startPipeline()` / `addJob()`:
     - Collect `selected_audio_indices` across playlist items and include in request payload.
   - In job history / retry:
     - Restore `selected_audio_indices` when loading or retrying jobs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_ui.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/static/index.html src/dvdcompress/static/js/app.js src/dvdcompress/static/css/style.css tests/test_ui.py
git commit -m "feat: add audio settings and interactive stream inspector to web UI"
```

---

### Task 7: Full Regression & Integration Verification

**Files:**
- Test: all tests under `tests/`

- [ ] **Step 1: Run full test suite**

Run: `./.venv/bin/pytest tests/ -v`  
Expected: 100% PASS (all 200+ unit and integration tests passing)

- [ ] **Step 2: Commit any final test polishes**

```bash
git add tests/
git commit -m "test: verify complete test suite for audio track selection and settings"
```
