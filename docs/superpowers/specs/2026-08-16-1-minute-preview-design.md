# Feature Specification: 1-Minute Video & ISO Preview Feature

**Date:** 2026-08-16  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Overview & Objective
DVDCompress authors and burns multi-gigabyte discs (DVD-5, DVD-9, BD-25, BD-50, etc.), which can take up to an hour or more to encode and author. To prevent wasted time and physical discs due to incorrect aspect ratio, standard (NTSC/PAL), bitrate budgeting, or audio track selection, this feature introduces a fast **1-minute preview clip** workflow.

Users can generate a 60-second sample taken from the midpoint of any selected video using their current project configuration. The output can be either:
1. **Sample Video Stream** (`.mpg` for DVD or `.m2ts` for Blu-ray)
2. **Sample Authored Mini-ISO** (`.iso` containing standard `VIDEO_TS` or `BDMV` structure)

Both output types are written directly to the configured output directory (`/output` or `dvd_output`).

---

## 2. Technical Architecture

### 2.1 Midpoint Seek & Time Calculation
For any target input video with probed duration $D$ (in seconds):
- **Seek Start Time ($T_{\text{start}}$):**
  $$T_{\text{start}} = \max(0.0, (D / 2.0) - 30.0)$$
- **Sample Duration ($T_{\text{duration}}$):**
  $$T_{\text{duration}} = \min(60.0, D)$$
- If the source video duration $D \le 60.0$, $T_{\text{start}} = 0.0$ and $T_{\text{duration}} = D$.

### 2.2 Transcoding Command Builder Updates (`transcoder.py`)
Both `build_dvd_transcode_command` and `build_bluray_transcode_command` will accept optional arguments:
- `seek_start_sec: Optional[float] = None`
- `duration_sec: Optional[float] = None`

When provided:
- FFmpeg injects `-ss <seek_start_sec>` **before** the `-i <input_file>` parameter for fast keyframe input seeking.
- FFmpeg injects `-t <duration_sec>` to bound the encode duration.
- The transcode maintains all active configuration parameters:
  - Video Bitrate (from calculated budget)
  - Target Format & Scaling (DVD NTSC 720×480, PAL 720×576 with 16:9 widescreen or 4:3 fullscreen SAR/DAR; Blu-ray 1080p)
  - Audio Encoding (AC3 48kHz stereo/5.1)
  - Hardware Acceleration (NVIDIA CUDA/NVENC or CPU fallback)

### 2.3 Domain Models (`models.py`)
- Extend `OutputMode` enum:
  - `PREVIEW_VIDEO = "preview_video"`
  - `PREVIEW_ISO = "preview_iso"`
- Add `CreatePreviewRequest` model:
  ```python
  class CreatePreviewRequest(BaseModel):
      input_file: str
      preview_mode: OutputMode = OutputMode.PREVIEW_VIDEO  # or OutputMode.PREVIEW_ISO
      disc_type: DiscType = DiscType.DVD5
      output_name: str = "preview_sample"
      tv_standard: TVStandard = TVStandard.AUTO
      aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
      menu_mode: MenuMode = MenuMode.AUTOPLAY
      use_gpu: bool = True
      custom_bitrate_kbps: Optional[int] = None
  ```

### 2.4 API Endpoint (`api.py`)
- **`POST /api/preview`**
  - Validates `input_file` exists.
  - Generates a unique Job ID (e.g. `prev_xxxxxxxx`).
  - Calculates bitrate budget matching current disc type and video duration.
  - Launches asynchronous pipeline in `JobManager`.
  - Returns `{"job_id": job_id, "status": "started", "preview_mode": req.preview_mode, "output_path": output_path}`.

### 2.5 Job Pipeline Execution (`job_manager.py`)
- **For `OutputMode.PREVIEW_VIDEO`:**
  1. Probe video metadata and calculate sample window.
  2. Transcode 60s slice directly to `/output/preview_<name>.<mpg|m2ts>`.
  3. Emit live progress, FPS, speed multiplier, and ETA over WebSocket `/ws/jobs/{job_id}`.
  4. Mark job as `COMPLETED` and log destination path.
- **For `OutputMode.PREVIEW_ISO`:**
  1. Probe video metadata and calculate sample window.
  2. Transcode 60s slice to scratch workspace (`/tmp/dvdcompress/<job_id>/sample.<mpg|m2ts>`).
  3. Author DVD structure with `dvdauthor` or Blu-ray structure with `tsMuxeR`.
  4. Master ISO with `genisoimage` (DVD) or `xorriso` (Blu-ray) directly into `/output/preview_<name>.iso`.
  5. Mark job as `COMPLETED` and log destination path.

---

## 3. Frontend Web Interface

### 3.1 Sidebar Preview Controls (`index.html`, `style.css`)
- In the Disc Configuration sidebar, place a **"Generate 1-Min Preview"** button next to **"Start Disc Project"**.
- The button is disabled when the playlist is empty.
- Clicking the button opens a modal dialog:
  - **Source Title Selector**: Dropdown if multiple titles are queued (defaults to first title).
  - **Preview Type**: Toggle between `Sample Video (.mpg / .m2ts)` and `Sample Mini-ISO (.iso)`.
  - **Summary**: Displays the exact 60-second time slice (e.g. `00:45:00 - 00:46:00`), video bitrate, aspect ratio, and acceleration mode.
  - **Submit Button**: **"Generate Sample in dvd_output"**.

### 3.2 Live Pipeline Monitoring (`app.js`)
- Submitting the preview redirects to the **Active Pipeline** monitor and connects to WebSocket `/ws/jobs/{job_id}`.
- Displays live transcoding metrics and terminal log output.
- When finished, displays a toast notification with the output filename in `/output`.

---

## 4. Verification & Testing Strategy

### 4.1 Unit Tests
- `tests/test_transcoder.py`: Verify that `-ss` and `-t` arguments are correctly placed when seeking/duration parameters are provided.
- `tests/test_api.py`: Verify `POST /api/preview` endpoint validation, parameter handling, and job creation.
- `tests/test_job_manager.py`: Test pipeline execution for both `preview_video` and `preview_iso` modes.

### 4.2 End-to-End Tests
- `tests/test_e2e.py`: Test end-to-end preview generation pipeline with synthetic media, verifying:
  - Generation of valid 60s `.mpg` sample video.
  - Generation of valid 60s `.iso` sample image.
  - Verification of non-zero output files in output directory.
