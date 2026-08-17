# DVDCompress

<div align="center">

**Hardware-Accelerated DVD-Video & Blu-ray Transcoding, Authoring, and Burning in Docker**

[![Docker Pulls](https://img.shields.io/docker/pulls/hovee/dvdcompress)](https://hub.docker.com/r/hovee/dvdcompress)
[![Docker Image Size](https://img.shields.io/docker/image-size/hovee/dvdcompress)](https://hub.docker.com/r/hovee/dvdcompress)
[![CUDA Version](https://img.shields.io/badge/CUDA-12.4.1-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[Features](#-features) • [Quick Start](#-quick-start) • [Deployment](#-deployment-guides) • [Hardware Acceleration](#-hardware-acceleration) • [Optical Burning](#-optical-drive-pass-through) • [API Reference](#-rest-api--websocket-reference)

</div>

---

## 📖 Overview

**DVDCompress** is an open-source, self-hosted web application that transforms arbitrary modern video files (`.mp4`, `.mkv`, `.avi`, `.mov`, `.ts`, `.webm`, etc.) into 100% standard-compliant, standalone-playable **DVD-Video** (`VIDEO_TS`) and **Blu-ray** (`BDMV`) physical discs or ISO images.

Equipped with a real-time mathematical bitrate budget calculator, NVIDIA GPU decode/encode acceleration, automatic optical drive discovery, pause/resume queue management, and a modern responsive web interface, DVDCompress eliminates the complexity of optical authoring on home servers, Unraid, TrueNAS, and NAS systems.

---

## ✨ Features

- 🎞️ **Universal Video Ingest:** Accepts single videos or multi-episode season playlists in any container format, video codec (H.264, HEVC, AV1, VP9, MPEG-4), and audio codec (AC3, AAC, DTS, TrueHD, FLAC).
- 🧮 **Dynamic Bitrate Budgeting Engine:** Calculates optimal video and audio bitrates across $N$ inputs with precision filesystem overhead allocation (UDF/ISO 9660 + MPEG multiplexing factors) to guarantee disc fit without overflow:
  - **DVD-5 (Single Layer):** 4.30 GiB target budget (~4,300 MB)
  - **DVD-9 (Dual Layer):** 7.85 GiB target budget (~7,850 MB)
  - **BD-25 (Single Layer Blu-ray):** 23.00 GiB target budget (~23,000 MB)
  - **BD-50 (Dual Layer Blu-ray):** 46.00 GiB target budget (~46,000 MB)
  - **BD-66 (Dual Layer UHD):** 61.50 GiB target budget (~61,500 MB)
  - **BD-100 (Triple Layer BDXL):** 92.00 GiB target budget (~92,000 MB)
  - **BD-128 (Quad Layer BDXL):** 118.00 GiB target budget (~118,000 MB)
- 📀 **Standard-Compliant Authoring:**
  - **DVD-Video:** MPEG-2 video (NTSC 720×480 @ 29.97fps / PAL 720×576 @ 25fps), 48kHz AC3 audio, `dvdauthor` VTS titlesets, 16:9 widescreen anamorphic / 4:3 aspect ratios, and selectable subtitle tracks.
  - **Blu-ray (BDMV):** H.264/AVC High Profile Level 4.1, `tsMuxeR` BDMV/CERTIFICATE structures, and UDF 2.50 formatting.
- 💬 **Subtitle Preservation:** Automatically converts PGS and SRT subtitle streams into compliant DVD subpictures (`dvdsub`), selectable using standard remote control subtitle toggles.
- ⏭️ **Full-Movie Chapters:** Preserves embedded chapter markers from source files, or automatically creates 5-minute interval chapters across the entire movie duration.
- ⚡ **Hardware Acceleration:** Full NVIDIA NVDEC hardware decode for all common formats, NVIDIA NVENC hardware encoding for Blu-ray streams, and multi-core CPU matrix-optimized transcoding with automatic fallback.
- ⏸️ **Pause / Resume Queue Controls:** Suspend in-progress transcoding or burning jobs on the fly. When a running job completes, DVDCompress automatically picks up and resumes the next queued job.
- 🔥 **Direct Optical Disc Burning:** Real-time SCSI/SATA/USB optical drive detection (`/dev/sr*`, `/dev/sg*`), disc media status inspection, and rock-solid burning with buffer underrun protection via `growisofs` and `cdrskin`/`xorriso`.
- 🌐 **Modern Real-Time Web Interface:** Live WebSocket pipeline monitoring, interactive media directory navigation, real-time transcoding FPS/speed/ETA telemetry, live CPU, RAM, and GPU/VRAM gauges, and integrated log terminal stream.
- 💿 **Standalone ISO Burner:** Quickly burn existing ISO files directly to disc with customizable burn speeds.

---

## 🏗 Architecture

```
+-------------------------------------------------------------------------+
|                              Docker Container                           |
|                                                                         |
|  +-----------------------+     +-------------------------------------+  |
|  |     Modern Web UI     | <-> | FastAPI Application Server (Python) |  |
|  |  (HTML5/CSS/Vanilla)  |     |  - REST API & WebSocket Handler     |  |
|  |  - Telemetry Chips    |     |  - Async Job Pipeline & Queue       |  |
|  +-----------------------+     +-------------------------------------+  |
|                                                   |                     |
|           +---------------------------------------+                     |
|           |                   |                   |                     |
|           v                   v                   v                     |
|  +----------------+  +-----------------+  +-----------------+           |
|  | Transcoding    |  | Disc Authoring  |  | Disc Burning    |           |
|  |  - FFmpeg      |  |  - dvdauthor    |  |  - growisofs    |           |
|  |  - NVDEC/CUDA  |  |  - spumux       |  |  - cdrskin      |           |
|  |  - NVENC / CPU |  |  - tsMuxeR      |  |  - xorriso      |           |
|  |  - ffprobe     |  |  - genisoimage  |  |  - lsscsi       |           |
|  +----------------+  +-----------------+  +-----------------+           |
+-------------------------------------------------------------------------+
       |                                   |                    |
       v (Volume Mounts)                   v (GPU Passthrough)  v (Device Pass)
   /media  (Source Videos)              --gpus all          /dev/sr0, /dev/sg0
   /output (Authored ISOs)             (NVIDIA Runtime)      (Optical Writer)
   /config (App Settings)
   /tmp/dvdcompress (Scratch)
```

---

## 🚀 Quick Start

### 1. Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  dvdcompress:
    image: hovee/dvdcompress:latest
    container_name: dvdcompress
    restart: unless-stopped
    privileged: true
    ports:
      - "8080:8080"
    environment:
      - TZ=America/New_York
      - DVDCOMPRESS_LOG_LEVEL=INFO
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all,video,compute,utility
    volumes:
      - /path/to/your/media:/media:ro
      - /path/to/your/output:/output:rw
      - /path/to/your/config:/config:rw
      - /path/to/your/temp:/tmp/dvdcompress:rw
    devices:
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
  --privileged \
  --gpus all \
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

#### CPU-Only Mode
```bash
docker run -d \
  --name dvdcompress \
  --restart unless-stopped \
  --privileged \
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
1. Install the **NVIDIA Driver** plugin from Community Applications (if using an NVIDIA GPU).
2. Add a new Docker Container in Unraid (or use the included `unraid-template.xml`):
   - **Repository:** `hovee/dvdcompress:latest`
   - **WebUI:** `http://[IP]:[PORT:8080]`
   - **Port:** `8080` $\rightarrow$ `8080`
   - **Path 1 (Media):** `/mnt/user/Media` $\rightarrow$ `/media` (Read-only)
   - **Path 2 (Output):** `/mnt/user/Media/dvd_output` $\rightarrow$ `/output` (Read/Write)
   - **Path 3 (Config):** `/mnt/user/appdata/dvdcompress` $\rightarrow$ `/config`
   - **Path 4 (Scratch Temp):** `/mnt/user/appdata/dvdcompress/working` $\rightarrow$ `/tmp/dvdcompress`
   - **Device 1:** `/dev/sr0` $\rightarrow$ `/dev/sr0`
   - **Device 2:** `/dev/sg0` $\rightarrow$ `/dev/sg0`
   - **Privileged:** `ON`
   - **Extra Parameters:** `--gpus all --runtime=nvidia`
   - **Variables:** `NVIDIA_VISIBLE_DEVICES` = `all`, `NVIDIA_DRIVER_CAPABILITIES` = `all,video,compute,utility`

### TrueNAS SCALE
1. Go to **Apps** $\rightarrow$ **Launch Docker Image** (or Custom App).
2. Configure Image: `hovee/dvdcompress:latest`.
3. Set Port Forwarding: Host Port `8080` to Container Port `8080`.
4. Configure Host Path Storage Volumes for `/media`, `/output`, `/config`, and `/tmp/dvdcompress`.
5. Under **GPU Resource Allocation**, allocate 1 NVIDIA GPU.
6. Under **Device Passthrough**, add `/dev/sr0` and `/dev/sg0` with Privileged access enabled.

---

## ⚡ Hardware Acceleration

DVDCompress utilizes NVIDIA CUDA and NVDEC/NVENC to accelerate media transcoding:

| Feature | NVIDIA GPU (NVDEC/NVENC) | CPU (Fallback) |
| :--- | :--- | :--- |
| **Decode Acceleration** | Hardware NVDEC (`-hwaccel cuda`) | Multi-threaded Software |
| **DVD-Video Transcode** | NVDEC decode + MPEG-2 Video Encoder | `mpeg2video` Software Encoder |
| **Blu-ray Transcode** | `h264_nvenc` Hardware Encoder | `libx264` High Profile Level 4.1 |
| **Audio Processing** | Multi-channel AC3 encoder (Stereo / 5.1) | Multi-channel AC3 encoder |

---

## 💿 Optical Drive Pass-Through

To enable physical disc burning from inside Docker, pass both the optical block device (`/dev/sr*`) and the SCSI generic device (`/dev/sg*`):

1. **Identify connected optical drives on the host:**
   ```bash
   lsscsi -k
   # Example output: [2:0:0:0] cd/dvd ASUS BW-16D1HT /dev/sr0 /dev/sg0
   ```

2. **Verify host permissions:**
   ```bash
   ls -l /dev/sr0 /dev/sg0
   ```

3. **Pass devices to container:**
   ```yaml
   devices:
     - /dev/sr0:/dev/sr0
     - /dev/sg0:/dev/sg0
   ```

---

## 📊 Technical Specifications & Capacities

| Disc Format | Physical Type | Target Capacity | Usable Budget | Max Video Bitrate | Audio Spec | Video Standard |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DVD-5** | Single Layer | 4.7 GB | 4,300 MB | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **DVD-9** | Dual Layer | 8.5 GB | 7,850 MB | 8,000 kbps | AC3 Stereo/5.1 (48kHz) | MPEG-2 (NTSC 720×480 / PAL 720×576) |
| **BD-25** | Single Layer | 25.0 GB | 23,000 MB | 35,000 kbps | AC3 Stereo/5.1 | H.264/AVC High@L4.1 (1080p) |
| **BD-50** | Dual Layer | 50.0 GB | 46,000 MB | 35,000 kbps | AC3 Stereo/5.1 | H.264/AVC High@L4.1 (1080p) |
| **BD-66** | Dual Layer UHD | 66.0 GB | 61,500 MB | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC UHD-BD |
| **BD-100** | Triple Layer BDXL | 100.0 GB | 92,000 MB | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |
| **BD-128** | Quad Layer BDXL | 128.0 GB | 118,000 MB | 35,000 kbps | AC3 Stereo/5.1 | H.264 / HEVC BDXL |

---

## 📡 REST API & WebSocket Reference

DVDCompress provides a full REST and WebSocket API:

- `GET /api/health` — Application health check
- `GET /api/files?path=/media/...` — File browser listing playable video files and ISOs
- `POST /api/probe` — FFprobe media analysis (duration, codec, resolution, audio streams, chapters, subtitles)
- `POST /api/calculate` — Bitrate budget calculation based on input durations and disc target
- `GET /api/drives` — Scan host system for optical drives and query disc media presence
- `GET /api/system` — Live system telemetry (CPU %, RAM used/total, GPU %, VRAM, temp)
- `POST /api/jobs` — Create and start a transcoding/authoring/burning job
- `POST /api/burn-iso` — Directly burn an existing ISO file to an optical drive
- `GET /api/jobs` — Retrieve active and historical jobs
- `GET /api/jobs/{job_id}` — Get single job progress and telemetry
- `POST /api/jobs/{job_id}/pause` — Pause an in-progress job
- `POST /api/jobs/{job_id}/resume` — Resume a paused job
- `POST /api/jobs/{job_id}/cancel` — Cancel an in-progress job and terminate child processes
- `WS /ws/jobs/{job_id}` — Real-time bidirectional WebSocket stream for progress updates and live logs

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

# Run full test suite
pytest tests/ -v

# Run local development server
uvicorn dvdcompress.api:app --host 127.0.0.1 --port 8080 --reload
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


