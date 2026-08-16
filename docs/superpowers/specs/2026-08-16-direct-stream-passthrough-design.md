# Design Specification: Direct Remux & Stream Passthrough for DVD & Blu-ray

**Date:** 2026-08-16  
**Status:** Approved  
**Author:** Antigravity / DVDCompress  

---

## 1. Goal & Motivation
When authoring video files (such as 4K UHD Blu-ray remuxes with HDR10/Dolby Vision or 1080p Blu-ray remuxes) to optical disc media that has sufficient sector capacity, re-encoding the video causes unnecessary CPU/GPU load, encoding time, and generation loss.

Providing an optional **Direct Remux / Stream Passthrough** mode allows DVDCompress to author standard-compliant BDMV or VIDEO_TS structures by directly remuxing compliant elementary video streams without transcoding, preserving 100% untouched HDR/Dolby Vision/HEVC/H.264 master quality.

---

## 2. Technical Architecture

### A. Domain Models & API
- In `Job`, `CreateJobRequest`, `CreatePreviewRequest`:
  - `passthrough: bool = False`

### B. Passthrough Eligibility Criteria
In `JobManager`:
1. **UHD Blu-ray (BD-66, BD-100, BD-128)**:
   - Target format supports native 4K HEVC HDR10 / Dolby Vision.
   - If `info.video_codec in ("hevc", "h264")` and total size $\le$ disc target capacity:
     - Directly ingest video stream into `tsMuxeR` using `V_MPEGH/ISO/HEVC` or `V_MPEG4/ISO/AVC`.
     - FFmpeg video re-encoding is completely bypassed.
2. **Standard Blu-ray (BD-25, BD-50)**:
   - If `info.video_codec == "h264"` and `info.width <= 1920` and `info.height <= 1080` and `not info.is_hdr` and total size $\le$ disc target capacity:
     - Directly ingest into `tsMuxeR` using `V_MPEG4/ISO/AVC`.
3. **DVD-Video (DVD-5, DVD-9)**:
   - If `info.video_codec == "mpeg2video"` and `info.width == 720` and total size $\le$ disc target capacity:
     - Direct remux without re-encoding.
   - Otherwise, transcode to standard MPEG-2 as required by physical DVD players.

### C. tsMuxeR Meta Generator Enhancements
In `authoring.py` (`generate_tsmuxer_meta`):
- Support HEVC video streams:
  `V_MPEGH/ISO/HEVC, "{vf}", fps=23.976, insertSEI, contSPS` for 4K UHD / HEVC inputs.
- Support AVC video streams:
  `V_MPEG4/ISO/AVC, "{vf}", fps=23.976, insertSEI, contSPS` for H.264 inputs.

### D. Web UI Toggle
In `index.html` and `app.js`:
- Add `toggle-passthrough` switch in Disc Configuration card.
- Forward `passthrough: state.config.passthrough` in job creation and preview payloads.

---

## 3. Verification Plan
- Unit tests in `test_authoring.py` for HEVC and AVC meta generation.
- Unit tests in `test_job_manager.py` verifying passthrough pipeline execution (skipping transcode subprocess).
- Unit tests in `test_api.py` for `passthrough` field in requests.
- UI tests in `test_ui.py` for toggle rendering and state persistence.
- End-to-end integration tests in `test_e2e.py` for 4K UHD HDR passthrough remuxing to BD-66/100.
