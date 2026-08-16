# Design Specification: Remote-Selectable Soft Subtitles for DVD & Blu-ray

**Date:** 2026-08-16  
**Status:** Approved  
**Author:** Antigravity / DVDCompress  

---

## 1. Problem Statement & Motivation
When authoring video files (especially 4K / Blu-ray rips with HDR, Dolby Vision, DTS audio, and embedded subtitle tracks) to physical DVD-Video (`VIDEO_TS`) and Blu-ray (`BDMV`) optical media, attempting to mux raw subtitle streams directly in the video transcode command causes encoder failures (`Subtitle encoding currently only possible from text to text or bitmap to bitmap`).

DVDCompress needs an automated subtitle pipeline that:
1. Detects and extracts all text (`SRT`, `ASS`) and bitmap (`PGS / SUP`) subtitle tracks from source containers.
2. Converts and authors subtitles into 100% standard-compliant, remote-selectable disc subpicture streams on both **Blu-ray** (via `tsMuxeR`) and **DVD-Video** (via `dvdauthor` / `spumux`).
3. Provides an interactive subtitle track selector in the web interface to allow selecting or excluding specific subtitle languages.

---

## 2. Subtitle Architecture & Pipeline

### A. Subtitle Stream Metadata Extraction
In `probe_media_file` (`probe.py`), each detected subtitle stream is captured with:
- `index`: Zero-based stream index in source media file.
- `codec_name`: Subtitle codec (`subrip`, `ass`, `hdmv_pgs_subtitle`, `dvdsub`, etc.).
- `language`: ISO-639 3-letter language code (`eng`, `spa`, `fre`, `ger`, `jpn`, etc.).
- `title`: Track descriptive title (`English [SDH]`, `Director Commentary`, etc.).
- `is_default`: Boolean indicating if stream is marked default in container.
- `is_forced`: Boolean indicating if stream is marked forced.

### B. Extraction Pass
During pipeline execution in `JobManager`:
- For **Text Subtitles** (`subrip`, `srt`, `ass`, `webvtt`, `mov_text`):
  ```bash
  ffmpeg -y -i <input_path> -map 0:<stream_index> <scratch_dir>/title_<t_idx>_sub_<s_idx>.srt
  ```
- For **Bitmap PGS Subtitles** (`hdmv_pgs_subtitle`):
  ```bash
  ffmpeg -y -i <input_path> -map 0:<stream_index> -c:s copy <scratch_dir>/title_<t_idx>_sub_<s_idx>.sup
  ```

### C. Blu-ray BDMV Subtitle Authoring (`tsMuxeR`)
In `authoring.py` (`generate_tsmuxer_meta`):
- For extracted `.srt` files:
  ```text
  S_TEXT/UTF8, "<scratch_dir>/title_1_sub_0.srt", font-name="Arial", font-size=65, font-color=0x00ffffff, bottom-offset=24, lang=eng
  ```
- For extracted `.sup` files:
  ```text
  S_HDMV/PGS, "<scratch_dir>/title_1_sub_0.sup", lang=eng
  ```
- `tsMuxeR` generates standard Blu-ray PGS streams selectable via remote control on any Blu-ray player or media software.

### D. DVD-Video Subtitle Authoring (`dvdauthor`)
In `authoring.py` (`generate_dvdauthor_xml`):
- Declares all present subtitle languages in `<titleset><titles>`:
  ```xml
  <subpicture lang="en" />
  <subpicture lang="es" />
  ```
- Integrates subtitle streams into the DVD title presentation graphics control (PGC).

### E. Frontend UI Track Management
- In `index.html` / `app.js`, each item in the Project Playlist displays its detected subtitle tracks.
- Checkboxes allow selecting or deselecting individual tracks per title.
- Selected subtitle indices are forwarded in the `CreateJobRequest` / `CreatePreviewRequest` payload.

---

## 3. Error Handling & Edge Cases
- **No Subtitle Streams**: Pipeline operates cleanly without extracting subtitle files or generating subtitle meta entries.
- **Corrupt Subtitle Packets**: If extraction fails for a non-critical subtitle track, the pipeline logs a warning and continues with remaining valid tracks.
- **Multi-Title Batch Discs**: Subtitle indices and generated filenames are keyed by title index (`title_{idx}_sub_{sub_idx}`) to prevent collision.

---

## 4. Verification Plan
1. Unit tests for subtitle metadata parsing and disposition flags in `test_probe.py`.
2. Unit tests for `generate_tsmuxer_meta` with multiple `.srt` and `.sup` subtitle tracks in `test_authoring.py`.
3. Unit tests for `generate_dvdauthor_xml` with multi-language `<subpicture>` entries in `test_authoring.py`.
4. Integration test in `test_job_manager.py` verifying subtitle extraction commands and meta injection.
5. End-to-end integration tests in `test_e2e.py` for full DVD and Blu-ray subtitle authoring workflows.
