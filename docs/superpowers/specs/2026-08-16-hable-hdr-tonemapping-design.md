# Design Specification: Hable Filmic Tone-Mapping for HDR/Dolby Vision to SDR

**Date:** 2026-08-16  
**Status:** Approved  
**Author:** Antigravity / DVDCompress  

---

## 1. Goal & Rationale
When transcoding High Dynamic Range (HDR10, HDR10+, Dolby Vision Profile 5/7/8, HLG) 4K/1080p source video into standard definition DVD-Video (MPEG-2 / Rec.601) or Standard Dynamic Range Blu-ray (AVC / Rec.709), standard linear clipping causes washed-out midtones, loss of highlight details, and grayish skin tones.

Implementing the **John Hable filmic tone-mapping algorithm** (`tonemap=tonemap=hable`) via 32-bit floating-point planar RGB (`format=gbrpf32le`) compresses HDR luminance (1,000 to 4,000 nits) smoothly into the standard SDR 100-nit range while preserving highlight details and color saturation.

---

## 2. Technical Architecture

### A. Probing & HDR Flag Detection
In `probe.py`:
- Extract `color_primaries`, `color_transfer` (or `color_trc`), `color_space`, and `pix_fmt`.
- Compute `is_hdr = True` if:
  - `color_transfer` in (`"smpte2084"`, `"arib-std-b67"`, `"smpte428"`)
  - `color_primaries` == `"bt2020"`
  - `pix_fmt` in (`"yuv420p10le"`, `"p010le"`, `"yuv422p10le"`, `"yuv444p10le"`, `"yuv420p12le"`)

### B. Transcoding Filter Construction
In `transcoder.py`:
- Accept `is_hdr: bool = False` in `build_dvd_transcode_command` and `build_bluray_transcode_command`.
- If `is_hdr` is True:
  - DVD: `scale=720:480,setsar=...,setdar=...,format=gbrpf32le,tonemap=tonemap=hable:desat=0.5:peak=100,format=yuv420p`
  - Blu-ray: `scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=gbrpf32le,tonemap=tonemap=hable:desat=0.5:peak=100,format=yuv420p`
- If `is_hdr` is False (SDR sources):
  - Standard scaling + `format=yuv420p` (no unnecessary tone-mapping overhead).

### C. Pipeline Orchestration
In `job_manager.py`:
- Pass `is_hdr=info.is_hdr` to `build_dvd_transcode_command` and `build_bluray_transcode_command`.
- Log `"Applying Hable Filmic Tone-Mapping (HDR -> SDR)"` when active.

---

## 3. Verification Plan
- Unit tests in `test_probe.py` for HDR flag detection on 10-bit / ST2084 / BT.2020 videos.
- Unit tests in `test_transcoder.py` verifying `tonemap=hable` insertion on HDR commands.
- End-to-end integration tests in `test_e2e.py` validating full pipeline execution on HDR input media.
