# Design Specification: Audio Track Selection & Smart Default Settings

**Date:** 2026-08-26  
**Status:** Approved  
**Topic:** Configurable Audio Track Selection with Settings-Based Default Preferences  

---

## 1. Overview & Objectives

DVDCompress currently defaults to transcoding only the first probed audio stream (`audio_streams[0]`) from a source media file into Dolby Digital AC-3 (48 kHz, 192 kbps stereo or 384/448 kbps 5.1).

This feature adds:
1. **Interactive Audio Track Selection:** Users can select one or multiple audio tracks per title in the Playlist Stream Inspector (similar to subtitle selection), supporting multi-audio authoring for DVD-Video and Blu-ray.
2. **Smart Default Settings:** Global settings in `AppSettings` (`preferred_audio_language` and `prefer_surround_audio`) automatically pre-select the optimal single audio track when media files are probed and loaded.
3. **Full Pipeline Integration:** End-to-end support across dynamic bitrate budgeting, multi-stream FFmpeg transcoding, `dvdauthor` multi-audio PGC definitions, `tsMuxeR` multi-audio tracks, and job persistence/retry.

---

## 2. Architecture & Detailed Component Changes

### 2.1 Configuration & Data Models

#### `src/dvdcompress/config.py`
Update `AppSettings` with audio preferences:
```python
class AppSettings(BaseModel):
    max_concurrent_jobs: int = Field(default=5, ge=1, le=20)
    preferred_audio_language: str = Field(default="eng")  # "auto", "eng", "jpn", "spa", "fre", "deu", etc.
    prefer_surround_audio: bool = Field(default=True)      # Prefer 5.1/7.1 over stereo when matching
```

#### `src/dvdcompress/models.py` & `src/dvdcompress/api.py`
* Update `JobCreateRequest`, `BurnOnlyRequest`, and `Job` domain models to accept:
  ```python
  selected_audio_indices: Optional[List[int]] = None
  ```
* In `api.py`, propagate `selected_audio_indices` in `/api/jobs` and `/api/burn/iso`.

---

### 2.2 Transcoding Engine (`src/dvdcompress/transcoder.py`)

Update transcode command generators to support a list of audio streams:

* **Audio Stream Model / Specifier:** Each audio track specification contains `index: int`, `channels: int`, `language: str`.
* **DVD Transcoding (`build_dvd_transcode_command`, `build_dvd_from_intermediate_command`, `build_gpu_hdr_intermediate_command`):**
  * Iterate over all selected audio streams:
    * Map stream: `-map 0:{stream_idx}`
    * Encode stream $i$: `-c:a:{i} ac3 -ar:a:{i} 48000`
    * Bitrate/Channels $i$: `-ac:a:{i} 6 -b:a:{i} 384k` (if channels $\ge 6$) or `-ac:a:{i} 2 -b:a:{i} 192k` (if stereo/mono).
* **Blu-ray Transcoding (`build_bluray_transcode_command`):**
  * Support generating multiple elementary audio files (`title_1_track1.ac3`, `title_1_track2.ac3`, etc.) at 448 kbps (5.1) or 192 kbps (stereo).

---

### 2.3 Authoring Specifications (`src/dvdcompress/authoring.py`)

* **DVD-Video (`generate_dvdauthor_xml`):**
  * Generate `<audio format="ac3" lang="{lang}" />` for each selected track inside `<titles>` for the title's PGC (DVD standard supports up to 8 audio tracks per title).
* **Blu-ray BDMV (`generate_tsmuxer_meta`):**
  * Generate `A_AC3, "{audio_file_path}", lang={lang}, track={track_num}` entries for all transcoded audio streams.

---

### 2.4 Bitrate Budgeting (`src/dvdcompress/calculator.py`)

* Ensure `calculate_bitrate_budget` sums the bitrates of all selected audio streams for all titles in the project, automatically lowering the video bitrate ceiling slightly if multiple audio tracks are present so the disc never overflows.

---

### 2.5 Pipeline Execution (`src/dvdcompress/job_manager.py`)

* In `_run_pipeline`:
  * Determine selected audio streams per title:
    * Filter `info.audio_streams` using `job.selected_audio_indices` if provided.
    * Fallback: if empty or unselected, default to `[info.audio_streams[0]]` (or first available audio stream).
    * Enforce optical spec caps (up to 8 audio tracks for DVD, up to 32 for Blu-ray).
  * Transcode and author all selected audio tracks.

---

### 2.6 Web UI & Settings Interface (`src/dvdcompress/static/`)

#### Settings Tab (`index.html` & `app.js`):
* Add UI controls in Settings:
  * **Preferred Audio Language** dropdown (`Auto / First Track`, `English [eng]`, `Japanese [jpn]`, `Spanish [spa]`, `French [fre]`, `German [deu]`, `Italian [ita]`, `Portuguese [por]`, `Mandarin [zho]`, `Korean [kor]`, `Undetermined [und]`).
  * **Prefer Surround Sound (5.1ch)** checkbox toggle.

#### Playlist Stream Inspector (`app.js` & `style.css`):
* Under **Audio Streams**, replace static list with interactive checkboxes:
  * Checkbox per track with: `Track #index`, Codec (`AC3`/`AAC`/`DTS`/`FLAC`), Channels (`5.1ch` vs `Stereo`), Language (`[ENG]`), Title/Description (e.g. `Main Feature`, `Commentary`), and Bitrate.
  * Header controls: "Select Default" (re-applies settings default) and "Select All".
  * Safety validation: warning badge if 0 audio tracks are selected, with automatic fallback on submission.
* **Smart Initial Selection Algorithm:**
  1. If `preferred_audio_language` is not `"auto"`, search for audio tracks matching the language code.
  2. If multiple match and `prefer_surround_audio` is enabled, pick the track with $\ge 6$ channels (or highest channel count).
  3. If none match the language preference, default to `audio_streams[0]`.
  4. Exactly **1** audio track is pre-selected by default.
* **Job Payload & State:**
  * Collect `selected_audio_indices` across playlist items and include in the `/api/jobs` POST request.
  * Restore `selected_audio_indices` when loading or retrying jobs from history.

---

## 3. Verification & Testing Strategy

1. **Unit Tests:**
   * `tests/test_calculator.py`: Verify bitrate calculations with multiple audio tracks (e.g. 5.1 track + stereo commentary = 576 kbps total audio).
   * `tests/test_transcoder.py`: Test multi-audio command line generation for both DVD and Blu-ray.
   * `tests/test_authoring.py`: Verify `dvdauthor.xml` and `tsmuxer.meta` output with multiple audio tracks and language tags.
   * `tests/test_api.py`: Verify settings persistence (`preferred_audio_language`, `prefer_surround_audio`) and job creation with `selected_audio_indices`.
2. **Integration & E2E Tests:**
   * `tests/test_job_manager.py` & `tests/test_e2e.py`: Verify end-to-end job lifecycle with single-track and multi-track audio selections.
3. **Manual / UI Verification:**
   * Inspect audio track checkboxes and settings in the browser.
