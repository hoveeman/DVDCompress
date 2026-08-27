# DVDCompress

<div align="center">

**Hardware-Accelerated DVD-Video & Blu-ray Transcoding, Authoring, and Burning in Docker**

[![Docker Pulls](https://img.shields.io/docker/pulls/hovee/dvdcompress)](https://hub.docker.com/r/hovee/dvdcompress)
[![Docker Image Size](https://img.shields.io/docker/image-size/hovee/dvdcompress)](https://hub.docker.com/r/hovee/dvdcompress)
[![CUDA Version](https://img.shields.io/badge/CUDA-12.4.1-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-209%20passed%20%7C%20100%25-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Features](#-features) • [Quick Start](#-quick-start) • [Deployment](#-deployment-guides) • [Hardware Acceleration](#-hardware-acceleration) • [Optical Burning](#-optical-drive-pass-through) • [API Reference](#-rest-api--websocket-reference) • [Local Development](#-local-development--testing)

</div>

---

## 📖 Overview

**DVDCompress** is an open-source, self-hosted web application that transforms arbitrary digital video files (`.mp4`, `.mkv`, `.avi`, `.mov`, `.ts`, `.webm`, etc.) into 100% standard-compliant, standalone-playable **DVD-Video** (`VIDEO_TS`) and **Blu-ray** (`BDMV`) physical optical discs or master ISO images.

Equipped with a real-time mathematical bitrate budget calculator, ultra-fast zero-copy GPU HDR10 / Dolby Vision tone-mapping (300+ FPS), interactive DVD menu authoring, multi-audio and subtitle preservation, automated DVD-9 seamless layer break calculation, direct optical drive burning, and a modern responsive web interface, DVDCompress eliminates the complexity of optical authoring on home servers, Unraid, TrueNAS, and NAS systems.

---

## ✨ Features

### 🔊 Multi-Audio Track Selection & Smart Audio Rules
- **Interactive Audio Selection:** Individually select, deselect, and preview audio streams per title with channel layout, format, language tags, and bitrate indicators.
- **Smart Audio Priority Defaults:** Configurable smart audio rules (persisted in `/config/settings.json`):
  - Language priority list matching (e.g. `en, eng, ja, jpn`).
  - Preference for multi-channel surround sound (5.1 / 7.1) over stereo downmixes.
  - Maximum audio tracks per title constraint.
  - Keep all tracks vs Keep only default/first track modes.
- **Standard-Compliant Audio Multiplexing:** Authors up to 8 AC3 audio streams on DVD-Video (`dvdauthor.xml`) and full multi-audio tracks on Blu-ray (`tsMuxeR`), complete with language codes and seamless remote control audio track switching.
- **Multi-Track Bitrate Budgeting:** Bitrate calculator automatically accounts for multi-audio allocations to guarantee the disc never overflows.

### ⚡ Ultra-Fast GPU HDR10 & Dolby Vision Tone-Mapping (300+ FPS)
- **Zero-Copy Hardware Pipeline:** Leverages `jellyfin-ffmpeg` with native `tonemap_cuda` and `scale_cuda` hardware filters on NVIDIA GPUs.
- **Hable Filmic Color Adaptation:** Converts BT.2020 PQ/HLG HDR10 and Dolby Vision to Rec.601 (DVD) or Rec.709 (Blu-ray) SDR without washed-out colors or blown-out dynamic range.
- **2-Phase GPU Intermediate Architecture:** Streams high-speed tone-mapped intermediates with instant cleanup after encoding.

### 📺 Interactive DVD Title Menus & Auto-Play Navigation
- **Interactive Title Menus:** Automatically generates DVD-Video root menus with dynamic button highlights rendered via `spumux` subpicture overlays.
- **Navigation Modes:** Choose between **Interactive Menu** (with "Play All" and individual episode buttons) or **Auto-Play Directly** (starts immediately on disc insert).
- **Flexible End Actions:** Return to the title menu upon playback completion or auto-play the next episode in sequence.
- **Remote Button Jumping:** Supports the DVD remote "Menu" button during playback via VTSM root menu bridges.
- **Master Palette Color Mapping:** Merges menu button highlight palettes with subtitle subpictures into a unified 16-color table to eliminate `dvdauthor color map full` errors.

### 💬 Subtitle Preservation (PGS Bitmap & SRT Text)
- **Blu-ray PGS Bitmap Conversion:** High-fidelity conversion of PGS bitmap subtitles to DVD subpictures (`dvdsub`) with 4-color quantization and PTS timestamp alignment.
- **SRT Text Subtitle Rendering:** Automatically renders text subtitles into DVD subpictures using FreeType font styling.
- **Multi-Track Remote Selection:** Multiplexes up to 32 subtitle streams into DVD-Video and Blu-ray discs with language tags and remote control subtitle toggle support.

### 📐 Dynamic Aspect Ratio Preservation
- **No Squished or Stretched Video:** Automatically calculates native Source Aspect Ratio (SAR/DAR) and applies precision letterboxing or pillarboxing (`pad` filter).
- **16:9 Anamorphic Widescreen & 4:3 Fullscreen:** Fully compliant NTSC (720×480 @ 29.97fps) and PAL (720×576 @ 25fps) framing.

### ⏭️ Full-Movie Chapters & Markers
- **Marker Extraction:** Extracts existing embedded chapter markers from MKV/MP4 files or automatically generates 5-minute interval chapters across the full duration of each title.

### 🔍 1-Minute Video & ISO Sample Preview Generator
- **Instant Test Previews:** Generate a 1-minute `.mp4` video sample or a playable mini ISO image in seconds to verify video quality, audio synchronization, aspect ratio, and subtitle rendering before committing to a full multi-hour burn.

### 🚀 Blu-ray Direct Stream Passthrough
- **Lossless Stream Copying:** When source video and audio already adhere to Blu-ray / BDMV standards (H.264 High@L4.1 / HEVC UHD and AC3/DTS), DVDCompress bypasses transcoding completely for near-instant ISO mastering.

### 🎯 Automated DVD-9 Seamless Layer Break Calculation
- **Deep Filesystem & IFO Parsing:** Scans ISO9660 directory structures and DVD-Video IFO Cell Address Tables (`VTS_C_ADT`) to locate the optimal 16-sector ECC-aligned chapter/cell layer transition point ($L_0 \ge L_1$).
- **Optical Laser Transition Injection:** Passes `-use-the-force-luke=break:<sector>` to `growisofs` and streams live layer break transition telemetry to prevent playback stutter on standalone DVD players.

### 🔥 Direct Optical Disc Burning & Standalone ISO Burner
- **Hardware Drive Discovery:** Auto-detects SCSI/SATA/USB optical drives (`/dev/sr*`, `/dev/sg*`) with media status queries and tray inspection.
- **Burn Speed Control & Underrun Protection:** Integrated buffer underrun protection via `growisofs` and `cdrskin`/`xorriso`.
- **Standalone ISO Burner Tab:** Directly burn existing ISO images to optical media with custom write speeds (2x, 4x, 8x, MAX).

### 🧮 Dynamic Bitrate Budgeting Engine & Complexity Sampling
- **Dynamic Bitrate Budgeting:** Mathematically calculates optimal video and audio bitrates across $N$ inputs with precision filesystem overhead allocation (UDF/ISO 9660 + MPEG multiplexing factors):
  - **DVD-5 (Single Layer):** 4.30 GiB target budget (~4,300 MB)
  - **DVD-9 (Dual Layer):** 7.85 GiB target budget (~7,850 MB)
  - **BD-25 (Single Layer Blu-ray):** 23.00 GiB target budget (~23,000 MB)
  - **BD-50 (Dual Layer Blu-ray):** 46.00 GiB target budget (~46,000 MB)
  - **BD-66 (Dual Layer UHD):** 61.50 GiB target budget (~61,500 MB)
  - **BD-100 (Triple Layer BDXL):** 92.00 GiB target budget (~92,000 MB)
  - **BD-128 (Quad Layer BDXL):** 118.00 GiB target budget (~118,000 MB)
- **Fast Sample Complexity Analysis:** 3-point sample encoder estimating real-world VBR bitrates.
- **Smart Disc Recommendations:** Dynamic UI widget suggesting Single-Layer vs Dual-Layer media with a 1-click format switcher.

### 📋 Async Job Queue, Concurrency Slots, & Persistent History
- **Parallel Concurrency Slots:** Configurable concurrent worker slots (1 to 4 parallel jobs) with FIFO queue scheduling.
- **Pause, Resume, & Cancel:** Live job control using process signals (`SIGSTOP`/`SIGCONT`).
- **Persistent State:** Saves queue, application settings, and job history across container restarts (`/config/settings.json`, `/config/jobs.json`).
- **Job History Management:** Sortable history table with duration, output size, pagination, one-click **Retry** for failed jobs, and **Edit** to reload previous configurations.

### 🌐 Modern Real-Time Web Interface & Telemetry
- **Zero-Bloat Frontend:** Pure HTML5, ES6 JavaScript, and CSS3 dark-mode design system (no React or external CDNs required).
- **Live Hardware Telemetry:** WebSocket stream reporting real-time CPU %, RAM %, GPU %, VRAM usage, GPU temperature, encoding FPS, speed multiplier (e.g. `4.09x`), and ETA.

---

## 🏗 Architecture

```
+---------------------------------------------------------------------------------------+
|                                    Docker Container                                   |
|                                                                                       |
|  +---------------------------+     +-----------------------------------------------+  |
|  |     Modern Web UI         | <-> |       FastAPI Application Server (Python)     |  |
|  |  (HTML5 / Vanilla ES6)    |     |  - REST Endpoints & WebSocket Broadcasting    |  |
|  |  - Real-Time Telemetry    |     |  - Concurrency Queue Scheduler (FIFO)         |  |
|  |  - Capacity & VBR Gauges  |     |  - Settings & Job History JSON Persistence    |  |
|  |  - Audio & Subtitle Setup |     +-----------------------------------------------+  |
|  +---------------------------+                             |                          |
|                                                            |                          |
|           +------------------------------------------------+                          |
|           |                                                                           |
|           v (Orchestrated Pipelines)                                                  |
|  +--------------------+  +--------------------+  +------------------+  +-----------+  |
|  | Transcoding        |  | Menu & Subtitles   |  | Disc Authoring   |  | Burning   |  |
|  | - Jellyfin FFmpeg  |  | - Menu Generator   |  | - dvdauthor      |  | - growiso |  |
|  | - NVDEC / NVENC    |  | - spumux Pipeline  |  | - tsMuxeR        |  | - cdrskin |  |
|  | - tonemap_cuda     |  | - PGS Quantizer    |  | - xorriso        |  | - xorriso |  |
|  | - CPU Fallback     |  | - SRT Subtitles    |  | - Layer Break    |  | - lsscsi  |  |
|  +--------------------+  +--------------------+  +------------------+  +-----------+  |
+---------------------------------------------------------------------------------------+
       |                                   |                                |
       v (Volume Mounts)                   v (GPU Passthrough)              v (Device Pass)
   /media  (Source Videos)              --gpus all                      /dev/sr0, /dev/sg0
   /output (Authored ISOs)             (NVIDIA Driver Capabilities)      (Optical Writer)
   /config (App Settings & Queue)
   /tmp/dvdcompress (Working Scratch)
```

---

## 🚀 Quick Start

### 1. Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
services:
  dvdcompress:
    image: hovee/dvdcompress:latest
    container_name: dvdcompress
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - TZ=America/New_York
      - DVDCOMPRESS_LOG_LEVEL=INFO
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all,video,compute,utility
    volumes:
      # Source media directory (mount read-only for safety)
      - /path/to/your/media:/media:ro
      # Authored ISO files output directory
      - /path/to/your/output:/output:rw
      # Persistent app settings and job history
      - /path/to/your/config:/config:rw
      # Scratch directory for intermediate transcoding and authoring
      - /path/to/your/temp:/tmp/dvdcompress:rw
    devices:
      # Optical disc writer block device and SCSI generic pass-through
      - /dev/sr0:/dev/sr0
      - /dev/sg0:/dev/sg0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu, video, compute, utility]
```

Launch the container:
```bash
docker compose up -d
```

Open your browser and navigate to: **`http://<your-server-ip>:8080`**

---

### 2. Docker CLI

#### GPU-Accelerated Mode (NVIDIA)
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --gpus all \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/media:/media:ro \
  -v /mnt/dvd_output:/output:rw \
  -v /mnt/appdata/dvdcompress:/config:rw \
  -v /tmp/dvdcompress:/tmp/dvdcompress:rw \
  -e TZ=UTC \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all,video,compute,utility \
  hovee/dvdcompress:latest
```

#### CPU-Only Mode
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --device /dev/sr0:/dev/sr0 \
  --device /dev/sg0:/dev/sg0 \
  -p 8080:8080 \
  -v /mnt/media:/media:ro \
  -v /mnt/dvd_output:/output:rw \
  -v /mnt/appdata/dvdcompress:/config:rw \
  -v /tmp/dvdcompress:/tmp/dvdcompress:rw \
  -e TZ=UTC \
  hovee/dvdcompress:latest
```

---

## 🖥 Deployment Guides

### Unraid OS
1. Install the **NVIDIA Driver** plugin from Unraid Community Applications (if using an NVIDIA GPU).
2. Install the **DVDCompress** Docker container via Community Applications or load `templates/DVDCompress.xml`:
   - **Repository:** `hovee/dvdcompress:latest`
   - **WebUI:** `http://[IP]:[PORT:8080]`
   - **Port:** `8080` $\rightarrow$ `8080`
   - **Path 1 (Media):** `/mnt/user/Media` $\rightarrow$ `/media` *(Read-only)*
   - **Path 2 (Output):** `/mnt/user/Media/dvd_output` $\rightarrow$ `/output` *(Read/Write)*
   - **Path 3 (Config):** `/mnt/user/appdata/dvdcompress` $\rightarrow$ `/config` *(Read/Write)*
   - **Path 4 (Scratch Temp):** `/mnt/user/appdata/dvdcompress/working` $\rightarrow$ `/tmp/dvdcompress` *(Read/Write)*
   - **Device 1:** `/dev/sr0` $\rightarrow$ `/dev/sr0`
   - **Device 2:** `/dev/sg0` $\rightarrow$ `/dev/sg0`
   - **Extra Parameters:** `--gpus all --device /dev/sr0:/dev/sr0 --device /dev/sg0:/dev/sg0`
   - **Variables:** `NVIDIA_VISIBLE_DEVICES` = `all`, `NVIDIA_DRIVER_CAPABILITIES` = `all,video,compute,utility`

### TrueNAS SCALE
1. Navigate to **Apps** $\rightarrow$ **Launch Docker Image** (or Custom App).
2. Set Image: `hovee/dvdcompress:latest`.
3. Set Port Forwarding: Host Port `8080` $\rightarrow$ Container Port `8080`.
4. Configure Host Path Storage Volumes for `/media`, `/output`, `/config`, and `/tmp/dvdcompress`.
5. Under **GPU Resource Allocation**, assign 1 NVIDIA GPU.
6. Under **Device Passthrough**, pass `/dev/sr0` and `/dev/sg0`.

---

## ⚡ Hardware Acceleration

DVDCompress utilizes `jellyfin-ffmpeg` with CUDA, NVDEC, and NVENC hardware acceleration:

| Transcoding Stage | NVIDIA GPU (`--gpus all`) | CPU Fallback |
| :--- | :--- | :--- |
| **Decode Acceleration** | Hardware NVDEC (`-hwaccel cuda`) | Multi-threaded Software |
| **4K HDR Tone-Mapping** | Zero-copy `tonemap_cuda` + `scale_cuda` (300+ FPS) | Filmic color matrix conversion |
| **DVD-Video Transcode** | NVDEC decode + MPEG-2 Video Encoder | `mpeg2video` Software Encoder |
| **Blu-ray Transcode** | `h264_nvenc` / `hevc_nvenc` Hardware Encoder | `libx264` / `libx265` Software Encoder |
| **Audio Transcode** | Multi-channel AC3 encoder (Stereo / 5.1 Surround) | Multi-channel AC3 encoder |

---

## 💿 Optical Drive Pass-Through

To enable physical disc burning from inside Docker, pass both the optical block device (`/dev/sr*`) and the SCSI generic device (`/dev/sg*`):

1. **Identify optical drives on the host:**
   ```bash
   lsscsi -k
   # Example output: [2:0:0:0] cd/dvd ASUS BW-16D1HT /dev/sr0 /dev/sg0
   ```

2. **Verify device permissions:**
   ```bash
   ls -l /dev/sr0 /dev/sg0
   ```

3. **Pass devices in Docker Compose:**
   ```yaml
   devices:
     - /dev/sr0:/dev/sr0
     - /dev/sg0:/dev/sg0
   ```

### Dual-Layer (DVD-9) Automated Layer Break & Burning

When burning DVD-9 dual-layer media (DVD+R DL / DVD-R DL), DVDCompress automatically:
1. **Locates Chapter Boundaries:** Scans the disc filesystem and IFO navigation tables to place the physical layer break at an exact Chapter/Cell start sector with closed GOP sequence headers.
2. **Enforces Physical Constraints:** Ensures Layer 0 holds $\ge 50\%$ of data ($L_0 \ge L_1$) aligned to a 32 KB (16-sector) ECC block.
3. **Programs Optical Hardware:** Injects `-use-the-force-luke=break:<sector>` into `growisofs`.
4. **Streams Live Transition Telemetry:** Alerts the live log terminal the exact moment the drive laser refocuses onto Layer 1.

---

## 📊 Disc Target Capacities & Sector Budgeting

| Disc Format | Physical Type | Target Capacity | Usable Sector Budget | Max Video Bitrate | Audio Format | Video Format |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| **DVD-5** | Single Layer | 4.7 GB | **4,300 MB** | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **DVD-9** | Dual Layer | 8.5 GB | **7,850 MB** | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **BD-25** | Single Layer | 25.0 GB | **23,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 High@L4.1 (1080p) |
| **BD-50** | Dual Layer | 50.0 GB | **46,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 High@L4.1 (1080p) |
| **BD-66** | Dual Layer UHD | 66.0 GB | **61,500 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC UHD-BD |
| **BD-100** | Triple Layer BDXL | 100.0 GB | **92,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |
| **BD-128** | Quad Layer BDXL | 128.0 GB | **118,000 MB** | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |

> **Safe Outer-Edge Margins:** DVDCompress intentionally targets ~4,300 MB on DVD-5 and ~7,850 MB on DVD-9 to stay safely away from the outer 10% edge of recordable media where dye thinning causes laser tracking errors on older players.

---

## 📡 REST API & WebSocket Reference

DVDCompress exposes a comprehensive REST and WebSocket API:

### System & Telemetry
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | `GET` | Application health check |
| `/api/version` | `GET` | Current application version |
| `/api/system` | `GET` | Live CPU, RAM, and GPU telemetry |
| `/api/settings` | `GET` | Current application settings (concurrency slots, smart audio rules) |
| `/api/settings` | `POST` | Update application settings |

### File Browser & Media Analysis
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/files` | `GET` | Browse video and ISO files in `/media` |
| `/api/probe` | `POST` | FFprobe media analysis (codecs, audio tracks, subtitles, chapters, HDR) |
| `/api/calculate` | `POST` | Dynamic bitrate budgeting calculation based on duration & disc target |
| `/api/analyze-complexity` | `POST` | Run 3-point sample complexity analysis for real-world VBR estimation |
| `/api/drives` | `GET` | Scan host system for optical drives and query disc media presence |

### Job Orchestration & Previews
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/jobs` | `POST` | Create and enqueue a transcoding/authoring/burning job |
| `/api/jobs` | `GET` | List active, queued, and historical jobs |
| `/api/jobs/{job_id}` | `GET` | Get status and progress telemetry for a specific job |
| `/api/jobs/{job_id}/pause` | `POST` | Pause an active job via `SIGSTOP` |
| `/api/jobs/{job_id}/resume` | `POST` | Resume a paused job via `SIGCONT` |
| `/api/jobs/{job_id}/cancel` | `POST` | Cancel an in-progress or queued job |
| `/api/jobs/{job_id}/retry` | `POST` | Re-queue a failed or cancelled job with original settings |
| `/api/jobs/{job_id}` | `DELETE` | Remove a job from history |
| `/api/jobs` | `DELETE` | Clear all completed, failed, and cancelled jobs from history |
| `/api/jobs/clear-history` | `POST` | Alternative endpoint to clear all job history |
| `/api/preview` | `POST` | Generate a 1-minute video sample (`.mp4`) or mini ISO preview |
| `/api/burn-iso` | `POST` | Burn a pre-existing ISO directly to an optical drive |
| `/ws/jobs/{job_id}` | `WS` | Real-time WebSocket streaming progress, ETA, and live log output |

---

## 🛠 Local Development & Testing

```bash
# Clone the repository
git clone https://github.com/hoveeman/DVDCompress.git
cd DVDCompress

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run full automated test suite (209 tests)
pytest tests/ -v

# Run local development server with hot-reload
uvicorn dvdcompress.api:app --host 127.0.0.1 --port 8080 --reload
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
