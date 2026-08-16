# 1-Minute Video & ISO Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a 1-minute video sample preview feature (supporting both encoded sample video `.mpg`/`.m2ts` and authored sample mini-ISO `.iso`) sampled from the midpoint of selected media and saved to `/output` (dvd_output).

**Architecture:** 
- Inject optional `-ss <seek_start_sec>` (fast input seek) and `-t <duration_sec>` in `transcoder.py`.
- Add `PREVIEW_VIDEO` and `PREVIEW_ISO` to `OutputMode` and create `CreatePreviewRequest` in `models.py`.
- Orchestrate `_run_pipeline` in `job_manager.py` to handle both sample video encoding and sample ISO authoring/mastering.
- Expose `POST /api/preview` endpoint in `api.py`.
- Add a modal dialog and sidebar trigger button in `index.html` and `app.js` with live telemetry tracking.

**Tech Stack:** Python 3.10+, FastAPI, FFmpeg, dvdauthor, tsMuxeR, genisoimage, xorriso, Vanilla JS/CSS Single Page Application, pytest.

## Global Constraints
- All preview clips are strictly bounded to 60 seconds (or source duration if shorter).
- Seek start time calculation: `max(0.0, (duration / 2.0) - 30.0)`.
- Preview outputs are written directly to `/output` (`dvd_output`) prefixed with `preview_`.
- No in-browser video player required; the user accesses generated files directly in `/output` with instant console/toast feedback.
- Must maintain 100% passing tests across the entire test suite.

---

### Task 1: Extend Transcoding Command Builders with Seek Start & Duration

**Files:**
- Modify: `src/dvdcompress/transcoder.py:8-120`
- Test: `tests/test_transcoder.py`

**Interfaces:**
- `build_dvd_transcode_command(..., seek_start_sec: Optional[float] = None, duration_sec: Optional[float] = None)` -> `List[str]`
- `build_bluray_transcode_command(..., seek_start_sec: Optional[float] = None, duration_sec: Optional[float] = None)` -> `List[str]`

- [ ] **Step 1: Write failing unit tests for seeking and duration flags**

Add tests to `tests/test_transcoder.py`:
```python
def test_dvd_transcode_command_with_seek_and_duration():
    from dvdcompress.transcoder import build_dvd_transcode_command
    from dvdcompress.models import TVStandard, AspectRatio

    cmd = build_dvd_transcode_command(
        input_file="/media/test.mkv",
        output_mpg="/output/preview.mpg",
        video_bitrate_kbps=6000,
        seek_start_sec=120.0,
        duration_sec=60.0,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=False,
    )
    # Verify -ss comes before -i for fast input seeking
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    i_idx = cmd.index("-i")
    assert ss_idx < i_idx
    assert cmd[ss_idx + 1] == "120.0"
    
    # Verify -t is present
    assert "-t" in cmd
    t_idx = cmd.index("-t")
    assert cmd[t_idx + 1] == "60.0"
    assert cmd[-1] == "/output/preview.mpg"


def test_bluray_transcode_command_with_seek_and_duration():
    from dvdcompress.transcoder import build_bluray_transcode_command

    cmd = build_bluray_transcode_command(
        input_file="/media/test.mkv",
        output_m2ts="/output/preview.m2ts",
        video_bitrate_kbps=25000,
        seek_start_sec=300.5,
        duration_sec=60.0,
        use_gpu=False,
    )
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    i_idx = cmd.index("-i")
    assert ss_idx < i_idx
    assert cmd[ss_idx + 1] == "300.5"
    assert "-t" in cmd
    t_idx = cmd.index("-t")
    assert cmd[t_idx + 1] == "60.0"
    assert cmd[-1] == "/output/preview.m2ts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcoder.py -k "seek_and_duration" -v`
Expected: FAIL with `TypeError: unexpected keyword argument 'seek_start_sec'`

- [ ] **Step 3: Update `transcoder.py` to support seek and duration**

In `src/dvdcompress/transcoder.py`:
Update `build_dvd_transcode_command`:
```python
def build_dvd_transcode_command(
    input_file: str,
    output_mpg: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 2,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    use_gpu: bool = False,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> List[str]:
    cmd = ["ffmpeg", "-y"]

    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])

    if seek_start_sec is not None and seek_start_sec > 0:
        cmd.extend(["-ss", str(seek_start_sec)])

    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])

    cmd.extend(["-i", input_file])
    ...
```

Update `build_bluray_transcode_command`:
```python
def build_bluray_transcode_command(
    input_file: str,
    output_m2ts: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 6,
    use_gpu: bool = False,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> List[str]:
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        if seek_start_sec is not None and seek_start_sec > 0:
            cmd.extend(["-ss", str(seek_start_sec)])
        if duration_sec is not None and duration_sec > 0:
            cmd.extend(["-t", str(duration_sec)])
        cmd.extend(["-hwaccel", "cuda", "-i", input_file])
        cmd.extend(["-c:v", "h264_nvenc", "-profile:v", "high", "-level", "4.1"])
    else:
        if seek_start_sec is not None and seek_start_sec > 0:
            cmd.extend(["-ss", str(seek_start_sec)])
        if duration_sec is not None and duration_sec > 0:
            cmd.extend(["-t", str(duration_sec)])
        cmd.extend(["-i", input_file])
        cmd.extend(["-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-bluray-compat", "1"])
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_transcoder.py -v`
Expected: PASS (all tests in `test_transcoder.py` pass)

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/transcoder.py tests/test_transcoder.py
git commit -m "feat: add seek_start_sec and duration_sec parameters to transcode command builders"
```

---

### Task 2: Extend Domain Models for Preview Request & Modes

**Files:**
- Modify: `src/dvdcompress/models.py:29-33`, `src/dvdcompress/models.py:80-91`
- Test: `tests/test_calculator.py`

**Interfaces:**
- `OutputMode.PREVIEW_VIDEO = "preview_video"`
- `OutputMode.PREVIEW_ISO = "preview_iso"`
- `CreatePreviewRequest(input_file: str, preview_mode: OutputMode, disc_type: DiscType, output_name: str, ...)`

- [ ] **Step 1: Write unit tests for Preview models**

In `tests/test_calculator.py`:
```python
def test_preview_output_modes_and_request_model():
    from dvdcompress.models import OutputMode, DiscType, TVStandard, AspectRatio
    from dvdcompress.api import CreatePreviewRequest

    assert OutputMode.PREVIEW_VIDEO == "preview_video"
    assert OutputMode.PREVIEW_ISO == "preview_iso"

    req = CreatePreviewRequest(
        input_file="/media/sample.mkv",
        preview_mode=OutputMode.PREVIEW_VIDEO,
        disc_type=DiscType.DVD5,
        output_name="test_preview",
    )
    assert req.input_file == "/media/sample.mkv"
    assert req.preview_mode == OutputMode.PREVIEW_VIDEO
    assert req.disc_type == DiscType.DVD5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_calculator.py -k "test_preview_output_modes_and_request_model" -v`
Expected: FAIL with `ImportError` / `AttributeError`

- [ ] **Step 3: Update `models.py`**

In `src/dvdcompress/models.py`:
```python
class OutputMode(str, Enum):
    ISO_ONLY = "iso_only"
    BURN_DIRECT = "burn_direct"
    AUTHOR_AND_BURN = "author_and_burn"
    PREVIEW_VIDEO = "preview_video"
    PREVIEW_ISO = "preview_iso"
```

In `src/dvdcompress/api.py`:
```python
class CreatePreviewRequest(BaseModel):
    input_file: str
    preview_mode: OutputMode = OutputMode.PREVIEW_VIDEO
    disc_type: DiscType = DiscType.DVD5
    output_name: str = "preview_sample"
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    use_gpu: bool = True
    custom_bitrate_kbps: Optional[int] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_calculator.py -k "test_preview_output_modes_and_request_model" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/models.py src/dvdcompress/api.py tests/test_calculator.py
git commit -m "feat: add PREVIEW_VIDEO and PREVIEW_ISO output modes and CreatePreviewRequest model"
```

---

### Task 3: Implement Preview Pipeline Execution in JobManager

**Files:**
- Modify: `src/dvdcompress/job_manager.py:230-520`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- `JobManager.create_job(..., output_mode=OutputMode.PREVIEW_VIDEO | OutputMode.PREVIEW_ISO)`
- Handles seek start computation: `max(0.0, (duration / 2.0) - 30.0)`
- Handles 60s sample encoding and optional authoring/ISO mastering into `output_dir`.

- [ ] **Step 1: Write unit tests for preview job execution in `tests/test_job_manager.py`**

```python
@pytest.mark.asyncio
async def test_job_pipeline_preview_video_execution(tmp_path, monkeypatch):
    from dvdcompress.job_manager import JobManager, JobStage
    from dvdcompress.models import DiscType, OutputMode, MediaInfo

    jm = JobManager()
    media_file = str(tmp_path / "movie.mkv")
    with open(media_file, "w") as f:
        f.write("dummy")

    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir, exist_ok=True)

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie.mkv",
            duration_sec=7200.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=23.976,
            video_codec="h264",
            size_bytes=1000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    executed_cmds = []
    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass

    async def fake_exec(*cmd, **kwargs):
        executed_cmds.append(list(cmd))
        # Create output file
        out = cmd[-1]
        with open(out, "w") as f:
            f.write("video_stream")
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = jm.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.PREVIEW_VIDEO,
        output_name="test_movie_preview",
    )

    await jm.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await asyncio.sleep(0.05)

    job = jm.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    assert job.output_iso_path == os.path.join(output_dir, "preview_test_movie_preview.mpg")
    # Verify FFmpeg was called with -ss 3570.0 (7200 / 2 - 30) and -t 60.0
    ffmpeg_cmd = executed_cmds[0]
    assert "-ss" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-ss") + 1] == "3570.0"
    assert "-t" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-t") + 1] == "60.0"


@pytest.mark.asyncio
async def test_job_pipeline_preview_iso_execution(tmp_path, monkeypatch):
    from dvdcompress.job_manager import JobManager, JobStage
    from dvdcompress.models import DiscType, OutputMode, MediaInfo

    jm = JobManager()
    media_file = str(tmp_path / "movie.mkv")
    with open(media_file, "w") as f:
        f.write("dummy")

    scratch_dir = str(tmp_path / "scratch")
    output_dir = str(tmp_path / "output")

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie.mkv",
            duration_sec=3600.0,
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=23.976,
            video_codec="h264",
            size_bytes=1000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass

    async def fake_exec(*cmd, **kwargs):
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = jm.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.PREVIEW_ISO,
        output_name="test_iso_preview",
    )

    await jm.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await asyncio.sleep(0.05)

    job = jm.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    assert job.output_iso_path == os.path.join(output_dir, "preview_test_iso_preview.iso")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_job_manager.py -k "test_job_pipeline_preview" -v`
Expected: FAIL (preview logic not yet integrated into `_run_pipeline`)

- [ ] **Step 3: Implement preview handling in `JobManager._run_pipeline`**

In `src/dvdcompress/job_manager.py`:
- In `_run_pipeline`:
  - Check if `job.output_mode in (OutputMode.PREVIEW_VIDEO, OutputMode.PREVIEW_ISO)`:
    - Compute `seek_start = max(0.0, (info.duration_sec / 2.0) - 30.0)` if `info.duration_sec > 60.0` else `0.0`.
    - Compute `sample_dur = min(60.0, info.duration_sec)` if `info.duration_sec > 0` else `60.0`.
    - If `job.output_mode == OutputMode.PREVIEW_VIDEO`:
      - Set `out_file = os.path.join(output_dir, f"preview_{job.output_name}{out_ext}")`.
      - Transcode with `seek_start_sec=seek_start` and `duration_sec=sample_dur`.
      - Set `job.output_iso_path = out_file`.
      - Skip authoring/ISO stages and mark as completed!
    - If `job.output_mode == OutputMode.PREVIEW_ISO`:
      - Transcode sample slice to `work_dir`.
      - Author DVD/Blu-ray structure in `work_dir/author`.
      - Master ISO to `os.path.join(output_dir, f"preview_{job.output_name}.iso")`.
      - Mark as completed!

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_job_manager.py -k "test_job_pipeline_preview" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/job_manager.py tests/test_job_manager.py
git commit -m "feat: implement preview_video and preview_iso orchestration in JobManager"
```

---

### Task 4: Add `POST /api/preview` Endpoint

**Files:**
- Modify: `src/dvdcompress/api.py:270-340`
- Test: `tests/test_api.py`

**Interfaces:**
- `POST /api/preview` with body `CreatePreviewRequest` returns `{"job_id": str, "status": "started", "preview_mode": str, "output_path": str}`.

- [ ] **Step 1: Write unit tests for `/api/preview` endpoint**

In `tests/test_api.py`:
```python
def test_api_preview_endpoint_validation_and_launch(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from dvdcompress.api import app, job_manager

    client = TestClient(app)

    # 1. Validation error if input file doesn't exist
    resp = client.post("/api/preview", json={
        "input_file": "/nonexistent/video.mkv",
        "preview_mode": "preview_video",
        "disc_type": "dvd5",
        "output_name": "sample_prev"
    })
    assert resp.status_code == 404 or resp.status_code == 400

    # 2. Success case with real file
    test_media = tmp_path / "sample.mp4"
    test_media.write_bytes(b"dummy")

    async def fake_start(job_id, scratch_dir, output_dir):
        pass

    monkeypatch.setattr(job_manager, "start_job", fake_start)

    resp = client.post("/api/preview", json={
        "input_file": str(test_media),
        "preview_mode": "preview_video",
        "disc_type": "dvd5",
        "output_name": "sample_prev"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "started"
    assert data["preview_mode"] == "preview_video"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -k "test_api_preview_endpoint" -v`
Expected: FAIL (endpoint `/api/preview` not found 404)

- [ ] **Step 3: Implement endpoint in `api.py`**

In `src/dvdcompress/api.py`:
```python
@app.post("/api/preview")
async def create_preview(req: CreatePreviewRequest):
    if not os.path.exists(req.input_file):
        raise HTTPException(
            status_code=404, detail=f"Input file does not exist: {req.input_file}"
        )

    clean_name = "".join([c if c.isalnum() else "_" for c in req.output_name.strip()]) or "preview_sample"
    if clean_name.startswith("preview_"):
        clean_name = clean_name[len("preview_"):]

    job_id = job_manager.create_job(
        input_files=[req.input_file],
        disc_type=req.disc_type,
        output_mode=req.preview_mode,
        output_name=clean_name,
        tv_standard=req.tv_standard,
        aspect_ratio=req.aspect_ratio,
        menu_mode=req.menu_mode,
        use_gpu=req.use_gpu,
    )

    await job_manager.start_job(
        job_id, scratch_dir=get_scratch_dir(), output_dir=get_output_dir()
    )

    ext = ".iso" if req.preview_mode == OutputMode.PREVIEW_ISO else (".m2ts" if req.disc_type in (DiscType.BD25, DiscType.BD50, DiscType.BD66, DiscType.BD100, DiscType.BD128) else ".mpg")
    output_path = os.path.join(get_output_dir(), f"preview_{clean_name}{ext}")

    return {
        "job_id": job_id,
        "status": "started",
        "preview_mode": req.preview_mode.value,
        "output_path": output_path,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -k "test_api_preview_endpoint" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/api.py tests/test_api.py
git commit -m "feat: add POST /api/preview endpoint"
```

---

### Task 5: Add Preview Controls Modal & Trigger in Web Frontend

**Files:**
- Modify: `src/dvdcompress/static/index.html:398-407`
- Modify: `src/dvdcompress/static/css/style.css`
- Modify: `src/dvdcompress/static/js/app.js`
- Test: `tests/test_ui.py`

**Interfaces:**
- Preview Button in Configuration card footer: `<button id="btn-preview-project" class="btn btn-secondary btn-lg">`
- Preview Modal dialog: `#modal-preview` with video title select, preview type toggle (`Sample Video` vs `Sample Mini-ISO`), preview time details, and **Generate Sample in dvd_output** submit button.

- [ ] **Step 1: Write UI tests for Preview elements in `tests/test_ui.py`**

```python
def test_preview_modal_and_button_in_html():
    from fastapi.testclient import TestClient
    from dvdcompress.api import app

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    assert 'id="btn-preview-project"' in html
    assert 'id="modal-preview"' in html
    assert 'id="btn-confirm-preview"' in html
    assert 'id="preview-type-video"' in html
    assert 'id="preview-type-iso"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ui.py -k "test_preview_modal" -v`
Expected: FAIL (`id="btn-preview-project"` not in html)

- [ ] **Step 3: Update `index.html`, `style.css`, and `app.js`**

1. In `src/dvdcompress/static/index.html`:
Add the Preview Button in the Config Card footer alongside Start Disc Project:
```html
<div class="card-footer" style="flex-direction: column; gap: 0.75rem;">
  <div style="display: flex; gap: 0.5rem; width: 100%;">
    <button class="btn btn-secondary btn-lg" id="btn-preview-project" style="flex: 1;" disabled title="Generate 1-Minute Preview Clip">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path>
      </svg>
      <span>1-Min Preview</span>
    </button>
    <button class="btn btn-primary btn-lg" id="btn-start-project" style="flex: 2;" disabled>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
      </svg>
      <span>Start Disc Project</span>
    </button>
  </div>
</div>
```

Add Modal HTML at the end of `index.html`:
```html
<!-- Modal: 1-Minute Preview Generator -->
<div class="modal-overlay" id="modal-preview" style="display: none;">
  <div class="modal-card">
    <div class="modal-header">
      <div class="card-title-group">
        <svg class="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path>
        </svg>
        <div>
          <h3 class="card-title">Generate 1-Minute Preview</h3>
          <p class="card-subtitle">Sample clip from video midpoint saved to dvd_output</p>
        </div>
      </div>
      <button class="modal-close" id="btn-close-preview-modal">&times;</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label class="form-label" for="select-preview-title">Source Video Title</label>
        <select id="select-preview-title" class="form-select"></select>
      </div>

      <div class="form-group">
        <label class="form-label">Preview Format</label>
        <div class="segmented-control" id="control-preview-type">
          <button type="button" class="segmented-option active" id="preview-type-video" data-value="preview_video">Sample Video (.mpg / .m2ts)</button>
          <button type="button" class="segmented-option" id="preview-type-iso" data-value="preview_iso">Sample Mini-ISO (.iso)</button>
        </div>
      </div>

      <div class="preview-info-box" id="preview-info-summary">
        <div class="preview-info-row">
          <span class="preview-info-label">Sample Window:</span>
          <span class="preview-info-val" id="preview-window-text">Midpoint 60 seconds</span>
        </div>
        <div class="preview-info-row">
          <span class="preview-info-label">Encoding Target:</span>
          <span class="preview-info-val" id="preview-encoding-text">MPEG-2 NTSC 16:9 • 8,000 kbps</span>
        </div>
        <div class="preview-info-row">
          <span class="preview-info-label">Destination Folder:</span>
          <span class="preview-info-val" style="font-family: var(--font-mono); color: var(--color-primary-light);">/output (dvd_output)</span>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" id="btn-cancel-preview-modal">Cancel</button>
      <button class="btn btn-primary" id="btn-confirm-preview">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        Generate Sample in dvd_output
      </button>
    </div>
  </div>
</div>
```

2. In `src/dvdcompress/static/css/style.css`:
Add modal overlay, modal card, and info box styles.

3. In `src/dvdcompress/static/js/app.js`:
- Wire up `btn-preview-project`, `modal-preview`, `btn-close-preview-modal`, `btn-cancel-preview-modal`, `btn-confirm-preview`.
- Populate video title select and update sample window text on change.
- Call `POST /api/preview` on confirm, redirect to Active Pipeline tab and connect live WebSocket.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/static/index.html src/dvdcompress/static/css/style.css src/dvdcompress/static/js/app.js tests/test_ui.py
git commit -m "feat: add 1-min preview modal dialog and sidebar trigger button"
```

---

### Task 6: Comprehensive End-to-End Test Suite for Video & ISO Preview Pipeline

**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Add E2E tests for both DVD & Blu-ray sample video and sample ISO generation**

In `tests/test_e2e.py`:
```python
@pytest.mark.asyncio
async def test_e2e_dvd_preview_video_pipeline(tmp_path, monkeypatch):
    """Test generating a 1-minute DVD sample .mpg video."""
    from dvdcompress.job_manager import JobManager, JobStage
    from dvdcompress.models import DiscType, OutputMode, TVStandard, AspectRatio, MediaInfo

    jm = JobManager()
    media_file = str(tmp_path / "movie.mkv")
    with open(media_file, "w") as f:
        f.write("content")

    output_dir = str(tmp_path / "output")
    scratch_dir = str(tmp_path / "scratch")
    os.makedirs(output_dir, exist_ok=True)

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="movie.mkv",
            duration_sec=5400.0, # 90 minutes
            width=1920,
            height=1080,
            aspect_ratio="16:9",
            frame_rate=24.0,
            video_codec="h264",
            size_bytes=4000000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    executed_commands = []
    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass

    async def fake_exec(*cmd, **kwargs):
        executed_commands.append(list(cmd))
        out_target = cmd[-1]
        with open(out_target, "w") as f:
            f.write("SAMPLE_MPG_BYTES")
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = jm.create_job(
        input_files=[media_file],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.PREVIEW_VIDEO,
        output_name="my_movie",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=False,
    )

    await jm.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await asyncio.sleep(0.05)

    job = jm.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    expected_out = os.path.join(output_dir, "preview_my_movie.mpg")
    assert job.output_iso_path == expected_out
    assert os.path.exists(expected_out)

    # Check that seek was 5400/2 - 30 = 2670.0
    cmd = executed_commands[0]
    assert "-ss" in cmd
    assert cmd[cmd.index("-ss") + 1] == "2670.0"
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "60.0"


@pytest.mark.asyncio
async def test_e2e_bluray_preview_iso_pipeline(tmp_path, monkeypatch):
    """Test generating a 1-minute Blu-ray sample .iso image."""
    from dvdcompress.job_manager import JobManager, JobStage
    from dvdcompress.models import DiscType, OutputMode, MediaInfo

    jm = JobManager()
    media_file = str(tmp_path / "feature.mkv")
    with open(media_file, "w") as f:
        f.write("content")

    output_dir = str(tmp_path / "output")
    scratch_dir = str(tmp_path / "scratch")
    os.makedirs(output_dir, exist_ok=True)

    async def fake_probe(path):
        return MediaInfo(
            path=path,
            filename="feature.mkv",
            duration_sec=7200.0,
            width=3840,
            height=2160,
            aspect_ratio="16:9",
            frame_rate=23.976,
            video_codec="hevc",
            size_bytes=25000000000,
        )

    monkeypatch.setattr("dvdcompress.job_manager.probe_media_file", fake_probe)

    executed_commands = []
    class FakeProc:
        returncode = 0
        async def wait(self): return 0
        @property
        def stderr(self):
            class Stream:
                async def read(self, n): return b""
            return Stream()
        def send_signal(self, sig): pass
        def kill(self): pass

    async def fake_exec(*cmd, **kwargs):
        executed_commands.append(list(cmd))
        out_target = cmd[-1]
        if out_target.endswith(".iso") or out_target.endswith(".m2ts"):
            with open(out_target, "w") as f:
                f.write("SAMPLE_ISO_BYTES")
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    job_id = jm.create_job(
        input_files=[media_file],
        disc_type=DiscType.BD25,
        output_mode=OutputMode.PREVIEW_ISO,
        output_name="feature_film",
        use_gpu=False,
    )

    await jm.start_job(job_id, scratch_dir=scratch_dir, output_dir=output_dir)
    await asyncio.sleep(0.05)

    job = jm.get_job(job_id)
    assert job.stage == JobStage.COMPLETED
    expected_out = os.path.join(output_dir, "preview_feature_film.iso")
    assert job.output_iso_path == expected_out
    assert os.path.exists(expected_out)
```

- [ ] **Step 2: Run all tests in repository**

Run: `.venv/bin/pytest tests/ -v`
Expected: 100% tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add comprehensive end-to-end tests for preview video and ISO pipelines"
```
