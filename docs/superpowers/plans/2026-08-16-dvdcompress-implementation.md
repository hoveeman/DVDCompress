# DVDCompress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready, hardware-accelerated (NVIDIA NVENC/NVDEC + multi-core CPU) Docker web application for transcoding, authoring, and burning standard-compliant DVD-Video (`VIDEO_TS`) and Blu-ray (`BDMV`) discs or standalone ISO images from unencrypted video files.

**Architecture:** A modular Python 3.11 FastAPI backend orchestrates media probing (`ffprobe`), multi-file aggregate bitrate budgeting, transcoding (FFmpeg with NVDEC/NVENC/CPU), disc authoring (`dvdauthor`/`spumux`/`tsMuxeR`), ISO mastering (`genisoimage`/`xorriso`), optical drive discovery/burning (`growisofs`/`cdrskin`), and system hardware monitoring. A responsive modern Web UI connects via REST and WebSockets for real-time stage progress and telemetry.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, WebSockets, FFmpeg, dvdauthor, spumux, tsMuxeR, genisoimage, dvd+rw-tools (growisofs), cdrskin, xorriso, Vanilla HTML5/CSS3/ES6, Docker, NVIDIA CUDA 12.4 runtime, pytest.

## Global Constraints
- **Platform:** Linux x86_64 container based on Ubuntu 22.04 with CUDA 12.4 runtime.
- **Hardware Acceleration:** Auto-detects NVIDIA GPU availability; uses NVDEC decode and NVENC encode when present, with automatic multi-core CPU fallback (`libx264`/`mpeg2video`).
- **Standard Compliance:** DVD-Video must produce strict `VIDEO_TS` structures with NTSC (720x480) or PAL (720x576) MPEG-2 and AC3 audio; Blu-ray must produce standard `BDMV` structures (AVC H.264 High Profile 4.1).
- **Capacity Limits:** Disc target budgets: DVD-5 ($4.30\text{ GiB}$), DVD-9 ($7.85\text{ GiB}$), BD-25 ($23.00\text{ GiB}$), BD-50 ($46.00\text{ GiB}$).

---

### Task 1: Project Setup, Data Models & Bitrate Engine

**Files:**
- Create: `pyproject.toml`
- Create: `src/dvdcompress/__init__.py`
- Create: `src/dvdcompress/config.py`
- Create: `src/dvdcompress/models.py`
- Create: `src/dvdcompress/calculator.py`
- Test: `tests/test_calculator.py`

**Interfaces:**
- Produces:
  - `DiscType` (Enum: `DVD5`, `DVD9`, `BD25`, `BD50`)
  - `TVStandard` (Enum: `NTSC`, `PAL`, `AUTO`)
  - `AspectRatio` (Enum: `RATIO_16_9`, `RATIO_4_3`)
  - `MediaStreamInfo`, `VideoMetadata`, `ProjectConfig`, `BitrateBudget` (Pydantic models)
  - `calculate_bitrate_budget(total_duration_sec: float, disc_type: DiscType, audio_tracks_kbps: list[int], video_count: int) -> BitrateBudget`

- [ ] **Step 1: Write the failing tests for bitrate calculation**

```python
# tests/test_calculator.py
import pytest
from dvdcompress.models import DiscType
from dvdcompress.calculator import calculate_bitrate_budget, DISC_CAPACITIES_MB

def test_dvd5_single_movie_bitrate():
    # 2 hour movie (7200 sec) with 1x AC3 192k audio on DVD-5 (4300 MB)
    budget = calculate_bitrate_budget(
        total_duration_sec=7200,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1
    )
    # Available bytes = ~4300 MB * 0.96 = ~4128 MB -> ~33024000 kbits
    # Audio total = 192 * 7200 = 1382400 kbits
    # Video bits = 31641600 kbits / 7200 s = ~4394 kbps
    assert 4000 <= budget.video_bitrate_kbps <= 4600
    assert budget.audio_bitrate_kbps == 192
    assert budget.total_bitrate_kbps <= 9800
    assert budget.fits_disc is True

def test_dvd5_clamping_short_video():
    # 5 minute video (300 sec) on DVD-5 should clamp to max DVD-Video bitrate (8000 kbps)
    budget = calculate_bitrate_budget(
        total_duration_sec=300,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1
    )
    assert budget.video_bitrate_kbps == 8000
    assert budget.fits_disc is True

def test_multi_episode_dvd9_calculation():
    # 6 episodes of 45 mins each = 270 mins = 16200 sec on DVD-9 (7850 MB)
    budget = calculate_bitrate_budget(
        total_duration_sec=16200,
        disc_type=DiscType.DVD9,
        audio_tracks_kbps=[192],
        video_count=6
    )
    assert 3000 <= budget.video_bitrate_kbps <= 4000
    assert budget.fits_disc is True

def test_oversized_duration_warning():
    # 10 hours on DVD-5 -> drops below min acceptable bitrate (2000 kbps)
    budget = calculate_bitrate_budget(
        total_duration_sec=36000,
        disc_type=DiscType.DVD5,
        audio_tracks_kbps=[192],
        video_count=1
    )
    assert budget.video_bitrate_kbps == 2000
    assert budget.fits_disc is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_calculator.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'dvdcompress'`

- [ ] **Step 3: Implement `pyproject.toml`, `config.py`, `models.py`, and `calculator.py`**

```python
# src/dvdcompress/models.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List

class DiscType(str, Enum):
    DVD5 = "dvd5"
    DVD9 = "dvd9"
    BD25 = "bd25"
    BD50 = "bd50"

class TVStandard(str, Enum):
    AUTO = "auto"
    NTSC = "ntsc"
    PAL = "pal"

class AspectRatio(str, Enum):
    RATIO_16_9 = "16:9"
    RATIO_4_3 = "4:3"

class MenuMode(str, Enum):
    AUTOPLAY = "autoplay"
    MENU = "menu"

class OutputMode(str, Enum):
    ISO_ONLY = "iso_only"
    BURN_DIRECT = "burn_direct"
    AUTHOR_AND_BURN = "author_and_burn"

class AudioStreamInfo(BaseModel):
    index: int
    codec_name: str
    channels: int
    channel_layout: Optional[str] = "stereo"
    language: Optional[str] = "und"
    title: Optional[str] = None
    bitrate: Optional[int] = None

class SubtitleStreamInfo(BaseModel):
    index: int
    codec_name: str
    language: Optional[str] = "und"
    title: Optional[str] = None

class MediaInfo(BaseModel):
    path: str
    filename: str
    duration_sec: float
    width: int
    height: int
    aspect_ratio: str
    frame_rate: float
    video_codec: str
    audio_streams: List[AudioStreamInfo] = []
    subtitle_streams: List[SubtitleStreamInfo] = []
    chapters_count: int = 0
    size_bytes: int = 0

class BitrateBudget(BaseModel):
    disc_type: DiscType
    target_capacity_mb: float
    used_capacity_mb: float
    capacity_percent: float
    video_bitrate_kbps: int
    audio_bitrate_kbps: int
    mux_overhead_kbps: int
    total_bitrate_kbps: int
    fits_disc: bool
    warnings: List[str] = []
```

```python
# src/dvdcompress/calculator.py
from dvdcompress.models import DiscType, BitrateBudget

# Target usable budgets in MegaBytes (MB = 1024 * 1024 bytes)
DISC_CAPACITIES_MB = {
    DiscType.DVD5: 4300.0,
    DiscType.DVD9: 7850.0,
    DiscType.BD25: 23000.0,
    DiscType.BD50: 46000.0,
}

# Bitrate constraints in kbps
DVD_MIN_VIDEO_BITRATE = 2000
DVD_MAX_VIDEO_BITRATE = 8000
DVD_MAX_TOTAL_BITRATE = 9800

BD_MIN_VIDEO_BITRATE = 5000
BD_MAX_VIDEO_BITRATE = 35000
BD_MAX_TOTAL_BITRATE = 40000

def calculate_bitrate_budget(
    total_duration_sec: float,
    disc_type: DiscType,
    audio_tracks_kbps: list[int] = None,
    video_count: int = 1,
) -> BitrateBudget:
    if audio_tracks_kbps is None or len(audio_tracks_kbps) == 0:
        audio_tracks_kbps = [192]

    if total_duration_sec <= 0:
        total_duration_sec = 1.0

    target_mb = DISC_CAPACITIES_MB[disc_type]
    target_bits = target_mb * 1024 * 1024 * 8

    # Reserve 4% for container multiplexing and filesystem overhead
    mux_factor = 0.96
    usable_bits = target_bits * mux_factor

    # Audio bits
    total_audio_kbps = sum(audio_tracks_kbps)
    audio_bits = total_audio_kbps * 1000 * total_duration_sec

    # Available video bits
    available_video_bits = usable_bits - audio_bits
    raw_video_bitrate_kbps = int((available_video_bits / total_duration_sec) / 1000)

    warnings = []
    fits = True

    is_dvd = disc_type in (DiscType.DVD5, DiscType.DVD9)
    min_v = DVD_MIN_VIDEO_BITRATE if is_dvd else BD_MIN_VIDEO_BITRATE
    max_v = DVD_MAX_VIDEO_BITRATE if is_dvd else BD_MAX_VIDEO_BITRATE
    max_total = DVD_MAX_TOTAL_BITRATE if is_dvd else BD_MAX_TOTAL_BITRATE

    if raw_video_bitrate_kbps < min_v:
        video_bitrate = min_v
        fits = False
        warnings.append(
            f"Content duration ({total_duration_sec/60:.1f} min) exceeds recommended capacity for {disc_type.value.upper()}. Quality may be degraded."
        )
    elif raw_video_bitrate_kbps > max_v:
        video_bitrate = max_v
    else:
        video_bitrate = raw_video_bitrate_kbps

    # Check total bitrate
    if video_bitrate + total_audio_kbps > max_total:
        video_bitrate = max_total - total_audio_kbps

    mux_overhead_kbps = int((video_bitrate + total_audio_kbps) * 0.04)
    total_kbps = video_bitrate + total_audio_kbps + mux_overhead_kbps

    # Estimate used MB
    total_project_bits = total_kbps * 1000 * total_duration_sec
    used_mb = (total_project_bits / 8) / (1024 * 1024)
    capacity_percent = min(100.0, (used_mb / target_mb) * 100.0)

    return BitrateBudget(
        disc_type=disc_type,
        target_capacity_mb=round(target_mb, 1),
        used_capacity_mb=round(used_mb, 1),
        capacity_percent=round(capacity_percent, 1),
        video_bitrate_kbps=video_bitrate,
        audio_bitrate_kbps=total_audio_kbps,
        mux_overhead_kbps=mux_overhead_kbps,
        total_bitrate_kbps=total_kbps,
        fits_disc=fits,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_calculator.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: implement disc models and dynamic bitrate calculator"
```

---

### Task 2: Media Prober & Stream Analyzer

**Files:**
- Create: `src/dvdcompress/probe.py`
- Test: `tests/test_probe.py`

**Interfaces:**
- Consumes: `MediaInfo`, `AudioStreamInfo`, `SubtitleStreamInfo` from `models.py`
- Produces: `async def probe_media_file(file_path: str) -> MediaInfo`

- [ ] **Step 1: Write the failing tests for media probing**

```python
# tests/test_probe.py
import pytest
import json
from unittest.mock import patch, AsyncMock
from dvdcompress.probe import probe_media_file, parse_ffprobe_output

SAMPLE_FFPROBE_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "display_aspect_ratio": "16:9",
            "r_frame_rate": "24000/1001",
            "duration": "5400.5"
        },
        {
            "codec_type": "audio",
            "index": 1,
            "codec_name": "eac3",
            "channels": 6,
            "channel_layout": "5.1(side)",
            "tags": {"language": "eng", "title": "English 5.1"}
        },
        {
            "codec_type": "subtitle",
            "index": 2,
            "codec_name": "subrip",
            "tags": {"language": "eng", "title": "English SDH"}
        }
    ],
    "format": {
        "duration": "5400.5",
        "size": "4500000000"
    },
    "chapters": [
        {"id": 0, "start_time": "0.0", "end_time": "300.0"},
        {"id": 1, "start_time": "300.0", "end_time": "600.0"}
    ]
}

def test_parse_ffprobe_output():
    media_info = parse_ffprobe_output("/media/movie.mkv", SAMPLE_FFPROBE_JSON)
    assert media_info.filename == "movie.mkv"
    assert media_info.duration_sec == 5400.5
    assert media_info.width == 1920
    assert media_info.height == 1080
    assert media_info.aspect_ratio == "16:9"
    assert round(media_info.frame_rate, 2) == 23.98
    assert len(media_info.audio_streams) == 1
    assert media_info.audio_streams[0].channels == 6
    assert media_info.audio_streams[0].language == "eng"
    assert len(media_info.subtitle_streams) == 1
    assert media_info.chapters_count == 2

@pytest.mark.asyncio
async def test_probe_media_file():
    with patch("dvdcompress.probe.run_ffprobe_json", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = SAMPLE_FFPROBE_JSON
        result = await probe_media_file("/media/movie.mkv")
        assert result.filename == "movie.mkv"
        assert result.duration_sec == 5400.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_probe.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'dvdcompress.probe'`

- [ ] **Step 3: Implement `src/dvdcompress/probe.py`**

```python
# src/dvdcompress/probe.py
import json
import os
import asyncio
from typing import Dict, Any
from dvdcompress.models import MediaInfo, AudioStreamInfo, SubtitleStreamInfo

async def run_ffprobe_json(file_path: str) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        file_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {file_path}: {stderr.decode()}")
    return json.loads(stdout.decode())

def parse_ffprobe_output(file_path: str, data: Dict[str, Any]) -> MediaInfo:
    filename = os.path.basename(file_path)
    streams = data.get("streams", [])
    format_info = data.get("format", {})
    chapters = data.get("chapters", [])

    duration = float(format_info.get("duration", 0.0))
    size_bytes = int(format_info.get("size", 0))

    video_codec = "unknown"
    width, height = 720, 480
    dar = "16:9"
    frame_rate = 29.97

    audio_streams = []
    subtitle_streams = []

    for s in streams:
        c_type = s.get("codec_type")
        if c_type == "video" and video_codec == "unknown":
            video_codec = s.get("codec_name", "unknown")
            width = int(s.get("width", 720))
            height = int(s.get("height", 480))
            dar = s.get("display_aspect_ratio", "16:9")
            if dar not in ("16:9", "4:3"):
                # derive from width/height
                ratio = width / height if height > 0 else 1.77
                dar = "16:9" if ratio >= 1.5 else "4:3"

            r_fps = s.get("r_frame_rate", "30/1")
            try:
                num, den = map(float, r_fps.split("/"))
                frame_rate = num / den if den > 0 else 29.97
            except Exception:
                frame_rate = 29.97

            if duration == 0.0 and "duration" in s:
                duration = float(s.get("duration", 0.0))

        elif c_type == "audio":
            tags = s.get("tags", {})
            audio_streams.append(
                AudioStreamInfo(
                    index=int(s.get("index", len(audio_streams))),
                    codec_name=s.get("codec_name", "unknown"),
                    channels=int(s.get("channels", 2)),
                    channel_layout=s.get("channel_layout", "stereo"),
                    language=tags.get("language", "und"),
                    title=tags.get("title"),
                    bitrate=int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
                )
            )
        elif c_type == "subtitle":
            tags = s.get("tags", {})
            subtitle_streams.append(
                SubtitleStreamInfo(
                    index=int(s.get("index", len(subtitle_streams))),
                    codec_name=s.get("codec_name", "unknown"),
                    language=tags.get("language", "und"),
                    title=tags.get("title"),
                )
            )

    return MediaInfo(
        path=file_path,
        filename=filename,
        duration_sec=duration,
        width=width,
        height=height,
        aspect_ratio=dar,
        frame_rate=frame_rate,
        video_codec=video_codec,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
        chapters_count=len(chapters),
        size_bytes=size_bytes,
    )

async def probe_media_file(file_path: str) -> MediaInfo:
    data = await run_ffprobe_json(file_path)
    return parse_ffprobe_output(file_path, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_probe.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/probe.py tests/test_probe.py
git commit -m "feat: implement media prober and stream analyzer"
```

---

### Task 3: Transcoding Engine & Hardware Acceleration Command Builder

**Files:**
- Create: `src/dvdcompress/transcoder.py`
- Test: `tests/test_transcoder.py`

**Interfaces:**
- Produces:
  - `build_dvd_transcode_command(input_file: str, output_mpg: str, video_bitrate_kbps: int, audio_stream_idx: int, audio_channels: int, tv_standard: TVStandard, aspect_ratio: AspectRatio, use_gpu: bool) -> list[str]`
  - `build_bluray_transcode_command(...) -> list[str]`
  - `parse_ffmpeg_progress_line(line: str) -> dict`

- [ ] **Step 1: Write the failing tests for transcoder command generation**

```python
# tests/test_transcoder.py
import pytest
from dvdcompress.models import TVStandard, AspectRatio
from dvdcompress.transcoder import (
    build_dvd_transcode_command,
    build_bluray_transcode_command,
    parse_ffmpeg_progress_line,
)

def test_dvd_ntsc_command_structure():
    cmd = build_dvd_transcode_command(
        input_file="/media/input.mkv",
        output_mpg="/tmp/output.mpg",
        video_bitrate_kbps=4500,
        audio_stream_idx=1,
        audio_channels=6,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=False,
    )
    cmd_str = " ".join(cmd)
    assert "-target ntsc-dvd" in cmd_str
    assert "-b:v 4500k" in cmd_str
    assert "-aspect 16:9" in cmd_str
    assert "-c:a ac3" in cmd_str
    assert "-ar 48000" in cmd_str

def test_dvd_gpu_decode_flag():
    cmd = build_dvd_transcode_command(
        input_file="/media/input.mkv",
        output_mpg="/tmp/output.mpg",
        video_bitrate_kbps=4500,
        audio_stream_idx=1,
        audio_channels=2,
        tv_standard=TVStandard.PAL,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=True,
    )
    cmd_str = " ".join(cmd)
    assert "-hwaccel cuda" in cmd_str
    assert "-target pal-dvd" in cmd_str

def test_bluray_nvenc_command():
    cmd = build_bluray_transcode_command(
        input_file="/media/input.mkv",
        output_m2ts="/tmp/output.m2ts",
        video_bitrate_kbps=25000,
        audio_stream_idx=1,
        use_gpu=True,
    )
    cmd_str = " ".join(cmd)
    assert "h264_nvenc" in cmd_str
    assert "-b:v 25000k" in cmd_str

def test_parse_ffmpeg_progress():
    line = "frame= 1450 fps= 85.4 q=2.0 size=   45056kB time=00:01:00.45 bitrate=6104.2kbits/s speed=3.56x"
    progress = parse_ffmpeg_progress_line(line)
    assert progress["frame"] == 1450
    assert progress["fps"] == 85.4
    assert progress["speed"] == "3.56x"
    assert progress["time_sec"] == pytest.approx(60.45, 0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transcoder.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'dvdcompress.transcoder'`

- [ ] **Step 3: Implement `src/dvdcompress/transcoder.py`**

```python
# src/dvdcompress/transcoder.py
import re
from typing import List, Dict, Any, Optional
from dvdcompress.models import TVStandard, AspectRatio

def build_dvd_transcode_command(
    input_file: str,
    output_mpg: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 2,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    use_gpu: bool = False,
) -> List[str]:
    cmd = ["ffmpeg", "-y"]

    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])

    cmd.extend(["-i", input_file])

    # Video stream mapping and scaling
    cmd.extend(["-map", "0:v:0"])
    cmd.extend(["-map", f"0:{audio_stream_idx}"])

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target = "ntsc-dvd" if is_ntsc else "pal-dvd"
    scale_w, scale_h = (720, 480) if is_ntsc else (720, 576)

    # High quality MPEG-2 video encoding
    cmd.extend(["-target", target])
    cmd.extend(["-b:v", f"{video_bitrate_kbps}k"])
    cmd.extend(["-maxrate", "8500k", "-bufsize", "1835k"])
    cmd.extend(["-aspect", aspect_ratio.value])
    cmd.extend([
        "-vf",
        f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
    ])

    # Audio encoding
    cmd.extend(["-c:a", "ac3", "-ar", "48000"])
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "384k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_mpg)
    return cmd

def build_bluray_transcode_command(
    input_file: str,
    output_m2ts: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 6,
    use_gpu: bool = False,
) -> List[str]:
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd.extend(["-hwaccel", "cuda", "-i", input_file])
        cmd.extend(["-c:v", "h264_nvenc", "-profile:v", "high", "-level", "4.1"])
    else:
        cmd.extend(["-i", input_file])
        cmd.extend(["-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-bluray-compat", "1"])

    cmd.extend(["-map", "0:v:0", "-map", f"0:{audio_stream_idx}"])
    cmd.extend(["-b:v", f"{video_bitrate_kbps}k", "-maxrate", "35000k", "-bufsize", "30000k"])
    cmd.extend(["-g", "24", "-keyint_min", "1", "-bf", "3"])
    cmd.extend(["-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"])
    cmd.extend(["-c:a", "ac3", "-ar", "48000"])
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "448k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_m2ts)
    return cmd

def parse_ffmpeg_progress_line(line: str) -> Dict[str, Any]:
    res = {}
    frame_m = re.search(r"frame=\s*(\d+)", line)
    if frame_m:
        res["frame"] = int(frame_m.group(1))

    fps_m = re.search(r"fps=\s*([\d\.]+)", line)
    if fps_m:
        res["fps"] = float(fps_m.group(1))

    time_m = re.search(r"time=\s*(\d+):(\d+):([\d\.]+)", line)
    if time_m:
        h = int(time_m.group(1))
        m = int(time_m.group(2))
        s = float(time_m.group(3))
        res["time_sec"] = h * 3600 + m * 60 + s

    speed_m = re.search(r"speed=\s*([\d\.]+)x", line)
    if speed_m:
        res["speed"] = f"{speed_m.group(1)}x"

    return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transcoder.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/transcoder.py tests/test_transcoder.py
git commit -m "feat: implement transcoding engine and progress parser"
```

---

### Task 4: Disc Authoring (dvdauthor, tsMuxeR) & ISO Generation

**Files:**
- Create: `src/dvdcompress/authoring.py`
- Create: `src/dvdcompress/iso.py`
- Test: `tests/test_authoring.py`

**Interfaces:**
- Produces:
  - `generate_dvdauthor_xml(titles_mpg: list[str], chapters_sec: list[list[float]], menu_mode: MenuMode, tv_standard: TVStandard) -> str`
  - `generate_tsmuxer_meta(video_files: list[str]) -> str`
  - `build_genisoimage_command(dvd_author_dir: str, output_iso_path: str, volume_label: str) -> list[str]`
  - `build_xorriso_bd_command(bd_author_dir: str, output_iso_path: str, volume_label: str) -> list[str]`

- [ ] **Step 1: Write the failing tests for authoring and ISO generators**

```python
# tests/test_authoring.py
import pytest
from dvdcompress.models import MenuMode, TVStandard
from dvdcompress.authoring import generate_dvdauthor_xml, generate_tsmuxer_meta
from dvdcompress.iso import build_genisoimage_command, build_xorriso_bd_command

def test_dvdauthor_xml_single_title_autoplay():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0, 600.0]],
        menu_mode=MenuMode.AUTOPLAY,
        tv_standard=TVStandard.NTSC,
    )
    assert "<dvdauthor" in xml
    assert "<vob file=\"/tmp/title1.mpg\"" in xml
    assert "chapters=\"00:00:00.000,00:05:00.000,00:10:00.000\"" in xml

def test_dvdauthor_xml_multi_titles():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/ep1.mpg", "/tmp/ep2.mpg"],
        chapters_sec=[[0.0, 300.0], [0.0, 300.0]],
        menu_mode=MenuMode.AUTOPLAY,
        tv_standard=TVStandard.NTSC,
    )
    assert "<vob file=\"/tmp/ep1.mpg\"" in xml
    assert "<vob file=\"/tmp/ep2.mpg\"" in xml

def test_iso_commands():
    iso_cmd = build_genisoimage_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "-dvd-video" in iso_cmd
    assert "-udf" in iso_cmd
    assert "MY_MOVIE" in iso_cmd

    bd_cmd = build_xorriso_bd_command("/tmp/bd_author", "/output/bd.iso", "MY_BLURAY")
    assert "-udf" in bd_cmd
    assert "MY_BLURAY" in bd_cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_authoring.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `authoring.py` and `iso.py`**

```python
# src/dvdcompress/authoring.py
from typing import List
from dvdcompress.models import MenuMode, TVStandard

def format_chapter_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

def generate_dvdauthor_xml(
    titles_mpg: List[str],
    chapters_sec: List[List[float]],
    menu_mode: MenuMode = MenuMode.AUTOPLAY,
    tv_standard: TVStandard = TVStandard.NTSC,
) -> str:
    video_format = "ntsc" if tv_standard in (TVStandard.NTSC, TVStandard.AUTO) else "pal"
    
    xml_lines = [
        '<dvdauthor dest="VIDEO_TS">',
        '  <vmgm />',
        '  <titleset>',
        '    <titles>',
        f'      <video format="{video_format}" aspect="16:9" />',
        '      <audio format="ac3" channels="2" />',
    ]

    for idx, mpg in enumerate(titles_mpg):
        chaps = chapters_sec[idx] if idx < len(chapters_sec) and len(chapters_sec[idx]) > 0 else [0.0]
        chap_str = ",".join([format_chapter_time(c) for c in chaps])
        xml_lines.append(f'      <pgc>')
        xml_lines.append(f'        <vob file="{mpg}" chapters="{chap_str}" />')
        # Play next title or loop
        if idx < len(titles_mpg) - 1:
            xml_lines.append(f'        <post>jump title {idx + 2};</post>')
        else:
            xml_lines.append('        <post>jump title 1;</post>')
        xml_lines.append('      </pgc>')

    xml_lines.extend([
        '    </titles>',
        '  </titleset>',
        '</dvdauthor>'
    ])

    return "\n".join(xml_lines)

def generate_tsmuxer_meta(video_files: List[str]) -> str:
    meta_lines = ["MUXOPT --no-pcr-on-video-pid --new-audio-pes --blu-ray --vbr --custom-chapters=00:00:00.000"]
    for vf in video_files:
        meta_lines.append(f"V_MPEG4/ISO/AVC, \"{vf}\", fps=23.976, insertSEI, contSPS")
        meta_lines.append(f"A_AC3, \"{vf}\"")
    return "\n".join(meta_lines)
```

```python
# src/dvdcompress/iso.py
from typing import List

def build_genisoimage_command(author_dir: str, output_iso_path: str, volume_label: str = "DVD_DISC") -> List[str]:
    # Sanitized volume label (max 32 uppercase alphanumeric chars)
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "genisoimage",
        "-dvd-video",
        "-udf",
        "-V", clean_label,
        "-o", output_iso_path,
        author_dir,
    ]

def build_xorriso_bd_command(author_dir: str, output_iso_path: str, volume_label: str = "BD_DISC") -> List[str]:
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "xorriso",
        "-as", "mkisofs",
        "-iso-level", "3",
        "-udf",
        "-V", clean_label,
        "-o", output_iso_path,
        author_dir,
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_authoring.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/authoring.py src/dvdcompress/iso.py tests/test_authoring.py
git commit -m "feat: implement dvdauthor xml and ISO mastering command generators"
```

---

### Task 5: Optical Drive Scanner & Disc Burning Manager

**Files:**
- Create: `src/dvdcompress/burner.py`
- Test: `tests/test_burner.py`

**Interfaces:**
- Produces:
  - `scan_optical_drives() -> list[OpticalDrive]`
  - `build_burn_command(device_path: str, iso_path: str, speed: int, is_bluray: bool) -> list[str]`
  - `parse_burn_progress_line(line: str) -> dict`

- [ ] **Step 1: Write the failing tests for burner manager**

```python
# tests/test_burner.py
import pytest
from dvdcompress.burner import (
    build_burn_command,
    parse_burn_progress_line,
    parse_lsscsi_output,
)

SAMPLE_LSSCSI = """
[0:0:0:0]    disk    ATA      Samsung SSD 870  1B6Q  /dev/sda 
[1:0:0:0]    cd/dvd  HL-DT-ST BD-RE WH16NS40   1.05  /dev/sr0  /dev/sg0
"""

def test_parse_lsscsi_drives():
    drives = parse_lsscsi_output(SAMPLE_LSSCSI)
    assert len(drives) == 1
    assert drives[0].device_path == "/dev/sr0"
    assert drives[0].vendor == "HL-DT-ST"
    assert "WH16NS40" in drives[0].model

def test_build_dvd_burn_command():
    cmd = build_burn_command("/dev/sr0", "/output/disc.iso", speed=4, is_bluray=False)
    cmd_str = " ".join(cmd)
    assert "growisofs" in cmd_str
    assert "-dvd-compat" in cmd_str
    assert "-speed=4" in cmd_str
    assert "/dev/sr0=/output/disc.iso" in cmd_str

def test_build_bluray_burn_command():
    cmd = build_burn_command("/dev/sr0", "/output/disc.iso", speed=2, is_bluray=True)
    cmd_str = " ".join(cmd)
    assert "cdrskin" in cmd_str
    assert "dev=/dev/sr0" in cmd_str
    assert "speed=2" in cmd_str

def test_parse_growisofs_progress():
    line = " 143523840/4699979776 ( 3.1%) @3.9x, remaining 14:12 RBU 100.0% UBU   4.2%"
    prog = parse_burn_progress_line(line)
    assert prog["percent"] == 3.1
    assert prog["speed"] == "3.9x"
    assert prog["remaining"] == "14:12"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_burner.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dvdcompress/burner.py`**

```python
# src/dvdcompress/burner.py
import re
import os
import glob
import subprocess
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class OpticalDrive(BaseModel):
    device_path: str
    sg_device: Optional[str] = None
    vendor: str = "Generic"
    model: str = "Optical Writer"
    is_writable: bool = True
    media_status: str = "Ready"

def parse_lsscsi_output(output: str) -> List[OpticalDrive]:
    drives = []
    for line in output.strip().splitlines():
        if "cd/dvd" in line:
            parts = line.split()
            # Find /dev/sr* and /dev/sg*
            sr_dev = next((p for p in parts if p.startswith("/dev/sr")), None)
            sg_dev = next((p for p in parts if p.startswith("/dev/sg")), None)
            if sr_dev:
                vendor = parts[2] if len(parts) > 2 else "Generic"
                model = " ".join(parts[3:5]) if len(parts) > 4 else "Drive"
                drives.append(
                    OpticalDrive(
                        device_path=sr_dev,
                        sg_device=sg_dev,
                        vendor=vendor,
                        model=model,
                    )
                )
    return drives

def scan_optical_drives() -> List[OpticalDrive]:
    # Try lsscsi first
    try:
        res = subprocess.run(["lsscsi", "-g"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            drives = parse_lsscsi_output(res.stdout)
            if drives:
                return drives
    except Exception:
        pass

    # Fallback to checking /dev/sr*
    found = []
    for dev in sorted(glob.glob("/dev/sr*")):
        found.append(
            OpticalDrive(
                device_path=dev,
                vendor="Standard",
                model=os.path.basename(dev),
            )
        )
    return found

def build_burn_command(device_path: str, iso_path: str, speed: int = 4, is_bluray: bool = False) -> List[str]:
    if is_bluray:
        return [
            "cdrskin",
            "-v",
            f"dev={device_path}",
            f"speed={speed}",
            "gracetime=2",
            "-dao",
            iso_path,
        ]
    else:
        return [
            "growisofs",
            "-dvd-compat",
            f"-speed={speed}",
            f"-Z", f"{device_path}={iso_path}",
        ]

def parse_burn_progress_line(line: str) -> Dict[str, Any]:
    res = {}
    # Match growisofs percentage: " ( 3.1%) @3.9x, remaining 14:12"
    m = re.search(r"\(\s*([\d\.]+)%\)\s*@([\d\.]+)x.*?remaining\s*([\d:]+)", line)
    if m:
        res["percent"] = float(m.group(1))
        res["speed"] = f"{m.group(2)}x"
        res["remaining"] = m.group(3)
        return res

    # Match cdrskin progress: "Track 01:   25 of  450 MB written (fifo 100%)"
    m2 = re.search(r"(\d+)\s+of\s+(\d+)\s+MB written", line)
    if m2:
        written = float(m2.group(1))
        total = float(m2.group(2))
        res["percent"] = round((written / total) * 100.0, 1) if total > 0 else 0.0

    return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_burner.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/burner.py tests/test_burner.py
git commit -m "feat: implement optical drive discovery and burning engine"
```

---

### Task 6: Async Job Manager & WebSocket Telemetry

**Files:**
- Create: `src/dvdcompress/system_info.py`
- Create: `src/dvdcompress/job_manager.py`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- Produces:
  - `JobStage` (Enum: `IDLE`, `PROBING`, `TRANSCODING`, `AUTHORING`, `MASTERING_ISO`, `BURNING`, `COMPLETED`, `FAILED`, `CANCELLED`)
  - `JobProgress` (Model with stage, percent, fps, speed, eta, logs)
  - `JobManager` (Singleton orchestrator managing background tasks, cancellation, and broadcast)
  - `get_hardware_telemetry() -> dict`

- [ ] **Step 1: Write the failing tests for JobManager**

```python
# tests/test_job_manager.py
import pytest
import asyncio
from dvdcompress.job_manager import JobManager, JobStage
from dvdcompress.models import DiscType, TVStandard, AspectRatio, MenuMode, OutputMode

@pytest.mark.asyncio
async def test_job_manager_lifecycle():
    manager = JobManager()
    job_id = manager.create_job(
        input_files=["/media/test.mkv"],
        disc_type=DiscType.DVD5,
        output_mode=OutputMode.ISO_ONLY,
        output_name="test_movie",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        menu_mode=MenuMode.AUTOPLAY,
    )
    job = manager.get_job(job_id)
    assert job is not None
    assert job.stage == JobStage.IDLE
    assert job.job_id == job_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_job_manager.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `src/dvdcompress/system_info.py` and `src/dvdcompress/job_manager.py`**

```python
# src/dvdcompress/system_info.py
import shutil
import subprocess
from typing import Dict, Any

def get_hardware_telemetry() -> Dict[str, Any]:
    telemetry = {
        "gpu_available": False,
        "gpu_name": None,
        "gpu_utilization_percent": 0,
        "gpu_memory_used_mb": 0,
        "gpu_memory_total_mb": 0,
        "gpu_temp_c": 0,
    }

    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 5:
                    telemetry["gpu_available"] = True
                    telemetry["gpu_name"] = parts[0]
                    telemetry["gpu_utilization_percent"] = int(parts[1])
                    telemetry["gpu_memory_used_mb"] = int(parts[2])
                    telemetry["gpu_memory_total_mb"] = int(parts[3])
                    telemetry["gpu_temp_c"] = int(parts[4])
        except Exception:
            pass

    return telemetry
```

```python
# src/dvdcompress/job_manager.py
import uuid
import asyncio
import os
import shutil
from enum import Enum
from typing import List, Dict, Optional, Callable
from pydantic import BaseModel, Field
from dvdcompress.models import DiscType, TVStandard, AspectRatio, MenuMode, OutputMode
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.probe import probe_media_file
from dvdcompress.transcoder import build_dvd_transcode_command, build_bluray_transcode_command, parse_ffmpeg_progress_line
from dvdcompress.authoring import generate_dvdauthor_xml, generate_tsmuxer_meta
from dvdcompress.iso import build_genisoimage_command, build_xorriso_bd_command
from dvdcompress.burner import build_burn_command, parse_burn_progress_line

class JobStage(str, Enum):
    IDLE = "idle"
    PROBING = "probing"
    TRANSCODING = "transcoding"
    AUTHORING = "authoring"
    MASTERING_ISO = "mastering_iso"
    BURNING = "burning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Job(BaseModel):
    job_id: str
    stage: JobStage = JobStage.IDLE
    input_files: List[str]
    disc_type: DiscType
    output_mode: OutputMode
    output_name: str
    tv_standard: TVStandard
    aspect_ratio: AspectRatio
    menu_mode: MenuMode
    burner_device: Optional[str] = None
    burn_speed: int = 4
    use_gpu: bool = True
    
    current_file_idx: int = 0
    total_files: int = 1
    progress_percent: float = 0.0
    stage_percent: float = 0.0
    fps: float = 0.0
    speed: str = "1.0x"
    eta: str = "--:--"
    error_message: Optional[str] = None
    output_iso_path: Optional[str] = None
    logs: List[str] = []

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.listeners: Dict[str, List[asyncio.Queue]] = {}

    def create_job(
        self,
        input_files: List[str],
        disc_type: DiscType,
        output_mode: OutputMode,
        output_name: str,
        tv_standard: TVStandard = TVStandard.AUTO,
        aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
        menu_mode: MenuMode = MenuMode.AUTOPLAY,
        burner_device: Optional[str] = None,
        burn_speed: int = 4,
        use_gpu: bool = True,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        clean_name = "".join([c if c.isalnum() else "_" for c in output_name.strip()]) or f"disc_{job_id}"
        job = Job(
            job_id=job_id,
            input_files=input_files,
            disc_type=disc_type,
            output_mode=output_mode,
            output_name=clean_name,
            tv_standard=tv_standard,
            aspect_ratio=aspect_ratio,
            menu_mode=menu_mode,
            burner_device=burner_device,
            burn_speed=burn_speed,
            use_gpu=use_gpu,
            total_files=len(input_files),
        )
        self.jobs[job_id] = job
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    async def broadcast(self, job_id: str):
        job = self.get_job(job_id)
        if not job or job_id not in self.listeners:
            return
        data = job.model_dump()
        for q in self.listeners[job_id]:
            await q.put(data)

    def register_listener(self, job_id: str, queue: asyncio.Queue):
        if job_id not in self.listeners:
            self.listeners[job_id] = []
        self.listeners[job_id].append(queue)

    def unregister_listener(self, job_id: str, queue: asyncio.Queue):
        if job_id in self.listeners and queue in self.listeners[job_id]:
            self.listeners[job_id].remove(queue)

    def log(self, job_id: str, message: str):
        job = self.get_job(job_id)
        if job:
            job.logs.append(message)
            if len(job.logs) > 500:
                job.logs.pop(0)

    async def start_job(self, job_id: str, scratch_dir: str = "/tmp/dvdcompress", output_dir: str = "/output"):
        task = asyncio.create_task(self._run_pipeline(job_id, scratch_dir, output_dir))
        self.active_tasks[job_id] = task

    async def cancel_job(self, job_id: str):
        if job_id in self.active_tasks:
            self.active_tasks[job_id].cancel()
            job = self.get_job(job_id)
            if job:
                job.stage = JobStage.CANCELLED
                job.error_message = "Job cancelled by user"
                await self.broadcast(job_id)

    async def _run_pipeline(self, job_id: str, scratch_dir: str, output_dir: str):
        job = self.get_job(job_id)
        if not job:
            return

        work_dir = os.path.join(scratch_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        try:
            # 1. Probing
            job.stage = JobStage.PROBING
            self.log(job_id, f"Probing {len(job.input_files)} input files...")
            await self.broadcast(job_id)

            media_infos = []
            total_duration = 0.0
            for f in job.input_files:
                info = await probe_media_file(f)
                media_infos.append(info)
                total_duration += info.duration_sec

            # Calculate bit budget
            budget = calculate_bitrate_budget(
                total_duration_sec=total_duration,
                disc_type=job.disc_type,
                video_count=len(job.input_files),
            )
            self.log(job_id, f"Allocated video bitrate: {budget.video_bitrate_kbps} kbps (Disc usage: {budget.capacity_percent}%)")

            # 2. Transcoding
            job.stage = JobStage.TRANSCODING
            await self.broadcast(job_id)

            is_bluray = job.disc_type in (DiscType.BD25, DiscType.BD50)
            transcoded_files = []

            for idx, info in enumerate(media_infos):
                job.current_file_idx = idx + 1
                out_ext = ".m2ts" if is_bluray else ".mpg"
                out_file = os.path.join(work_dir, f"title_{idx+1}{out_ext}")
                transcoded_files.append(out_file)

                if is_bluray:
                    cmd = build_bluray_transcode_command(
                        input_file=info.path,
                        output_m2ts=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        use_gpu=job.use_gpu,
                    )
                else:
                    cmd = build_dvd_transcode_command(
                        input_file=info.path,
                        output_mpg=out_file,
                        video_bitrate_kbps=budget.video_bitrate_kbps,
                        tv_standard=job.tv_standard,
                        aspect_ratio=job.aspect_ratio,
                        use_gpu=job.use_gpu,
                    )

                self.log(job_id, f"Transcoding [{idx+1}/{len(media_infos)}]: {info.filename}")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace")
                    prog = parse_ffmpeg_progress_line(decoded)
                    if "frame" in prog:
                        job.fps = prog.get("fps", job.fps)
                        job.speed = prog.get("speed", job.speed)
                        if info.duration_sec > 0 and "time_sec" in prog:
                            file_pct = min(100.0, (prog["time_sec"] / info.duration_sec) * 100.0)
                            job.stage_percent = round(file_pct, 1)
                            overall_pct = ((idx + (file_pct / 100.0)) / len(media_infos)) * 60.0
                            job.progress_percent = round(overall_pct, 1)
                        await self.broadcast(job_id)

                await proc.wait()
                if proc.returncode != 0:
                    raise RuntimeError(f"Transcoding failed for {info.filename}")

            # 3. Authoring
            job.stage = JobStage.AUTHORING
            job.progress_percent = 70.0
            self.log(job_id, "Authoring disc structure...")
            await self.broadcast(job_id)

            author_dir = os.path.join(work_dir, "author")
            os.makedirs(author_dir, exist_ok=True)

            if is_bluray:
                meta_content = generate_tsmuxer_meta(transcoded_files)
                meta_path = os.path.join(work_dir, "tsmuxer.meta")
                with open(meta_path, "w") as mf:
                    mf.write(meta_content)
                proc = await asyncio.create_subprocess_exec("tsMuxeR", meta_path, author_dir)
                await proc.wait()
            else:
                xml_content = generate_dvdauthor_xml(
                    titles_mpg=transcoded_files,
                    chapters_sec=[[0.0, 300.0, 600.0, 900.0] for _ in transcoded_files],
                    menu_mode=job.menu_mode,
                    tv_standard=job.tv_standard,
                )
                xml_path = os.path.join(work_dir, "dvdauthor.xml")
                with open(xml_path, "w") as xf:
                    xf.write(xml_content)
                proc = await asyncio.create_subprocess_exec("dvdauthor", "-o", author_dir, "-x", xml_path)
                await proc.wait()

            # 4. ISO Creation
            job.stage = JobStage.MASTERING_ISO
            job.progress_percent = 85.0
            iso_path = os.path.join(output_dir, f"{job.output_name}.iso")
            job.output_iso_path = iso_path
            self.log(job_id, f"Building ISO: {iso_path}")
            await self.broadcast(job_id)

            if is_bluray:
                iso_cmd = build_xorriso_bd_command(author_dir, iso_path, job.output_name)
            else:
                iso_cmd = build_genisoimage_command(author_dir, iso_path, job.output_name)

            proc = await asyncio.create_subprocess_exec(*iso_cmd)
            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError("ISO creation failed")

            # 5. Burning (Optional)
            if job.output_mode in (OutputMode.BURN_DIRECT, OutputMode.AUTHOR_AND_BURN) and job.burner_device:
                job.stage = JobStage.BURNING
                self.log(job_id, f"Burning ISO to {job.burner_device} at {job.burn_speed}x...")
                await self.broadcast(job_id)
                burn_cmd = build_burn_command(job.burner_device, iso_path, speed=job.burn_speed, is_bluray=is_bluray)
                proc = await asyncio.create_subprocess_exec(
                    *burn_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace")
                    prog = parse_burn_progress_line(decoded)
                    if "percent" in prog:
                        job.stage_percent = prog["percent"]
                        job.progress_percent = 85.0 + (prog["percent"] * 0.15)
                        job.eta = prog.get("remaining", job.eta)
                        await self.broadcast(job_id)
                await proc.wait()

            job.stage = JobStage.COMPLETED
            job.progress_percent = 100.0
            self.log(job_id, "Job finished successfully!")
            await self.broadcast(job_id)

        except asyncio.CancelledError:
            job.stage = JobStage.CANCELLED
            self.log(job_id, "Job was cancelled.")
            await self.broadcast(job_id)
        except Exception as e:
            job.stage = JobStage.FAILED
            job.error_message = str(e)
            self.log(job_id, f"ERROR: {str(e)}")
            await self.broadcast(job_id)
        finally:
            # Clean scratch work dir
            shutil.rmtree(work_dir, ignore_errors=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_job_manager.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/system_info.py src/dvdcompress/job_manager.py tests/test_job_manager.py
git commit -m "feat: implement async job manager, system telemetry, and websocket broadcasting"
```

---

### Task 7: FastAPI Application Server & REST/WebSocket Endpoints

**Files:**
- Create: `src/dvdcompress/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces:
  - `GET /api/files?path=/media` (Browse filesystem video files)
  - `POST /api/probe` (Inspect video metadata)
  - `POST /api/calculate` (Calculate disc bit budget)
  - `GET /api/drives` (Scan optical writers)
  - `GET /api/system` (Hardware & GPU status)
  - `POST /api/jobs` (Create and start job)
  - `GET /api/jobs/{job_id}` (Get job status)
  - `POST /api/jobs/{job_id}/cancel` (Cancel job)
  - `POST /api/burn-iso` (Burn standalone ISO)
  - `WS /ws/jobs/{job_id}` (Real-time progress telemetry)

- [ ] **Step 1: Write the failing tests for API endpoints**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from dvdcompress.api import app

client = TestClient(app)

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_api_calculate():
    res = client.post("/api/calculate", json={
        "total_duration_sec": 7200,
        "disc_type": "dvd5",
        "audio_tracks_kbps": [192],
        "video_count": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["video_bitrate_kbps"] > 0
    assert data["target_capacity_mb"] == 4300.0

def test_api_drives():
    res = client.get("/api/drives")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_api_system():
    res = client.get("/api/system")
    assert res.status_code == 200
    data = res.json()
    assert "gpu_available" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dvdcompress/api.py`**

```python
# src/dvdcompress/api.py
import os
import glob
import asyncio
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from dvdcompress.models import DiscType, TVStandard, AspectRatio, MenuMode, OutputMode, BitrateBudget, MediaInfo
from dvdcompress.calculator import calculate_bitrate_budget
from dvdcompress.probe import probe_media_file
from dvdcompress.burner import scan_optical_drives, OpticalDrive, build_burn_command
from dvdcompress.system_info import get_hardware_telemetry
from dvdcompress.job_manager import JobManager

app = FastAPI(title="DVDCompress API", version="1.0.0")
job_manager = JobManager()

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/output")
SCRATCH_DIR = os.environ.get("SCRATCH_DIR", "/tmp/dvdcompress")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".ts", ".m2ts", ".webm", ".flv", ".mpg", ".vob"}

class CalculateRequest(BaseModel):
    total_duration_sec: float
    disc_type: DiscType
    audio_tracks_kbps: List[int] = [192]
    video_count: int = 1

class ProbeRequest(BaseModel):
    file_path: str

class CreateJobRequest(BaseModel):
    input_files: List[str]
    disc_type: DiscType
    output_mode: OutputMode
    output_name: str
    tv_standard: TVStandard = TVStandard.AUTO
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9
    menu_mode: MenuMode = MenuMode.AUTOPLAY
    burner_device: Optional[str] = None
    burn_speed: int = 4
    use_gpu: bool = True

class BurnIsoRequest(BaseModel):
    iso_path: str
    device_path: str
    burn_speed: int = 4
    is_bluray: bool = False

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "DVDCompress"}

@app.get("/api/files")
def list_files(path: Optional[str] = None):
    target = path or MEDIA_DIR
    if not os.path.exists(target):
        return {"current_path": target, "parent_path": None, "directories": [], "files": []}

    entries = os.listdir(target)
    dirs = []
    files = []

    for e in sorted(entries):
        if e.startswith("."):
            continue
        full = os.path.join(target, e)
        if os.path.isdir(full):
            dirs.append({"name": e, "path": full})
        elif os.path.isfile(full):
            ext = os.path.splitext(e)[1].lower()
            if ext in VIDEO_EXTENSIONS or ext == ".iso":
                files.append({
                    "name": e,
                    "path": full,
                    "size_bytes": os.path.getsize(full),
                    "is_video": ext in VIDEO_EXTENSIONS,
                    "is_iso": ext == ".iso",
                })

    parent = os.path.dirname(target) if target != MEDIA_DIR and target != "/" else None
    return {
        "current_path": target,
        "parent_path": parent,
        "directories": dirs,
        "files": files,
    }

@app.post("/api/probe", response_model=MediaInfo)
async def probe_file(req: ProbeRequest):
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        return await probe_media_file(req.file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calculate", response_model=BitrateBudget)
def calculate_budget(req: CalculateRequest):
    return calculate_bitrate_budget(
        total_duration_sec=req.total_duration_sec,
        disc_type=req.disc_type,
        audio_tracks_kbps=req.audio_tracks_kbps,
        video_count=req.video_count,
    )

@app.get("/api/drives", response_model=List[OpticalDrive])
def list_drives():
    return scan_optical_drives()

@app.get("/api/system")
def get_system():
    return get_hardware_telemetry()

@app.post("/api/jobs")
async def create_job(req: CreateJobRequest):
    for f in req.input_files:
        if not os.path.exists(f):
            raise HTTPException(status_code=400, detail=f"Input file does not exist: {f}")

    job_id = job_manager.create_job(
        input_files=req.input_files,
        disc_type=req.disc_type,
        output_mode=req.output_mode,
        output_name=req.output_name,
        tv_standard=req.tv_standard,
        aspect_ratio=req.aspect_ratio,
        menu_mode=req.menu_mode,
        burner_device=req.burner_device,
        burn_speed=req.burn_speed,
        use_gpu=req.use_gpu,
    )
    await job_manager.start_job(job_id, scratch_dir=SCRATCH_DIR, output_dir=OUTPUT_DIR)
    return {"job_id": job_id, "status": "started"}

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    await job_manager.cancel_job(job_id)
    return {"status": "cancelled"}

@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    queue = asyncio.Queue()
    job_manager.register_listener(job_id, queue)
    
    # Send initial state
    job = job_manager.get_job(job_id)
    if job:
        await websocket.send_json(job.model_dump())

    try:
        while True:
            data = await queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        job_manager.unregister_listener(job_id, queue)
    except Exception:
        job_manager.unregister_listener(job_id, queue)

# Serve static web frontend
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/api.py tests/test_api.py
git commit -m "feat: implement FastAPI endpoints and static file mounts"
```

---

### Task 8: Modern Responsive Web User Interface

**Files:**
- Create: `src/dvdcompress/static/index.html`
- Create: `src/dvdcompress/static/css/style.css`
- Create: `src/dvdcompress/static/js/app.js`

**Interfaces:**
- Interactive directory browser with instant media info probing
- Multi-video queue with drag-and-drop / ordering
- Dynamic capacity & bitrate allocation gauge
- Multi-phase live pipeline tracker with WebSockets
- Dedicated ISO Burner tab and hardware telemetry bar

- [ ] **Step 1: Create `src/dvdcompress/static/css/style.css`** (clean, modern dark UI styling, zero cliché gradient bloat, crisp typography, fluid responsiveness).
- [ ] **Step 2: Create `src/dvdcompress/static/index.html`** with semantic layout, disc configurator, project playlist, progress telemetry modal/view, and drive controls.
- [ ] **Step 3: Create `src/dvdcompress/static/js/app.js`** implementing state management, REST calls, WebSocket subscriber, and capacity math updates.
- [ ] **Step 4: Verify static assets are served and rendered properly via FastAPI test client**.
- [ ] **Step 5: Commit**

```bash
git add src/dvdcompress/static/
git commit -m "feat: implement modern web user interface"
```

---

### Task 9: Docker Containerization, Multi-Stage Build & Entrypoint

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `entrypoint.sh`
- Create: `README.md`

**Interfaces:**
- Docker image build with NVIDIA CUDA 12.4 + FFmpeg + dvdauthor + tsMuxeR + growisofs + cdrskin + xorriso.
- Entrypoint permissions check and FastAPI server launch.
- Comprehensive user documentation for Docker CLI, Docker Compose, Unraid, and TrueNAS.

- [ ] **Step 1: Create `entrypoint.sh`**

```bash
#!/bin/bash
set -e

echo "=== DVDCompress Starting ==="
echo "Python: $(python3 --version)"
echo "FFmpeg: $(ffmpeg -version | head -n 1)"
echo "dvdauthor: $(dvdauthor --version 2>&1 | head -n 1 || echo 'Installed')"
echo "growisofs: $(growisofs --version 2>&1 | head -n 1 || echo 'Installed')"

# Verify GPU access
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU Detected:"
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || echo "NVIDIA SMI failed"
else
    echo "Running in CPU-only mode."
fi

exec uvicorn dvdcompress.api:app --host 0.0.0.0 --port 8080
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies, optical burning tools, and authoring utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-setuptools \
    ffmpeg \
    dvdauthor \
    genisoimage \
    dvd+rw-tools \
    cdrskin \
    xorriso \
    wodim \
    lsscsi \
    sg3-utils \
    pciutils \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install tsMuxeR for Blu-ray BDMV authoring
RUN curl -L -o /tmp/tsmuxer.tar.gz https://github.com/justdan96/tsMuxer/releases/download/nightly-2024-01-01-02-10-34/tsMuxeR-2.6.12-linux.tar.gz \
    && tar -xzf /tmp/tsmuxer.tar.gz -C /usr/local/bin/ tsMuxeR || true \
    && rm -f /tmp/tsmuxer.tar.gz

WORKDIR /app

# Copy application files
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Install Python requirements
RUN pip3 install --no-cache-dir -e /app

EXPOSE 8080

VOLUME ["/media", "/output", "/config", "/tmp/dvdcompress"]

ENTRYPOINT ["/app/entrypoint.sh"]
```

- [ ] **Step 3: Create `docker-compose.yml` and `README.md`**
- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml entrypoint.sh README.md
git commit -m "feat: add Dockerfile, compose config, entrypoint, and documentation"
```

---

### Task 10: End-to-End Verification & Integration Suite

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Runs synthetic video creation, probes metadata, calculates bitrate budget, creates DVD-Video structure, masters ISO, and validates ISO file headers.

- [ ] **Step 1: Write `tests/test_e2e.py`**
- [ ] **Step 2: Run all unit and integration tests**

Run: `pytest tests/ -v`  
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add comprehensive end-to-end test pipeline"
```
